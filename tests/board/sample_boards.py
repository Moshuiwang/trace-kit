# -*- coding: utf-8 -*-
"""手工构造的 Board 样例（S-3 渲染 / TUI 测试用；S-5 夹具与 run_fake_tui 也可复用）。

    import sample_boards
    board = sample_boards.BOARDS["six"]()          # simple / complex / tiers / unknown / six
    build = sample_boards.fake_build("six", delay=0.5, fail="none")   # 假 build()，可注入延迟 / 异常 / 超时

样例形态：
    simple  ：3 模块，模块 0 → 模块 1 ‖ 模块 2（并排）。
    complex ：4 路并行实施 → 冻结 → 审核（失效）→ 修复包（↺）→ 复核 → 门禁 → 人工 → 发布；含 F1–F4 四种故障。
    tiers   ：5 模块链，边框档位 0 / 1 / 2 / 3 / 3 轮以上齐全。
    unknown ：证据不可得——模块轮数未知、Step 未知、五级阶段未知 / 未配置、预算未知。
    six     ：块 A / Wave 0 / Wave 1 / Wave 2 / Wave 3 / 收口 六模块链、21 个 Step（150×52 简易版必须一屏放下）。
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugin", "scripts"))

from boardlib.model import (  # noqa: E402
    Board, EvidenceType, Grade, Header, ModuleView, Rounds, Section, StageLevel, Status, Step, StepType, StepView, Tier, Val, Why,
)

NOW = datetime(2026, 9, 5, 6, 0, tzinfo=timezone.utc)      # 北京 14:00


def ago(minutes):
    return NOW - timedelta(minutes=minutes)


def val(v, grade=Grade.MEASURED, source="gh.prs"):
    return Val(v, grade, source, NOW, True)


def rounds(review=0, external=0, fixpack=0, red=0, green=0, unknown=False):
    if unknown:
        return Rounds(Val.unknown("gh.issue"), Val.unknown("gh.issue"), Val.unknown("gh.issue"), Val.unknown("gh.runs"), Val.unknown("gh.runs"))
    return Rounds(val(review, source="gh.issue"), val(external, source="gh.issue"), val(fixpack, source="gh.issue"),
                  val(red, Grade.INFERRED, "gh.runs"), val(green, Grade.INFERRED, "gh.runs"))


def rounds_line(r):
    return "审 %s · 外 %s · 修 %s · CI 红%s 绿%s" % (r.review.text(), r.external.text(), r.fixpack.text(), r.ci_red.text(), r.ci_green.text())


def step(sid, title, checked, section, status, *, stype=StepType.IMPL, needs=(), owner="", est=None, actual=None, elapsed=None,
         chip="", chip_status=None, rework=False, started=None, last=None, why=()):
    st = Step(sid, title, checked, section, 0, stype, list(needs), owner, est, [], [], [], [], "")
    return StepView(st, status, started, last, actual, elapsed, est, chip, chip_status or status, rework, list(why))


def module(index, title, status, tier, done, total, r, evidence, *, needs=(), actual=None, elapsed=None, est=None, steps=(), why=()):
    sec = Section(index, title, [sv.step for sv in steps])
    what = "%s %d/%d" % (title.split("（")[0].strip(), done, total)
    return ModuleView(sec, status, tier, r, done, total, what, rounds_line(r), evidence, actual, elapsed, est, list(needs), list(why))


def stages(merged=False, published=False, staging=None, production=None, closed=False, unknown=False):
    def lv(key, label, v):
        if unknown:
            return StageLevel(key, label, Val.unknown("gh"), True)
        if v is None:
            return StageLevel(key, label, Val.unknown("config"), False)
        return StageLevel(key, label, val(v), True)
    return [lv("merged", "合入主干", merged), lv("published", "已发布", published), lv("staging", "预发已升级", staging),
            lv("production", "已上生产", production), lv("closed", "收口", closed)]


def header(title, stage, block, nxt, doubt, evidence, budget=None, stg=None, warnings=()):
    budget = budget if budget is not None else [("完整门禁", val(3, source="gh.runs"), 10), ("PR", val(4, Grade.INFERRED, "gh.prs"), None), ("人次", val(6, Grade.REPORTED, "gh.issue"), 14)]
    return Header(title, stage, block, nxt, budget, doubt, evidence, stg if stg is not None else stages(), list(warnings))


def why(subject, status, ev, source, value, available=True):
    return Why(subject, status, ev, source, value, NOW, available)


# ---------- simple：3 模块，0 → 1 ‖ 2 ----------
def board_simple():
    s1 = step("S-1", "实现 validateEmail", True, 0, Status.DONE, est=30, actual=28, chip="PR #31 ✓ 自测✓ CI✓ 18s", chip_status=Status.DONE)
    s2 = step("S-2", "补边界测试", False, 1, Status.WATCH, needs=["S-1"], est=45, elapsed=65, chip="commit 1f2e3d · 65m 前 · 无 PR", chip_status=Status.WATCH)
    s3 = step("S-3", "独立审核", False, 2, Status.TODO, stype=StepType.REVIEW, needs=["S-1"], est=20, chip="审核结论 待", chip_status=Status.TODO)
    m0 = module(0, "Wave 1（实施）", Status.DONE, Tier.NONE, 1, 1, rounds(green=1), "PR #31 MERGED · 评论 1 · 最新 13:10", actual=28, est=30, steps=[s1])
    m1 = module(1, "Wave 2", Status.WATCH, Tier.NONE, 0, 1, rounds(), "commit 1f2e3d · 评论 0 · 最新 12:55", needs=[0], elapsed=65, est=45, steps=[s2])
    m2 = module(2, "Wave 3", Status.TODO, Tier.NONE, 0, 1, rounds(), "无", needs=[0], est=20, steps=[s3])
    h = header("简单用例 · batch/30-demo", "Executing · W1（1/3 完成）", "S-2 65 分钟无外部证据（观察；90 分钟转卡住）", "S-3 等 S-2 · 窗口状态未知，需元守护核",
               "合同 PR #30 由发起人自合、零批准", "65 分钟前 · commit 1f2e3d（S-2）")
    return Board(h, [s1, s2, s3], [m0, m1, m2], NOW, [why("阶段 merged", "否", EvidenceType.PR_STATE, "gh.prs", "OPEN")])


# ---------- complex：四路并行 + 审核链 + F1–F4 ----------
def board_complex():
    a1 = step("S-A1", "打包 plugin 目录", False, 0, Status.STALLED, est=90, elapsed=130, chip="8c58a7 · 95m 前 · 无 PR", chip_status=Status.STALLED, owner="impl_a")
    a2 = step("S-A2", "打包 template 分层 CI", True, 0, Status.DONEQ, est=30, chip="无 commit · 无 PR", chip_status=Status.DONEQ, owner="impl_b")
    a3 = step("S-A3", "examples 示例清单", True, 0, Status.DONE, est=45, actual=41, chip="PR #21 ✓ 自测✓ CI✓ 26s", chip_status=Status.DONE, owner="impl_c")
    a4 = step("S-A4", "deploy 骨架", False, 0, Status.RUNNING, est=60, elapsed=38, chip="PR #24 打开 · CI 跑 3m", chip_status=Status.RUNNING, owner="impl_d")
    k = step("K-1", "候选冻结", True, 1, Status.STALE, stype=StepType.GATE, needs=["S-A1", "S-A2", "S-A3", "S-A4"], chip="候选 dd53ec 冻结 → 已变 8c58a7", chip_status=Status.STALE)
    r1 = step("R-1", "独立审核（子代理 · 第 1 轮）", True, 1, Status.STALE, stype=StepType.REVIEW, needs=["K-1"], est=60, actual=25, chip="结论 0 P0 / 2 P1 / 3 P2 · 已失效", chip_status=Status.STALE)
    f1 = step("F-1", "统一修复包", False, 1, Status.READY, needs=["R-1"], est=30, rework=True, owner="impl_a", chip="修复包 PR 待", chip_status=Status.TODO)
    r2 = step("R-2", "定向复核（同一审核者 · 第 2 轮）", False, 1, Status.TODO, stype=StepType.REVIEW, needs=["F-1"], est=15, chip="复核结论 待", chip_status=Status.TODO)
    g = step("G-1", "完整门禁", False, 2, Status.TODO, stype=StepType.GATE, needs=["R-2"], est=8, chip="CI run 待", chip_status=Status.TODO)
    hm = step("H-1", "产品负责人批准发布", False, 2, Status.HUMAN, stype=StepType.HUMAN, needs=["G-1"])
    d = step("D-1", "发布 tag v0.2.0", False, 2, Status.TODO, stype=StepType.DEPLOY, needs=["H-1"], est=10, chip="tag 待", chip_status=Status.TODO)
    u = step("U-1", "这一行的标题故意超过十八个汉字用来验证只裁不加省略号的规则", False, 2, Status.UNKNOWN, needs=["H-1"], chip="gh 不可用", chip_status=Status.UNKNOWN)
    steps = [a1, a2, a3, a4, k, r1, f1, r2, g, hm, d, u]
    m0 = module(0, "Wave 1（四路并行）", Status.STALLED, Tier.NONE, 2, 4, rounds(green=2, red=1), "PR #21 MERGED · PR #24 OPEN · 评论 3 · 最新 12:25", elapsed=130, est=225, steps=steps[:4])
    m1 = module(1, "Wave 2", Status.READY, Tier.ONE, 2, 4, rounds(review=1, fixpack=0), "评论 2 · 最新 11:40", needs=[0], actual=25, est=105, steps=steps[4:8])
    m2 = module(2, "Wave 3", Status.HUMAN, Tier.NONE, 0, 4, rounds(), "无", needs=[1], est=18, steps=steps[8:])
    h = header("演示 · batch/20-demo", "Executing · W1→W2（5/17 步骤完成）", "S-A1 95 分钟无外部证据；R-1 审核结论失效", "F-1 可立即做 · 窗口状态未知，需元守护核",
               "自述未证 1（S-A2）· 合同 PR #20 由发起人自合、零批准", "12 分钟前 · commit 8c58a7（S-A4）", warnings=["超限 1 行"])
    return Board(h, steps, [m0, m1, m2], NOW, [why("阶段 merged", "否", EvidenceType.PR_STATE, "gh.prs", "OPEN")])


# ---------- tiers：五档齐全 ----------
def board_tiers():
    mods, steps, specs = [], [], [
        ("块 A", Status.DONE, Tier.NONE, 0), ("Wave 0", Status.DONE, Tier.ONE, 1), ("Wave 1", Status.RUNNING, Tier.TWO, 2),
        ("Wave 2", Status.WATCH, Tier.THREE, 3), ("收口", Status.TODO, Tier.MORE, 5),
    ]
    for k, (title, st, tier, n) in enumerate(specs):
        sv = step("S-%d" % k, "%s 的步骤" % title, st == Status.DONE, k, st, needs=["S-%d" % (k - 1)] if k else [], est=30, chip="PR #%d" % (k + 10))
        steps.append(sv)
        mods.append(module(k, title, st, tier, 1 if st == Status.DONE else 0, 1, rounds(review=n, green=n), "评论 %d · 最新 13:%02d" % (n, k * 5),
                           needs=[k - 1] if k else [], actual=20 if st == Status.DONE else None, elapsed=None if st == Status.DONE else 12, est=30, steps=[sv]))
    h = header("五档边框样张", "Executing", "无", "Wave 2 等复核", "无", "3 分钟前", stg=stages(merged=True, published=True, staging=True, production=False, closed=False))
    return Board(h, steps, mods, NOW)


# ---------- unknown：证据不可得 ----------
def board_unknown():
    s1 = step("S-1", "已完成的步骤", True, 0, Status.DONE, actual=10, est=10, chip="PR #3 ✓")
    s2 = step("S-2", "gh 不可用时的步骤", False, 0, Status.UNKNOWN, needs=["S-1"], chip="gh 不可用", chip_status=Status.UNKNOWN,
              why=[why("S-2", "unknown", EvidenceType.PR_STATE, "gh.prs", "", False)])
    m0 = module(0, "Wave 1", Status.UNKNOWN, Tier.NONE, 1, 2, rounds(unknown=True), "未知", actual=None, est=10, steps=[s1, s2],
                why=[why("Wave 1", "unknown", EvidenceType.COMMENT_TITLE, "gh.issue", "", False)])
    h = header("证据不可得", "未知", "未知", "未知", "未知", "未知", budget=[("完整门禁", Val.unknown("gh.runs"), 10)], stg=stages(unknown=True),
               warnings=["gh 不可用：证据缺 4 键"])
    return Board(h, [s1, s2], [m0], NOW, [why("阶段 merged", "未知", EvidenceType.PR_STATE, "gh.prs", "", False)])


# ---------- six：六模块链 ----------
def board_six():
    S = []
    S += [step("A-1", "输入 Issue 与裁定给齐", True, 0, Status.DONE, actual=5, chip="评论 ✓ 13:5x", chip_status=Status.DONE)]
    S += [step("W0-1", "接管登记与只读盘点", True, 1, Status.DONE, needs=["A-1"], est=30, actual=26, chip="评论 ✓ 14:20", chip_status=Status.DONE),
          step("W0-2", "简易版真实快照", True, 1, Status.DONEQ, needs=["W0-1"], est=45, chip="无 commit · 无 PR", chip_status=Status.DONEQ)]
    S += [step("S-1", "小修包与 CODEOWNERS", True, 2, Status.DONE, needs=["W0-2"], est=45, actual=41, chip="PR #19 ✓ CI✓ 24s", chip_status=Status.DONE, owner="impl_a"),
          step("S-2", "解析与状态推断", False, 2, Status.RUNNING, needs=["W0-2"], est=120, elapsed=38, chip="worktree S-2 · 3 commits", chip_status=Status.RUNNING, owner="impl_b"),
          step("S-3", "渲染与 TUI", False, 2, Status.RUNNING, needs=["W0-2"], est=120, elapsed=35, chip="worktree S-3 · 1 commit", chip_status=Status.RUNNING, owner="impl_c"),
          step("S-4", "证据源配置", False, 2, Status.WATCH, needs=["W0-2"], est=60, elapsed=70, chip="worktree S-4 · 70m 前", chip_status=Status.WATCH, owner="impl_d"),
          step("S-5", "夹具与 CI", False, 2, Status.STALLED, needs=["W0-2"], est=60, elapsed=130, chip="8c58a7 · 95m 前 · 无 PR", chip_status=Status.STALLED, owner="impl_e"),
          step("S-6", "skill 与文档", False, 2, Status.TODO, needs=["S-2", "S-3", "S-4", "S-5"], est=45, chip="待：PR", chip_status=Status.TODO)]
    S += [step("S-7a", "集成与 Draft PR", False, 3, Status.TODO, needs=["S-6"], est=30, chip="CI run 待", chip_status=Status.TODO),
          step("S-7b", "独立审核与外审", False, 3, Status.TODO, stype=StepType.REVIEW, needs=["S-7a"], est=60, chip="审核结论 待", chip_status=Status.TODO),
          step("S-7c", "修复包与复核", False, 3, Status.TODO, needs=["S-7b"], est=45, rework=True, chip="复核结论 待", chip_status=Status.TODO),
          step("S-7d", "合 main 与 tag", False, 3, Status.TODO, stype=StepType.DEPLOY, needs=["S-7c"], est=10, chip="tag 待", chip_status=Status.TODO)]
    S += [step("S-8a", "安装插件并排试穿", False, 4, Status.TODO, needs=["S-7d"], est=60),
          step("S-8b", "产品负责人看一次", False, 4, Status.HUMAN, stype=StepType.HUMAN, needs=["S-8a"]),
          step("S-8c", "换窗口与退役旧脚本", False, 4, Status.TODO, needs=["S-8b"], est=15),
          step("S-8d", "收口小 PR", False, 4, Status.TODO, needs=["S-8c"], est=20),
          step("S-8e", "七张 Issue 关闭评论", False, 4, Status.TODO, needs=["S-8d"], est=20)]
    S += [step("S-9a", "环境盘点", False, 5, Status.TODO, needs=["S-8e"], est=10),
          step("S-9b", "任务表回写", False, 5, Status.TODO, needs=["S-9a"], est=10),
          step("S-9c", "收口评论与关闭", False, 5, Status.TODO, needs=["S-9b"], est=15)]
    by = {}
    for sv in S:
        by.setdefault(sv.step.section, []).append(sv)
    M = [
        module(0, "块 A", Status.DONE, Tier.NONE, 1, 1, rounds(), "评论 1 · 最新 13:55", actual=5, steps=by[0]),
        module(1, "Wave 0", Status.DONEQ, Tier.ONE, 2, 2, rounds(review=1, green=1), "评论 3 · 最新 14:20", needs=[0], actual=71, est=75, steps=by[1]),
        module(2, "Wave 1（实施；各自 worktree，改完先 commit 再汇报）", Status.STALLED, Tier.TWO, 1, 6, rounds(review=2, external=1, fixpack=1, red=1, green=4),
               "PR #19 MERGED · 评论 6 · 最新 13:48", needs=[1], elapsed=130, est=450, steps=by[2]),
        module(3, "Wave 2（集成、批终链）", Status.TODO, Tier.THREE, 0, 4, rounds(review=3, external=2, fixpack=1, green=2), "无", needs=[2], est=145, steps=by[3]),
        module(4, "Wave 3（试穿与收口 PR）", Status.TODO, Tier.MORE, 0, 5, rounds(review=5, external=2, fixpack=2, red=2, green=6), "无", needs=[3], est=115, steps=by[4]),
        module(5, "收口", Status.TODO, Tier.NONE, 0, 3, rounds(), "无", needs=[4], est=35, steps=by[5]),
    ]
    h = header("Trace #17 · batch/17-board", "Executing · Wave 1（5/21 步骤完成）", "S-5 95 分钟无外部证据；S-4 70 分钟观察",
               "S-6 等 S-2 / S-3 / S-4 / S-5 · 编排窗口 1 · worktree 5 · 窗口状态未知，需元守护核",
               "自述未证 1（W0-2）· 合同 PR #18 由发起人自合、零批准", "12 分钟前 · commit 8c58a7（S-2）", warnings=["未解析 1 行", "超限 2 行"])
    whys = [why("阶段 merged", "否", EvidenceType.PR_STATE, "gh.prs", "OPEN"), why("阶段 closed", "否", EvidenceType.ISSUE_STATE, "gh.issue", "OPEN")]
    return Board(h, S, M, NOW, whys)


BOARDS = {"simple": board_simple, "complex": board_complex, "tiers": board_tiers, "unknown": board_unknown, "six": board_six}


def fake_build(name="six", delay=0.0, fail="none"):
    """假 build()：`delay` 每轮睡眠秒数；`fail` ∈ none / exception（每轮抛）/ exception-once（首轮抛）/ timeout（首轮睡 delay 秒，之后正常）。
    返回的 board 标题带轮次号「第 N 轮」，便于测试观察刷新是否发生；`build.calls[0]` 是调用次数。"""
    factory = BOARDS[name]
    calls = [0]

    def build():
        calls[0] += 1
        n = calls[0]
        if fail == "exception" or (fail == "exception-once" and n == 1):
            raise RuntimeError("注入异常 #%d" % n)
        if fail == "timeout":
            if n == 1:
                time.sleep(delay)
        elif delay:
            time.sleep(delay)
        b = factory()
        b.header.title = "%s · 第 %d 轮" % (b.header.title, n)
        return b

    build.calls = calls
    return build
