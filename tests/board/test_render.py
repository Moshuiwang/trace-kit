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
from boardlib.model import Board, Header, Status, Tier  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")
SIZES = ((150, 52), (75, 52))
CORNERS = "┌╔┏"


def body_lines(text):
    """去掉图例行（以「节点」「边框」「■未知」开头的尾行）。"""
    lines = text.splitlines()
    while lines and (lines[-1].startswith(("节点", "边框", "■")) or not lines[-1]):
        lines.pop()
    return lines


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
                        self.assertNotIn("…", text)
                        for ln in lines:
                            self.assertLessEqual(render.dw(ln), W, ln)
                            self.assertEqual(ln, ln.rstrip())
                        if W < 120:
                            for ln in body_lines(text):
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
        self.assertTrue(any(ln.strip("│ ").startswith("Wave 3") and "↺重审来源" not in ln for ln in lines))
        self.assertEqual(text.count("? 自由文本 · 待做"), 2)   # 两张并排在同一行
        idx = text.index("? 自由文本")
        self.assertGreater(idx, text.index("S-9c 实施"), "自由文本卡放图末")
        text2 = render.dump(sample_boards.board_complex(), "complex", 150, 200)
        self.assertIn("Wave 2 · 评论 1 · dd53ecf", text2)

    def test_complex_view_rework_stale_unknown_chips(self):
        text = render.dump(sample_boards.board_complex(), "complex", 150, 200)
        self.assertIn("↺重审来源", text)
        self.assertIn("[候选 dd53ec 冻结 → 已变 8c58a7]", text)
        self.assertIn("[gh 不可用]", text)
        self.assertIn("这一行的标题故意超过十八个汉字", text)
        self.assertNotIn("…", text)
        lines, _, _ = render.frame(sample_boards.board_complex(), "complex", 150, 80, 0, 0)
        joined = "\n".join(lines)
        self.assertIn("\x1b[38;5;240m", joined)   # 失效灰暗
        self.assertIn("\x1b[3m", joined)           # 未知斜体


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
