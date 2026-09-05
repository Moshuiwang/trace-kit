# -*- coding: utf-8 -*-
"""渲染结构断言：两视图 × 两尺寸 × 五个样例；四档边框、角标、未知、无省略号、6 模块 150×52 不滚动、75 列每行 ≤ 3 张、--why。"""
from __future__ import annotations

import os
import re
import sys
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "plugin", "scripts"))
sys.path.insert(0, HERE)

import sample_boards  # noqa: E402
from boardlib import render  # noqa: E402
from boardlib.model import Board, EvidenceType, Header, Status, Tier, Val, Why  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")
SIZES = ((150, 52), (75, 52))
CORNERS = "┌╔┏"


def split_frame(text, W, view):
    """dump 帧切成 (头部 10 行, 正文, 图例行)；图例永远是最后 k 行（k 由 render 自己算）。"""
    lines = text.splitlines()
    k = len(render._legend_rows(W, view))
    return lines[:render.HEADER_ROWS], lines[render.HEADER_ROWS:-k], lines[-k:]


class DumpShapeTest(unittest.TestCase):
    def test_every_sample_fits_and_is_plain(self):
        for name, factory in sample_boards.BOARDS.items():
            board = factory()
            for view in ("simple", "complex"):
                for W, H in SIZES:
                    text = render.dump(board, view, W, H)
                    lines = text.splitlines()
                    with self.subTest(sample=name, view=view, size=(W, H)):
                        self.assertLessEqual(len(lines), H)
                        self.assertNotIn("\x1b", text)
                        head, body, legend = split_frame(text, W, view)
                        for ln in body + legend:
                            self.assertNotIn("…", ln)             # 卡片与图例零省略号；头部超宽用 …(+N) 提示（K-4）
                        for ln in lines:
                            self.assertLessEqual(render.dw(ln), W, ln)
                            self.assertEqual(ln, ln.rstrip())
                        if W < 120:
                            for ln in body:
                                self.assertLessEqual(sum(ln.count(c) for c in CORNERS), 3, ln)

    def test_six_modules_fit_150x52_without_scroll(self):
        board = sample_boards.board_six()
        self.assertEqual(render.scroll_limit(board, "simple", 150, 52), 0)
        text = render.dump(board, "simple", 150, 52)
        for mv in board.modules:
            self.assertIn(render.short_title(mv.section.title), text)
        self.assertIn("视图 简易版", text)

    def test_frame_lines_and_anim(self):
        board = sample_boards.board_six()
        lines, anim, avail = render.frame(board, "simple", 150, 52, 0, 0)
        self.assertEqual(len(lines), 52)
        self.assertGreater(avail, 0)
        for ln in lines:
            self.assertLessEqual(render.dw(ANSI.sub("", ln)), 150)
        self.assertTrue(anim, "运行中 / 观察节点与图例应有动效单元")
        lines2, _, _ = render.frame(board, "simple", 150, 52, 0, 3)
        self.assertNotEqual(lines, lines2, "phase>0 应把高亮格烘进整帧")
        self.assertEqual([ANSI.sub("", a) for a in lines], [ANSI.sub("", b) for b in lines2])


class BorderAndMarksTest(unittest.TestCase):
    def test_four_tiers_and_more_mark(self):
        text = render.dump(sample_boards.board_tiers(), "simple", 150, 52)
        for sample in ("┌─ 块 A · 完成", "╔═ Wave 0 · 完成", "┏━ Wave 1 · 运行中", "┏╍ Wave 2 · 观察", "┏╍ 收口 · 待做 ⟲5"):
            self.assertIn(sample, text)
        self.assertIn("┇", text)
        self.assertIn("╚", text)
        self.assertIn("┗━", text)

    def test_legend_has_five_tier_samples_and_ten_statuses(self):
        for W in (150, 75):
            text = render.dump(sample_boards.board_simple(), "simple", W, 52)
            for lab in ("未审", "1轮", "2轮", "3轮", "⟲N 3轮+", "┌─┐", "╔═╗", "┏━┓", "┏╍┓"):
                self.assertIn(lab, text, "W=%d 缺 %s" % (W, lab))
            for _, lab in render.STATUS_LEGEND:
                self.assertIn("■" + lab if lab not in ("运行中", "观察") else "┌──┐" + lab, text)

    def test_marks_unknown_unconfigured(self):
        text = render.dump(sample_boards.board_six(), "simple", 150, 52)
        self.assertIn("完整门禁 ▰▰▱▱▱▱ 3实/10", text)
        self.assertIn("人次 ▰▰▰▱▱▱ 6报/14", text)
        self.assertIn("PR 4推   人次", text)               # 无上限：只写数字＋角标，不画条
        self.assertNotIn("PR ▰", text)
        self.assertIn("审 2实 · 外 1实", text)
        self.assertIn("预发已升级 未配置", text)
        self.assertIn("合入主干 否", text)
        text = render.dump(sample_boards.board_unknown(), "simple", 150, 52)
        self.assertIn("审 未知", text)
        self.assertIn("合入主干 未知", text)
        self.assertIn("完整门禁 未知", text)
        text = render.dump(sample_boards.board_tiers(), "simple", 150, 52)
        self.assertIn("已发布 是", text)
        self.assertIn("已上生产 否", text)

    def test_duration_formats(self):
        self.assertEqual(render.dur_text(41, None, 45, Status.DONE), "41/45")
        self.assertEqual(render.dur_text(None, 38, 60, Status.RUNNING), "38/60")
        self.assertEqual(render.dur_text(None, None, 40, Status.TODO), "/40")
        self.assertEqual(render.dur_text(None, None, 30, Status.DONEQ), "?/30")
        self.assertEqual(render.dur_text(None, 12, None, Status.RUNNING), "12/─")

    def test_status_words_only_in_dump(self):
        board = sample_boards.board_six()
        text = render.dump(board, "simple", 150, 52)
        for word in ("块 A · 完成", "Wave 0 · 自述未证", "Wave 1 · 卡住", "Wave 2 · 待做", "收口 · 待做"):
            self.assertIn(word, text)
        text = render.dump(board, "complex", 150, 300)
        for pat in (r"S-1( 实施)? · 完成", r"S-2( 实施)? · 运行中", r"S-4( 实施)? · 观察", r"S-5( 实施)? · 卡住", "S-8b 人工 · 待人类", "S-9c 实施 · 待做"):
            self.assertRegex(text, pat)                    # 28 列窄卡放不下类型词时退成「编号 · 状态词」，状态词不裁
        self.assertNotIn(" · 完 ", text)
        self.assertNotIn(" · 运行 ", text)
        for view in ("simple", "complex"):
            lines, _, _ = render.frame(board, view, 150, 300, 0, 0)
            plain = ANSI.sub("", "\n".join(lines))
            self.assertNotIn(" · 完成", plain)
            self.assertNotIn(" · 运行中", plain)
        self.assertIn("节点 ■完成", text)                   # 图例在 dump 里保留

    def test_free_text_cards_and_third_line(self):
        board = sample_boards.board_six()
        text = render.dump(board, "complex", 150, 300)
        self.assertIn("? 自由文本 · 待做", text)
        self.assertIn("这一行没有编号所以解析不", text)                       # 去掉复选框标记后截 18 汉字（卡宽 28 折两行）
        self.assertIn("了，正文故意", text)
        self.assertNotIn("写得很", text)
        self.assertIn("任务表第 12 行 · 未解析", text)
        self.assertIn("任务表第 40 行 · 未解析", text)
        self.assertNotIn("…", text)
        self.assertNotIn("自由文本", render.dump(board, "simple", 150, 52))
        self.assertIn("│ Wave 1 · PR #19 · 评论 2", text)                    # 第三行：章节名 · 指针摘要（28 列卡内只裁不省略）
        self.assertIn("│ Wave 1 · impl_b", text)
        self.assertEqual(render.pointer_summary(board.steps[3].step), "PR #19 · 评论 2 · impl_a")
        lines = text.splitlines()
        self.assertTrue(any(ln.strip("│ ").startswith("Wave 3") and "↺重审" not in ln for ln in lines))
        self.assertEqual(text.count("? 自由文本 · 待做"), 2)   # 两张并排在同一行
        idx = text.index("? 自由文本")
        self.assertGreater(idx, text.index("S-9c 实施"), "自由文本卡放图末")
        text2 = render.dump(sample_boards.board_complex(), "complex", 150, 200)
        self.assertIn("Wave 2 · 评论 1 · dd53ecf", text2)

    def test_complex_view_rework_stale_unknown_chips(self):
        text = render.dump(sample_boards.board_complex(), "complex", 150, 200)
        self.assertIn("↺重审 Wave 2 · impl_a", text)     # K-5：短形放第三行行首，不被卡宽裁掉
        self.assertIn("[候选 dd53ec 冻结 → 已变 8c58a7]", text)
        self.assertIn("[gh 不可用]", text)
        self.assertIn("这一行的标题故意超过十八个汉字", text)
        self.assertNotIn("…", text)
        lines, _, _ = render.frame(sample_boards.board_complex(), "complex", 150, 80, 0, 0)
        joined = "\n".join(lines)
        self.assertIn("\x1b[38;5;240m", joined)   # 失效灰暗
        self.assertIn("\x1b[3m", joined)           # 未知斜体


class FixPackTest(unittest.TestCase):
    """统一修复包（账本 K-4 / K-5 / R1-16 / R2-3 / R2-6 / R2-10 / R2-11 / R2-12 / R2-13）。"""

    def test_k4_header_overflow_is_marked_not_silent(self):
        b = sample_boards.board_six()
        b.header.doubt = "存疑" * 120
        b.header.block = "阻塞" * 120
        b.header.nxt = "S-7a 集成 → `smoke.sh --strict`" + "很长" * 80
        for W in (150, 75):
            text = render.dump(b, "simple", W, 52)
            for label in ("存疑", "阻塞", "下一步"):
                row = next(ln for ln in text.splitlines() if ln.startswith(label))
                self.assertLessEqual(render.dw(row), W)
                self.assertRegex(row, r"…\(\+\d+\)$", "超长行必须以 …(+N) 结尾提示：%s" % row)
        self.assertEqual(render.fit_mark("abc", 3), "abc")
        self.assertEqual(render.fit_mark("abcdefghij", 8), "abc…(+7)")

    def test_k4_budget_overflow_marked(self):
        b = sample_boards.board_six()
        b.header.budget = [("预算条%d" % k, Val(k, source="x"), 10) for k in range(12)]
        text = render.dump(b, "simple", 75, 52)
        row = next(ln for ln in text.splitlines() if ln.startswith("预算"))
        self.assertLessEqual(render.dw(row), 75)
        self.assertRegex(row, r"…\(\+\d+ 项\)$")

    def test_r2_6_warning_survives_long_title_and_narrow_pane(self):
        b = sample_boards.board_six()
        b.header.title = "非常长的标题" * 30
        b.header.warnings = ["刷新超时（65 秒未返回）"]
        for W in (150, 75):
            text = render.dump(b, "simple", W, 52)
            row0 = text.splitlines()[0]
            self.assertIn("⚠ 刷新超时（65 秒未返回）", row0)
            self.assertIn("更新 ", row0)
            self.assertLessEqual(render.dw(row0), W)
            self.assertIn("…(+", row0)                       # 让位的是标题，且带提示

    def test_k5_rework_mark_first_on_third_line(self):
        text = render.dump(sample_boards.board_six(), "complex", 150, 300)
        self.assertIn("│ ↺重审 Wave 2", text)              # 28 列窄卡里也完整
        self.assertNotIn("↺重审来源", text)

    def test_r1_16_unknown_rounds_border_and_legend(self):
        text = render.dump(sample_boards.board_unknown(), "simple", 150, 52)
        title = next(ln for ln in text.splitlines() if "Wave 1" in ln and "┄" in ln)
        self.assertIn("┌┄ Wave 1", title)
        self.assertIn("审 未知", title)
        self.assertIn("┆ 审 未知 · 外 未知", text)
        self.assertIn("└┄", text)
        self.assertIn("┌┄┐未知", text)                      # 图例多一档
        text = render.dump(sample_boards.board_six(), "simple", 150, 52)
        self.assertNotIn("┄", text.split("节点")[0])          # 可得时不画虚线

    def test_r2_3_external_strings_sanitized(self):
        b = sample_boards.board_six()
        b.header.title = "标题\x1b[?1049l尾\x9b31m"
        b.header.block = "第一行\n第二行\r第三行"
        b.header.warnings = ["告警\x1b]0;x\x07尾"]
        b.modules[0].what = "什么\x9b31m色\x00"
        b.steps[0].step.title = "t\x1b]0;x\x07itle"
        b.steps[0].chip = "chip\r芯\x07"
        b.unparsed = [(3, "- [ ] 自由\x1b[2Jtext")]
        b.why.append(Why("主体|x", "状态\n换行", EvidenceType.PR_STATE, "src\x1b[m", "值|带竖线\n和换行", sample_boards.NOW))
        for view in ("simple", "complex"):
            text = render.dump(b, view, 150, 300, why=True)
            for bad in ("\x1b", "\x9b", "\r", "\x07", "\x00"):
                self.assertNotIn(bad, text)
            self.assertIn("第一行 第二行 第三行", text)
            self.assertIn("标题尾", text)                    # 整段 CSI / C1-CSI 序列被删，不留残字
            lines, _, _ = render.frame(b, view, 150, 300, 0, 0)
            for ln in lines:
                self.assertNotIn("\x1b", ANSI.sub("", ln))
                self.assertNotIn("\x9b", ln)
        why = text.split("证据链（--why）")[1].splitlines()
        self.assertTrue(any("主体\\|x | 状态 换行 | pr_state | src | 值\\|带竖线 和换行" in ln for ln in why), why[-3:])

    def test_r2_10_nfc_and_zero_width_attach(self):
        b = sample_boards.board_six()
        b.header.title = "cafe\u0301 a\u200db"
        text = render.dump(b, "simple", 150, 52)
        self.assertIn("café a\u200db", text)                # NFC 合成；ZWJ 附着前一格、不占列
        row0 = text.splitlines()[0]
        self.assertLessEqual(render.dw(row0), 150)
        self.assertEqual(render.dw("a\u200db"), 2)

    def test_r2_11_status_word_is_uncuttable_suffix(self):
        steps = [sample_boards.step("P-%d" % k, "并行步骤 %d" % k, True, 0, Status.DONEQ, actual=130, est=450) for k in range(1, 6)]
        mod = sample_boards.module(0, "Wave 1", Status.DONEQ, Tier.NONE, 5, 5, sample_boards.rounds(), "无", actual=130, est=450, steps=steps)
        b = Board(sample_boards.header("窄卡", "x", "", "", "", ""), steps, [mod], sample_boards.NOW)
        text = render.dump(b, "complex", 150, 60)
        row = next(ln for ln in text.splitlines() if "P-1" in ln)
        self.assertEqual(row.count("自述未证"), 5, row)         # 五张 28 列卡的状态词一个都不裁
        self.assertIn("130/450", row)                           # 时长保留（去掉了它两侧的空格）
        self.assertLessEqual(render.dw(row), 150)

    def test_r2_12_simple_overflow_hint_and_chain_zero_scroll(self):
        b = sample_boards.board_six()
        self.assertEqual(render.scroll_limit(b, "simple", 150, 52), 0)   # 链式六模块零滚动
        text = render.dump(b, "simple", 150, 40)
        self.assertRegex(text.splitlines()[0], r"⚠ .*简易版 \d+ 行超一屏")
        self.assertNotIn("超一屏", render.dump(b, "complex", 150, 40).splitlines()[0])

    def test_r2_13_tiny_pane(self):
        b = sample_boards.board_six()
        for W, H in ((15, 40), (150, 8), (10, 5)):
            lines, anim, avail = render.frame(b, "simple", W, H, 0, 0)
            self.assertEqual(len(lines), H)
            self.assertIn("窗口过小", ANSI.sub("", lines[0]))
            self.assertEqual(anim, [])
            self.assertEqual(render.scroll_limit(b, "simple", W, H), 0)
            text = render.dump(b, "simple", W, H)
            self.assertEqual(len(text.splitlines()), 1)
            self.assertLessEqual(render.dw(text.strip()), W)


class ApiContractTest(unittest.TestCase):
    def test_validate_called_on_entry(self):
        board = sample_boards.board_simple()
        board.modules[0].status = "done"          # 写错状态串
        with self.assertRaises(ValueError):
            render.dump(board, "simple", 150, 52)
        with self.assertRaises(ValueError):
            render.frame(board, "simple", 150, 52, 0, 0)

    def test_bad_view_rejected(self):
        with self.assertRaises(ValueError):
            render.dump(sample_boards.board_simple(), "fancy", 150, 52)

    def test_empty_board_and_placeholder(self):
        board = Board(Header("采集中…", "", "", "", [], "", "", [], ["刷新超时（65 秒未返回）"]), [], [], datetime(2026, 9, 5, tzinfo=timezone.utc))
        text = render.dump(board, "simple", 150, 52)
        self.assertIn("采集中…", text)
        self.assertIn("⚠ 刷新超时", text)
        self.assertLessEqual(len(text.splitlines()), 52)

    def test_why_table(self):
        text = render.dump(sample_boards.board_unknown(), "simple", 150, 52, why=True)
        self.assertIn("证据链（--why）", text)
        self.assertIn("Wave 1 | unknown | comment_title | gh.issue |  | 2026-09-05 14:00 | 否", text)
        self.assertIn("阶段 merged | 未知 | pr_state | gh.prs", text)
        for ln in text.splitlines():
            self.assertEqual(ln, ln.rstrip())

    def test_scroll_clamps(self):
        board = sample_boards.board_six()
        limit = render.scroll_limit(board, "complex", 150, 52)
        self.assertGreater(limit, 10)
        top, _, _ = render.frame(board, "complex", 150, 52, 0, 0)
        end, _, _ = render.frame(board, "complex", 150, 52, 10 ** 6, 0)
        self.assertNotEqual(top, end)
        self.assertIn("↕ %d/%d" % (limit, limit), ANSI.sub("", "\n".join(end)))

    def test_tier_table_complete(self):
        for tier in Tier:
            self.assertIn(tier, render.BORDER)
            self.assertIn(tier, render.TIER_LABEL)


if __name__ == "__main__":
    unittest.main()
