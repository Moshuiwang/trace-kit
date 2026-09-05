# -*- coding: utf-8 -*-
"""状态推断单测（接口约定 §7；合成快照，零网络）。账本 F-1 条目各有用例（见类名 / 用例名括号里的编号）。"""
import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "plugin", "scripts"))

from boardlib import infer, registry, tasktable  # noqa: E402
from boardlib.model import EvidenceType as E, Grade, ProviderResult, Snapshot, Status, Tier  # noqa: E402

NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
T0 = NOW - timedelta(hours=6)  # Trace 起点


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def ago(minutes):
    return NOW - timedelta(minutes=minutes)


def ok(key, value, grade=Grade.MEASURED, fetched=NOW):
    return ProviderResult(key, True, value, "", "<test>", fetched, grade)


def bad(key, error="命令不可用：gh"):
    return ProviderResult(key, False, None, error, "<test>", NOW)


def commit(sha, at, subject, refs="", docs_only=False):
    return {"sha": sha, "at": iso(at), "committed": iso(at), "author": "t", "subject": subject, "refs": refs, "docs_only": docs_only, "files_n": 1}


def log(*commits, mode="branch", truncated=False):
    return {"mode": mode, "refs": ["batch/7-x"] if mode == "branch" else [], "truncated": truncated, "commits": list(commits)}


def pr(number, title, created, merged=None, head="feat/x", author="a", merged_by=None, reviews=(), body="", draft=False, merge_commit="", head_oid=""):
    return {
        "number": number, "title": title, "state": "MERGED" if merged else "OPEN", "isDraft": draft, "createdAt": iso(created),
        "mergedAt": iso(merged) if merged else "", "closedAt": iso(merged) if merged else "", "mergedBy": merged_by or "",
        "author": author, "reviews": [{"state": r, "author": "r", "submittedAt": ""} for r in reviews], "headRefName": head,
        "head_oid": head_oid, "baseRefName": "main", "mergeCommit": merge_commit, "url": "", "body": body, "checks": [],
    }


def issue(comments=(), state="OPEN", closed=None, created=T0):
    return {"number": 7, "title": "t", "state": state, "createdAt": iso(created), "closedAt": iso(closed) if closed else "", "url": "",
            "comments": [{"id": i + 1, "createdAt": iso(at), "author": "a", "first_line": line, "url": ""} for i, (at, line) in enumerate(comments)]}


def run(at, conclusion, branch="feat/x", sha="", name="ci", updated=None):
    return {"id": 1, "name": name, "workflowName": name, "conclusion": conclusion, "status": "completed", "createdAt": iso(at),
            "updatedAt": iso(updated or at), "headSha": sha, "headBranch": branch, "event": "push", "url": ""}


def history(*entries):
    return {"path": "docs/traces/7-demo/任务表.md", "commits": [{"sha": sha, "at": iso(at), "ids": ids, "checked": checked, "quotes": quotes}
                                                                for sha, at, ids, checked, quotes in entries]}


BASE_TABLE = "## W0\n- [x] S-0 合同\n## W1\n- [ ] S-1 实现\n- [ ] S-2 测试\n- [ ] S-3 审核 [t:review]\n## W2\n- [ ] S-4 人工闸 [t:human]\n"
BATCH = "batch/7-x"
TIP = "b" * 40


def snap(table=BASE_TABLE, results=None, branch=BATCH, now=NOW, config=None):
    tt = tasktable.parse(table, "docs/traces/7-demo/任务表.md")
    res = {
        "git.log": ok("git.log", log()),
        "git.tasktable_history": ok("git.tasktable_history", history(("aaaaaaa", T0, ["S-0", "S-1", "S-2", "S-3", "S-4"], ["S-0"], [])), Grade.INFERRED),
        "git.worktrees": ok("git.worktrees", []),
        "git.tags": ok("git.tags", []),
        "git.branches": ok("git.branches", [{"name": branch, "sha": TIP, "at": iso(NOW)}] if branch else []),
        "git.contract": ok("git.contract", None),
        "tasktable.quotes": ok("tasktable.quotes", [], Grade.REPORTED),
        "gh.prs": ok("gh.prs", []),
        "gh.issue": ok("gh.issue", issue()),
        "gh.runs": ok("gh.runs", []),
        "gh.release_runs": bad("gh.release_runs", "未配置发布工作流"),
        "gh.tags": ok("gh.tags", []),
        "gh.compare": bad("gh.compare", "无已证实的合并点（批次 PR 未合入或未识别）"),
        "tmux.windows": bad("tmux.windows", "未配置编排 session"),
    }
    res.update(results or {})
    return Snapshot(now=now, repo="o/r", trace_no=7, trace_dir="docs/traces/7-demo", branch=branch, tasktable=tt, results=res, config=config or {})


def board_of(**kw):
    conf = kw.pop("conf", types.SimpleNamespace())
    return infer.infer(snap(**kw), conf)


def view(board, sid):
    return next(v for v in board.steps if v.step.id == sid)


def stage(board, key):
    return {s.key: s for s in board.header.stages}[key]


def batch_pr(merged=True, head_oid=TIP, **kw):
    return pr(9, "batch", ago(120), ago(60) if merged else None, head=BATCH, merged_by="a", merge_commit="m" * 40, head_oid=head_oid, **kw)


class StepStatusTest(unittest.TestCase):
    def test_module_lives_in_this_tree(self):
        self.assertTrue(os.path.abspath(infer.__file__).startswith(ROOT))

    def test_done_with_merged_pr_pointer(self):
        table = "## W1\n- [x] S-1 实现 — PR #3 合入\n"
        b = board_of(table=table, results={"gh.prs": ok("gh.prs", [pr(3, "x", ago(50), ago(40), author="a", merged_by="a")])})
        v = view(b, "S-1")
        self.assertEqual(v.status, Status.DONE)
        self.assertEqual(v.chip, "PR #3 ✓合入 · 自合")
        self.assertEqual(v.chip_status, Status.DONE)
        self.assertEqual(v.actual_min, 10)

    def test_done_with_commit_touching_repo(self):
        b = board_of(table="## W1\n- [x] S-1 实现\n", results={"git.log": ok("git.log", log(commit("c" * 40, ago(30), "feat: S-1 done")))})
        v = view(b, "S-1")
        self.assertEqual(v.status, Status.DONE)
        self.assertEqual(v.chip, "commit ccccccc ✓")

    def test_docs_only_commit_is_not_artifact(self):
        """A-2：只改 docs/traces/<n>/ 的勾选提交不算独立制品，只算活动证据（推）。"""
        b = board_of(table="## W1\n- [x] S-1 实现\n", results={"git.log": ok("git.log", log(commit("d" * 40, ago(30), "docs(#7): 任务表 S-1 勾选", docs_only=True)))})
        v = view(b, "S-1")
        self.assertEqual(v.status, Status.DONEQ)
        self.assertEqual(v.chip, "无制品 · 勾选提交 ddddddd")
        self.assertEqual(v.chip_status, Status.DONEQ)
        self.assertIn("自述未证 1实（S-1）", b.header.doubt)
        b2 = board_of(table="## W1\n- [ ] S-1 实现\n", results={"git.log": ok("git.log", log(commit("d" * 40, ago(30), "docs(#7): S-1 派发", docs_only=True)))})
        self.assertEqual(view(b2, "S-1").status, Status.RUNNING)  # 活动证据仍算

    def test_comment_mention_is_activity_not_artifact(self):
        """R1-2：评论首行提及 Step ID 只算活动证据；只有任务表指针指向的评论才是制品。"""
        table = "## W1\n- [x] S-1 实现\n- [x] S-2 测试 — [评论](https://x/issues/7#issuecomment-2)\n- [ ] S-3 审核\n"
        comments = [(ago(30), "S-1 尚未开始"), (ago(20), "收口评论"), (ago(10), "S-3 正在跑")]
        b = board_of(table=table, results={"gh.issue": ok("gh.issue", issue(comments))})
        self.assertEqual(view(b, "S-1").status, Status.DONEQ)
        self.assertEqual(view(b, "S-1").chip, "无制品 · 评论提及")
        self.assertEqual(view(b, "S-2").status, Status.DONE)
        self.assertEqual(view(b, "S-3").status, Status.RUNNING)

    def test_id_word_boundary(self):
        table = "## W1\n- [x] S-1 a\n- [x] S-1a b\n- [x] S-1-1 c\n"
        b = board_of(table=table, results={"git.log": ok("git.log", log(commit("1" * 40, ago(30), "feat: S-1a and S-1-1 only")))})
        self.assertEqual(view(b, "S-1").status, Status.DONEQ)
        self.assertEqual(view(b, "S-1a").status, Status.DONE)
        self.assertEqual(view(b, "S-1-1").status, Status.DONE)
        b2 = board_of(table="## W1\n- [ ] S-2 a\n", results={"git.log": ok("git.log", log(commit("2" * 40, ago(10), "wip", refs="wt/17-S-2")))})
        self.assertEqual(view(b2, "S-2").status, Status.RUNNING)

    def test_doneq_without_artifact(self):
        b = board_of(table="## W1\n- [x] S-1 实现\n")
        v = view(b, "S-1")
        self.assertEqual(v.status, Status.DONEQ)
        self.assertEqual(v.chip, "无 commit · 无 PR")
        self.assertIsNone(v.started)
        self.assertTrue(v.why[0].value.startswith(registry.STATUS_RULE[Status.DONEQ]))  # R1-24：登记表与推断共用规则句

    def test_human(self):
        self.assertEqual(view(board_of(), "S-4").status, Status.HUMAN)

    def test_running_watch_stalled_by_age(self):
        for minutes, want in ((30, Status.RUNNING), (75, Status.WATCH), (120, Status.STALLED)):
            b = board_of(table="## W1\n- [ ] S-1 实现\n", results={"git.log": ok("git.log", log(commit("d" * 40, ago(minutes), "S-1 wip")))})
            self.assertEqual(view(b, "S-1").status, want, minutes)
            self.assertEqual(view(b, "S-1").elapsed_min, minutes)
        b = board_of(table="## W1\n- [ ] S-1 实现\n", results={"git.log": ok("git.log", log(commit("d" * 40, ago(120), "S-1 wip")))})
        self.assertIn("S-1 120实 分钟无证据", b.header.block)

    def test_ci_freshness_uses_updated_at(self):
        """R1-19：CI 新鲜度用结论时刻 updatedAt，不用 createdAt。"""
        prs = [pr(5, "S-1 impl", ago(200), head="feat/x")]
        runs = [run(ago(130), "success", updated=ago(20))]
        b = board_of(table="## W1\n- [ ] S-1 实现 — PR #5\n", results={"gh.prs": ok("gh.prs", prs), "gh.runs": ok("gh.runs", runs)})
        self.assertEqual(view(b, "S-1").status, Status.RUNNING)

    def test_worktree_evidence(self):
        wt = [{"name": "S-1", "head": "e" * 40, "branch": "wt/7-S-1", "main": False, "last_at": iso(ago(5)), "last_subject": "x", "ahead": 2, "dirty": 0, "files": [], "error": ""}]
        b = board_of(table="## W1\n- [ ] S-1 实现\n", results={"git.worktrees": ok("git.worktrees", wt)})
        self.assertEqual(view(b, "S-1").status, Status.RUNNING)
        self.assertTrue(view(b, "S-1").chip.startswith("wt S-1"))

    def test_ready_needs_dep_status_done_or_doneq(self):
        """R1-6：依赖满足看依赖状态 ∈ {完成, 自述未证}；依赖不存在 / 成环 → 未知＋告警。"""
        b = board_of()
        self.assertEqual(view(b, "S-1").status, Status.READY)  # S-0 自述未证 → 视为满足（现场裁定）
        self.assertEqual(view(b, "S-2").status, Status.TODO)
        self.assertEqual(b.header.nxt, "S-1 实现（下一步） · worktree 0实")
        b2 = board_of(table="## W1\n- [ ] S-1 a [needs:S-404]\n- [ ] S-2 b [needs:S-3]\n- [ ] S-3 c [needs:S-2]\n")
        self.assertEqual(view(b2, "S-1").status, Status.UNKNOWN)
        self.assertEqual(view(b2, "S-2").status, Status.UNKNOWN)
        self.assertEqual(view(b2, "S-3").status, Status.UNKNOWN)
        self.assertTrue(any(w.startswith("依赖不存在：S-1 → S-404") for w in b2.header.warnings))
        self.assertTrue(any(w.startswith("依赖成环") for w in b2.header.warnings))
        self.assertFalse(view(b2, "S-1").why[0].available)

    def test_stale_review_and_gate_even_when_checked(self):
        """K-2 / K-3 / R1-7：t:review 与 t:gate 带 SHA 的步骤（含已勾选）候选 ≠ HEAD → 失效；远端 head 优先。"""
        table = "## W1\n- [ ] S-3 审核 — 候选 `abc1234` [t:review]\n- [x] G-1 门禁 — 候选 `abc1234` [t:gate]\n- [x] S-5 实施 — 候选 `abc1234`\n"
        b = board_of(table=table)
        self.assertEqual(view(b, "S-3").status, Status.STALE)
        self.assertEqual(view(b, "G-1").status, Status.STALE)
        self.assertTrue(view(b, "G-1").rework)
        self.assertIn("已勾选但候选已变", view(b, "G-1").why[0].value)
        self.assertEqual(view(b, "S-5").status, Status.DONEQ)  # impl 类型不比对 SHA
        self.assertTrue(view(b, "S-3").chip.startswith("候选 abc123"))
        self.assertIn("审核结论失效 S-3/G-1", b.header.block)
        b2 = board_of(table="## W1\n- [ ] S-3 审核 — 候选 `bbbbbbb` [t:review]\n")
        self.assertEqual(view(b2, "S-3").status, Status.READY)
        # 远端 head OID 优先于本地分支：本地说变了，远端说没变 → 不失效
        prs = [batch_pr(merged=False, head_oid="abc1234" + "0" * 33)]
        b3 = board_of(table="## W1\n- [ ] S-3 审核 — 候选 `abc1234` [t:review]\n", results={"gh.prs": ok("gh.prs", prs)})
        self.assertEqual(view(b3, "S-3").status, Status.READY)
        self.assertEqual(view(b3, "S-3").why[0].source, "任务表")

    def test_stale_unknown_when_no_head(self):
        """R1-7：远端 head 与本地分支都不可得 → 带 SHA 的 review 步骤未知。"""
        b = board_of(table="## W1\n- [ ] S-3 审核 — 候选 `abc1234` [t:review]\n- [x] R-2 复核 — 候选 `abc1234` [t:review]\n",
                     results={"git.branches": bad("git.branches", "命令不可用：git")})
        self.assertEqual(view(b, "S-3").status, Status.UNKNOWN)
        self.assertEqual(view(b, "R-2").status, Status.UNKNOWN)
        self.assertEqual(view(b, "S-3").why[0].evidence, E.SHA_EQUAL)
        self.assertTrue(any(w.source == "git.branches" and not w.available for w in view(b, "S-3").why))

    def test_now_before_first_check_is_unchecked(self):
        hist = history(("aaaaaaa", NOW + timedelta(hours=1), ["S-1"], ["S-1"], []))
        b = board_of(table="## W1\n- [x] S-1 实现\n", results={"git.tasktable_history": ok("git.tasktable_history", hist, Grade.INFERRED)})
        self.assertEqual(view(b, "S-1").status, Status.READY)

    def test_replay_before_recording_without_history_is_unknown(self):
        """R1-9：--now 早于采集时刻且任务表历史不可得 → 依赖复选框的结论未知。"""
        res = {"git.tasktable_history": bad("git.tasktable_history", "超时 25s"), "gh.prs": ok("gh.prs", [], fetched=NOW + timedelta(hours=2))}
        b = board_of(table="## W1\n- [x] S-1 实现 — PR #3 合入\n- [ ] S-2 测试\n", results=res)
        self.assertEqual(view(b, "S-1").status, Status.UNKNOWN)
        self.assertEqual(view(b, "S-2").status, Status.UNKNOWN)
        self.assertIn("复选框真值未知", view(b, "S-1").why[0].value)


class UnknownTest(unittest.TestCase):
    """证据不可得 → 未知，不回落（https://github.com/Moshuiwang/lingxi/issues/579）。"""

    GH_DOWN = {"gh.prs": bad("gh.prs", "命令不可用：gh"), "gh.issue": bad("gh.issue", "命令不可用：gh"), "gh.runs": bad("gh.runs", "命令不可用：gh"),
               "gh.tags": bad("gh.tags", "命令不可用：gh")}

    def test_gh_unavailable_everything_unknown_not_todo(self):
        b = board_of(results=self.GH_DOWN)
        for sid in ("S-0", "S-1", "S-2"):
            self.assertEqual(view(b, sid).status, Status.UNKNOWN, sid)
        self.assertEqual(view(b, "S-4").status, Status.HUMAN)  # 标签判定不依赖 gh
        self.assertEqual(view(b, "S-1").chip, "证据未知")
        self.assertFalse(stage(b, "merged").value.available)
        self.assertFalse(stage(b, "published").value.available)  # R1-12：无已证实的合并点 → 未知
        self.assertFalse(stage(b, "closed").value.available)
        self.assertTrue(b.header.stage.startswith("未知（收口证据"))  # R1-15：不显示「执行中」
        self.assertIn("阶段未知：合入主干 / 已发布 / 收口", b.header.block)
        m = b.modules[1]
        self.assertEqual(m.status, Status.UNKNOWN)
        self.assertFalse(m.rounds.review.available)
        self.assertEqual(m.tier, Tier.NONE)  # R1-16
        self.assertIn("未知", m.rounds_line)
        self.assertIn("PR 未知", m.evidence_line)
        self.assertIn("PR 存疑未知", b.header.doubt)
        self.assertTrue(any(w.startswith("gh.prs 不可得：命令不可用") for w in b.header.warnings))
        # R1-23：每个不可得依赖各一行、EvidenceType 按键，来源只写键
        rows = {w.source: w for w in view(b, "S-1").why if not w.available}
        self.assertEqual({rows["gh.prs"].evidence, rows["gh.issue"].evidence, rows["gh.runs"].evidence}, {E.PR_STATE, E.COMMENT_TITLE, E.CI_CONCLUSION})
        self.assertEqual(view(b, "S-1").why[0].evidence, E.PR_STATE)
        self.assertEqual(view(b, "S-1").why[0].status, "未知")

    def test_fresh_git_evidence_still_running_when_gh_down(self):
        res = dict(self.GH_DOWN)
        res["git.log"] = ok("git.log", log(commit("f" * 40, ago(10), "S-1 wip"), commit("e" * 40, ago(200), "S-2 wip")))
        b = board_of(results=res)
        self.assertEqual(view(b, "S-1").status, Status.RUNNING)
        self.assertEqual(view(b, "S-2").status, Status.UNKNOWN)  # 旧证据 + 键不可得，不能断言卡住

    def test_git_unavailable_too(self):
        res = {k: bad(k, "命令不可用：git") for k in ("git.log", "git.tasktable_history", "git.worktrees", "git.tags", "git.branches", "git.contract", "gh.prs", "gh.issue", "gh.runs", "gh.tags")}
        b = board_of(results=res)
        self.assertTrue(all(v.status in (Status.UNKNOWN, Status.HUMAN) for v in b.steps))
        self.assertTrue(all(not s.value.available for s in b.header.stages))
        self.assertEqual(b.header.evidence, "未知（git.log/gh.prs/gh.issue/gh.runs/git.worktrees 不可得）")

    def test_recorded_missing_key(self):
        b = board_of(results={"gh.prs": ProviderResult("gh.prs", False, None, "夹具未记录")})
        self.assertEqual(view(b, "S-1").status, Status.UNKNOWN)

    def test_tasktable_unavailable_all_unknown(self):
        """R1-8：任务表缺失 / 不可读 → 头部全部未知并告警，模块区为空。"""
        s = snap()
        s.tasktable.available = False
        s.tasktable.error = "任务表不可读：docs/traces/7-demo/任务表.md（FileNotFoundError）"
        s.tasktable.sections = []
        b = infer.infer(s, types.SimpleNamespace())
        self.assertEqual((b.steps, b.modules), ([], []))
        self.assertTrue(b.header.stage.startswith("未知（任务表不可得"))
        self.assertEqual(b.header.evidence, "未知（任务表不可得）")
        self.assertIn("任务表不可得", b.header.block)
        self.assertTrue(all(not st.value.available for st in b.header.stages))
        self.assertTrue(any(w.startswith("任务表不可得") for w in b.header.warnings))

    def test_config_error_only_category_in_why(self):
        """A-1：config.* 键的 Why 只写键与失败类别，绝不带 stderr。"""
        cfg = {"stages": [{"key": "production", "result_key": "config.production", "label": ""}],
               "budgets": [{"key": "gate", "result_key": "config.gate", "label": "门禁", "cap": 3}],
               "evidence": [{"key": "hosts", "result_key": "config.hosts", "label": "主机"}]}
        leak = "退出码 255：ssh: connect to host secret-host-01.example port 22: Connection refused"
        res = {"gh.prs": ok("gh.prs", [batch_pr()]), "gh.tags": ok("gh.tags", [{"name": "v1", "sha": "m" * 40, "at": ""}]),
               "config.production": bad("config.production", leak), "config.gate": bad("config.gate", "超时（20 秒）"), "config.hosts": bad("config.hosts", leak)}
        b = board_of(results=res, config=cfg)
        text = " ".join(w.value + w.source for w in b.why) + b.header.evidence + b.header.block + b.header.doubt
        self.assertNotIn("secret-host", text)
        self.assertNotIn("ssh", text)
        rows = {w.subject: w for w in b.why}
        self.assertEqual(rows["阶段·已上生产"].value, "config.production：退出码 255")
        self.assertEqual(rows["预算·门禁"].value, "config.gate：超时")
        self.assertIn("主机 未知（退出码 255）", b.header.evidence)
        self.assertEqual([(l, v.available, cap) for l, v, cap in b.header.budget], [("门禁", False, 3)])


class CommentWindowTest(unittest.TestCase):
    """§7.2 归属：首行含 Step ID → 该模块（实）；否则落在哪个模块活动窗口（推，重叠取最晚开始）；都不命中 → Trace 级。"""

    TABLE = "## W1\n- [x] S-1 a — PR #1 合入\n## W2\n- [x] S-2 b\n- [ ] S-3 c\n"

    def _res(self, comments):
        return {"gh.prs": ok("gh.prs", [pr(1, "S-1", ago(300), ago(280), merged_by="a")]),
                "git.log": ok("git.log", log(commit("2" * 40, ago(200), "S-2 done"), commit("3" * 40, ago(30), "S-3 wip"))),
                "gh.issue": ok("gh.issue", issue(comments))}

    def test_window_fallback_inferred(self):
        comments = [(ago(290), "## 审核①结论（首行无 Step）"), (ago(100), "## 修复包合入"), (ago(20), "## 定向复核②结论"), (ago(350), "## 审核③结论（W1 窗口之前）")]
        b = board_of(table=self.TABLE, results=self._res(comments))
        w1, w2 = b.modules
        self.assertEqual((w1.rounds.review.value, w1.rounds.review.grade), (1, Grade.INFERRED))
        self.assertEqual(w1.tier, Tier.ONE)
        self.assertEqual((w2.rounds.review.value, w2.rounds.fixpack.value), (1, 1))
        self.assertEqual(w2.rounds.review.grade, Grade.INFERRED)
        self.assertIn("推（落在窗口", next(w for w in w2.why if w.status == "轮数").value)
        self.assertIn("Trace 级 审 1实", b.header.stage)

    def test_explicit_beats_window_and_overlap_picks_latest_start(self):
        comments = [(ago(100), "## 审核①结论 S-1")]
        b = board_of(table=self.TABLE, results=self._res(comments))
        self.assertEqual((b.modules[0].rounds.review.value, b.modules[0].rounds.review.grade), (1, Grade.MEASURED))
        self.assertEqual(b.modules[1].rounds.review.value, 0)
        table = "## W1\n- [ ] S-1 a\n## W2\n- [ ] S-2 b\n"
        res = {"git.log": ok("git.log", log(commit("1" * 40, ago(200), "S-1 wip"), commit("2" * 40, ago(150), "S-2 wip"))),
               "gh.issue": ok("gh.issue", issue([(ago(100), "## 审核①结论")]))}
        b2 = board_of(table=table, results=res)
        self.assertEqual((b2.modules[0].rounds.review.value, b2.modules[1].rounds.review.value), (0, 1))

    def test_regex_whole_first_line_with_negation_and_fixpack_needs_result(self):
        """R1-3（r5 裁定）/ A-6：首行全文匹配，关键词前 6 字符内有否定词不计；「修」只计有结果；一条评论可同时计审＋外。"""
        comments = [
            (ago(50), "## 审核①结论 S-1"),                                                   # 审
            (ago(45), "## 这不是审核①结论，只是引用 codex 外审结论 S-1"),                       # 否定 / 引用 → 都不计
            (ago(44), "## 不算修复包合入，只是引用 agy 账本 S-1"),                                 # 不算 / 引用 → 都不计
            (ago(40), "## 修复包已派发（S-1）"),                                               # 派发类不计
            (ago(35), "> 修复包合入 S-1"),                                                    # 修
            (ago(30), "## 唯一缺陷账本：审核①（Fable）＋ codex ＋ agy 三路结论并入 S-1"),      # 肯定形态在首行中段 → 审＋外
            (ago(25), "## 复核②未出结论；外审取消 S-1"),                                       # 「未」在关键词后不算否定 → 审；外审前「取消」不在前 6 字符 → 但关键词后的「取消」不算 → 外无结论词 → 不计
        ]
        b = board_of(table="## W1\n- [ ] S-1 a\n", results={"gh.issue": ok("gh.issue", issue(comments))})
        m = b.modules[0]
        self.assertEqual((m.rounds.review.value, m.rounds.external.value, m.rounds.fixpack.value), (3, 1, 1))
        self.assertEqual(m.tier, Tier.THREE)
        self.assertEqual(m.rounds_line, "审 3实 · 外 1实 · 修 1实 · CI 红0推 绿0推")
        self.assertIn("评论 7实", m.evidence_line)
        self.assertEqual(infer._classify_comment("## 无审核①结论，取消 codex 外审的账本，不算修复包合入"), (False, False, False))
        # r6：审 类命中须同一首行含 结论 / 账本 / 复核结论——#606 真实首行「…前一轮（并行审核①真库变异时）唯一失败…」→ 0
        real = ("本机 full 补证（`ux-b1`，2026-09-05 13:13 北京）：对措辞修正后的候选（代码面＝`9692ace`，文档修正 `f1ce0a5`，任务表 `3aa3c8b`）"
                "复跑 `scripts/dev/check.sh full`，这次把 check.sh 退出码单独写进日志：**`Ran 5947 tests / OK`、`CHECK_EXIT=0`**，临时真库容器已清。"
                "前一轮（并行审核①真库变异时）唯一失败 `test_gateway_postgres` 已定位")
        self.assertEqual(infer._classify_comment(real)[0], False)
        self.assertEqual(infer._classify_comment("## 定向复核②：全部闭合")[0], False)
        self.assertEqual(infer._classify_comment("## 定向复核②复核结论：全部闭合")[0], True)
        self.assertEqual(infer._classify_comment("## 唯一缺陷账本：审核①（Fable）＋ codex ＋ agy 三路结论并入，编排者裁定"), (True, True, False))

    def test_ci_run_unique_attribution(self):
        """R1-5：CI run 唯一归属（headSha 提交 → PR 分支 → 最晚开始的重叠窗口），绝不重复计数。"""
        table = "## W1\n- [ ] S-1 a\n## W2\n- [ ] S-2 b\n"
        res = {"git.log": ok("git.log", log(commit("1" * 40, ago(200), "S-1 wip"), commit("2" * 40, ago(150), "S-2 wip"))),
               "gh.runs": ok("gh.runs", [run(ago(100), "failure", sha="1" * 40), run(ago(90), "success", sha="z" * 40), run(ago(80), "failure", sha="2" * 40)])}
        b = board_of(table=table, results=res)
        w1, w2 = b.modules
        self.assertEqual((w1.rounds.ci_red.value, w1.rounds.ci_green.value), (1, 0))   # headSha → S-1
        self.assertEqual((w2.rounds.ci_red.value, w2.rounds.ci_green.value), (1, 1))   # headSha → S-2；无归属 run 落最晚开始的 W2
        total = w1.rounds.ci_red.value + w1.rounds.ci_green.value + w2.rounds.ci_red.value + w2.rounds.ci_green.value
        self.assertEqual(total, 3)


class ModuleTest(unittest.TestCase):
    def test_aggregation_priority_and_first_line(self):
        """R1-20：第一行 `勾选 d/t`＋`未证 n`；ModuleView.done 只计完成。"""
        table = "## W1\n- [x] S-1 a — PR #1 合入\n- [x] S-2 x\n- [ ] S-3 c\n"
        res = {"gh.prs": ok("gh.prs", [pr(1, "S-1", ago(90), ago(80), merged_by="a")]),
               "git.log": ok("git.log", log(commit("2" * 40, ago(5), "S-3 wip")))}
        m = board_of(table=table, results=res).modules[0]
        self.assertEqual(m.status, Status.RUNNING)
        self.assertEqual((m.done, m.total), (1, 3))
        self.assertEqual(m.what, "W1 勾选 2/3 · 未证 1")
        all_done = board_of(table="## W1\n- [x] S-1 a — PR #1 合入\n", results={"gh.prs": res["gh.prs"]}).modules[0]
        self.assertEqual(all_done.status, Status.DONE)
        self.assertEqual(all_done.what, "W1 勾选 1/1")
        self.assertEqual(all_done.actual_min, 10)
        self.assertEqual(board_of(table="## W1\n- [ ] S-1 a\n- [ ] S-2 b [t:human]\n").modules[0].status, Status.HUMAN)

    def test_empty_and_unparsed_sections(self):
        """A-3：章节无可解析步骤但有未解析行 → 未知＋「N 行未解析」；完全为空 → `—`。"""
        b = board_of(table="## 块 A\n- [x] A-1…A-6 已给齐\n## 空\n## W1\n- [ ] S-1 a\n- [ ] 无编号\n")
        a, empty, w1 = b.modules
        self.assertEqual(a.status, Status.UNKNOWN)
        self.assertEqual(a.what, "块 A ?/?（未解析 1 行）")
        self.assertEqual(empty.what, "空 —")
        self.assertEqual(w1.what, "W1 勾选 0/1 · 未解析 1 行")
        self.assertEqual(b.unparsed, [(2, "- [x] A-1…A-6 已给齐"), (6, "- [ ] 无编号")])
        self.assertIn("任务表未解析 2实 行", b.header.warnings)

    def test_module_needs(self):
        table = "## A\n- [ ] S-1 a\n## B\n- [ ] S-2 b\n## C\n- [ ] S-3 c [needs:S-1]\n"
        self.assertEqual([m.needs for m in board_of(table=table).modules], [[], [0], [0]])

    def test_tier_table(self):
        for n, want in ((0, Tier.NONE), (1, Tier.ONE), (2, Tier.TWO), (3, Tier.THREE), (4, Tier.MORE), (9, Tier.MORE)):
            self.assertEqual(infer._tier(n), want)


class StageTest(unittest.TestCase):
    def test_merged_only_unique_batch_pr(self):
        """R1-11 / N-3：唯一批次 PR；无批次分支 → 合入主干「不适用」、已发布「不适用」（不进阻塞）。"""
        b = board_of(results={"gh.prs": ok("gh.prs", [batch_pr()])})
        self.assertIs(stage(b, "merged").value.value, True)
        self.assertTrue(b.header.stage.startswith("已合入主干"))
        b2 = board_of(results={"gh.prs": ok("gh.prs", [pr(1, "S-1 kickoff", ago(300), ago(290), head="trace/7-kickoff", merged_by="a")])})
        self.assertIs(stage(b2, "merged").value.value, False)
        self.assertEqual(stage(b2, "merged").value.grade, Grade.MEASURED)
        b3 = board_of(branch="", results={"gh.prs": ok("gh.prs", [pr(1, "S-1 kickoff", ago(300), ago(290), head="trace/7-kickoff", merged_by="a")])})
        self.assertFalse(stage(b3, "merged").configured)
        pub = stage(b3, "published").value
        self.assertTrue(pub.available)
        self.assertIs(pub.value, False)
        self.assertEqual(getattr(pub, "note", ""), "不适用")
        self.assertNotIn("阶段未知", b3.header.block)
        self.assertTrue(b3.header.stage.startswith("执行中"))

    def test_batch_pr_identity_rules_h1(self):
        """H-1：同分支多 PR——①恰一 MERGED；②多 MERGED 取最早合并；③无 MERGED 取最早创建的 OPEN；④全部关闭未合并 → 未知。"""
        m608 = dict(batch_pr(), number=608)
        o610 = dict(batch_pr(merged=False), number=610, createdAt=iso(ago(10)))
        b1 = board_of(results={"gh.prs": ok("gh.prs", [m608, o610])})
        self.assertIs(stage(b1, "merged").value.value, True)
        self.assertEqual(stage(b1, "merged").value.grade, Grade.INFERRED)
        self.assertIn("另有 PR #610 开放", b1.header.doubt)
        w = next(w for w in b1.why if w.subject == "阶段·合入主干")
        self.assertIn("批次 PR #608", w.value)
        self.assertIn("规则①", w.value)
        # 已发布按 #608 合并点判定
        b1b = board_of(results={"gh.prs": ok("gh.prs", [m608, o610]), "gh.tags": ok("gh.tags", [{"name": "v1", "sha": "m" * 40, "at": ""}])})
        self.assertIs(stage(b1b, "published").value.value, True)
        early = dict(batch_pr(), number=1, mergedAt=iso(ago(200)), mergeCommit="e" * 40)
        late = dict(batch_pr(), number=2)
        b2 = board_of(results={"gh.prs": ok("gh.prs", [late, early])})
        self.assertIs(stage(b2, "merged").value.value, True)
        self.assertIn("批次 PR #1", next(w for w in b2.why if w.subject == "阶段·合入主干").value)
        self.assertIn("规则②", next(w for w in b2.why if w.subject == "阶段·合入主干").value)
        self.assertIn("另有 PR #2 已合入", b2.header.doubt)
        o_old = dict(batch_pr(merged=False), number=3, createdAt=iso(ago(300)))
        o_new = dict(batch_pr(merged=False), number=4, createdAt=iso(ago(20)))
        b3 = board_of(results={"gh.prs": ok("gh.prs", [o_new, o_old])})
        self.assertIs(stage(b3, "merged").value.value, False)
        self.assertIn("批次 PR #3 OPEN", next(w for w in b3.why if w.subject == "阶段·合入主干").value)
        self.assertIn("规则③", next(w for w in b3.why if w.subject == "阶段·合入主干").value)
        self.assertIn("另有 PR #4 开放", b3.header.doubt)
        closed = [dict(batch_pr(merged=False), number=5, state="CLOSED", closedAt=iso(ago(30))), dict(batch_pr(merged=False), number=6, state="CLOSED", closedAt=iso(ago(20)))]
        b4 = board_of(results={"gh.prs": ok("gh.prs", closed)})
        self.assertFalse(stage(b4, "merged").value.available)
        self.assertIn("规则④", next(w for w in b4.why if w.subject == "阶段·合入主干").value)
        self.assertIn("阶段未知：合入主干", b4.header.block)

    def test_published_requires_merge_point_and_never_contradicts_merged(self):
        """R1-12：已发布须有已证实的合并点；绝不「合入 否 · 已发布 是」。"""
        tags = [{"name": "v1.0.0", "sha": "x" * 40, "at": iso(ago(30))}]
        b = board_of(results={"gh.prs": ok("gh.prs", [batch_pr(merged=False)]), "gh.tags": ok("gh.tags", tags)})
        self.assertIs(stage(b, "merged").value.value, False)
        self.assertIs(stage(b, "published").value.value, False)
        b2 = board_of(results={"gh.prs": bad("gh.prs"), "gh.tags": ok("gh.tags", tags)})
        self.assertFalse(stage(b2, "published").value.available)
        for b_ in (b, b2):
            self.assertFalse(stage(b_, "published").value.available and stage(b_, "published").value.value and not stage(b_, "merged").value.value)

    def test_published_tag_via_compare_time_and_gh_tags_authority(self):
        """R1-13 / gh.tags 权威：祖先关系优先 gh.compare；不可得按时间判（推）；gh.tags 不可得 → 未知。"""
        base = {"gh.prs": ok("gh.prs", [batch_pr()])}
        b = board_of(results=dict(base, **{"gh.tags": ok("gh.tags", [{"name": "v1", "sha": "m" * 40, "at": ""}])}))
        self.assertIs(stage(b, "published").value.value, True)
        self.assertEqual(stage(b, "published").value.grade, Grade.MEASURED)
        cmp_ok = ok("gh.compare", {"base": "m" * 40, "results": {"y" * 40: "ahead", "z" * 40: "behind"}})
        b2 = board_of(results=dict(base, **{"gh.tags": ok("gh.tags", [{"name": "v2", "sha": "z" * 40, "at": iso(ago(10))}, {"name": "v1", "sha": "y" * 40, "at": ""}]), "gh.compare": cmp_ok}))
        self.assertIs(stage(b2, "published").value.value, True)
        self.assertEqual(stage(b2, "published").value.grade, Grade.MEASURED)
        self.assertIn("v1 → yyyyyyy", next(w for w in b2.why if w.subject == "阶段·已发布").value)
        b3 = board_of(results=dict(base, **{"gh.tags": ok("gh.tags", [{"name": "v1", "sha": "q" * 40, "at": iso(ago(30))}])}))
        self.assertIs(stage(b3, "published").value.value, True)
        self.assertEqual(stage(b3, "published").value.grade, Grade.INFERRED)
        self.assertIn("按时间判", next(w for w in b3.why if w.subject == "阶段·已发布").value)
        b4 = board_of(results=dict(base, **{"gh.tags": bad("gh.tags", "命令不可用：gh"),
                                            "git.tags": ok("git.tags", [{"name": "v1", "at": iso(ago(30)), "object": "t" * 40, "commit": "m" * 40}])}))
        self.assertFalse(stage(b4, "published").value.available)
        b5 = board_of(results=dict(base, **{"gh.tags": ok("gh.tags", [{"name": "v0", "sha": "o" * 40, "at": iso(ago(500))}])}))
        self.assertIs(stage(b5, "published").value.value, False)

    def test_release_run_head_must_descend_from_merge(self):
        cfg = {"release_workflow": "Publish"}
        base = {"gh.prs": ok("gh.prs", [batch_pr()]), "gh.tags": ok("gh.tags", [{"name": "v1.0.0", "sha": "m" * 40, "at": ""}])}
        good = dict(base, **{"gh.release_runs": ok("gh.release_runs", [run(ago(55), "success", "main", "m" * 40, "Publish")])})
        self.assertIs(stage(board_of(results=good, config=cfg), "published").value.value, True)
        stray = dict(base, **{"gh.release_runs": ok("gh.release_runs", [run(ago(55), "success", "main", "z" * 40, "Publish")])})
        self.assertIs(stage(board_of(results=stray, config=cfg), "published").value.value, False)
        no_tag = dict(good, **{"gh.tags": ok("gh.tags", [])})
        b = board_of(results=no_tag, config=cfg)
        self.assertIs(stage(b, "published").value.value, False)
        self.assertIn("无合并后的 tag", next(w for w in b.why if w.subject == "阶段·已发布").value)
        down = dict(base, **{"gh.release_runs": bad("gh.release_runs", "超时 25s")})
        self.assertFalse(stage(board_of(results=down, config=cfg), "published").value.available)

    def test_staging_production_not_yet_published_n1(self):
        """N-1：已发布已知为「否」→ 预发 / 生产显示「尚未发布」（value=False＋note），不进阻塞；真不可得才未知。"""
        cfg = {"stages": [{"key": "staging", "result_key": "config.staging", "label": ""}, {"key": "production", "result_key": "config.production", "label": ""}]}
        res = {"gh.prs": ok("gh.prs", [batch_pr()]), "gh.tags": ok("gh.tags", []), "config.staging": ok("config.staging", "v1"), "config.production": bad("config.production", "超时")}
        b = board_of(results=res, config=cfg)
        self.assertIs(stage(b, "published").value.value, False)
        for key in ("staging", "production"):
            v = stage(b, key).value
            self.assertTrue(v.available)
            self.assertIs(v.value, False)
            self.assertEqual(getattr(v, "note", ""), "尚未发布")
        self.assertEqual(b.header.block, "无")
        self.assertIn("尚未发布", next(w for w in b.why if w.subject == "阶段·已上生产").value)

    def test_staging_production_follow_published(self):
        """R1-14：已发布未知 → 预发 / 生产一律未知；已发布可得时按配置命令比对。"""
        cfg = {"stages": [{"key": "staging", "result_key": "config.staging", "label": ""}, {"key": "production", "result_key": "config.production", "label": ""}]}
        base = {"gh.prs": ok("gh.prs", [batch_pr()]), "gh.tags": ok("gh.tags", [{"name": "v1.0.0", "sha": "m" * 40, "at": ""}]),
                "config.staging": ok("config.staging", "v1.0.0\n"), "config.production": bad("config.production", "远端命令超时")}
        b = board_of(results=base, config=cfg)
        self.assertIs(stage(b, "staging").value.value, True)
        self.assertFalse(stage(b, "production").value.available)
        self.assertIn("阶段未知：已上生产", b.header.block)
        res2 = dict(base, **{"config.production": ok("config.production", "v1.0.0")})
        b2 = board_of(results=res2, config=cfg)
        self.assertTrue(b2.header.stage.startswith("已上生产"))
        self.assertTrue(b2.header.nxt.startswith("观察与收口"))
        res3 = dict(res2, **{"gh.tags": bad("gh.tags", "命令不可用：gh")})
        b3 = board_of(results=res3, config=cfg)
        self.assertFalse(stage(b3, "published").value.available)
        self.assertFalse(stage(b3, "staging").value.available)
        self.assertFalse(stage(b3, "production").value.available)
        self.assertIn("已发布未知 → 本级未知", next(w for w in b3.why if w.subject == "阶段·已上生产").value)

    def test_closed(self):
        b = board_of(results={"gh.prs": ok("gh.prs", [batch_pr()]), "gh.issue": ok("gh.issue", issue(state="CLOSED", closed=ago(10)))})
        self.assertTrue(stage(b, "closed").value.value)
        self.assertTrue(b.header.stage.startswith("已收口"))
        self.assertEqual(b.header.nxt, "无（Trace 已关闭）")


class HeaderTest(unittest.TestCase):
    def test_contract_pr_self_merged_zero_approval(self):
        table = "## W0\n- [x] S-0 合同 — PR #2 合入\n"
        prs = [pr(2, "合同", ago(300), ago(290), head="trace/7-kickoff", author="bot", merged_by="bot", merge_commit="a" * 40)]
        res = {"gh.prs": ok("gh.prs", prs), "git.contract": ok("git.contract", {"sha": "a" * 40, "at": iso(ago(290)), "subject": "docs (#2)", "path": "x"})}
        b = board_of(table=table, results=res)
        v = view(b, "S-0")
        self.assertEqual(v.status, Status.DONE)
        self.assertEqual(v.chip, "PR #2 ✓合入 · 自合 · 零批准")
        self.assertEqual(v.chip_status, Status.DONEQ)
        self.assertIn("合同 PR #2 自合/零批准", b.header.doubt)
        self.assertIn("PR 自合 1/1实 零批准", b.header.doubt)
        prs2 = [pr(2, "合同", ago(300), ago(290), head="trace/7-kickoff", author="bot", merged_by="pm", reviews=("APPROVED",), merge_commit="a" * 40)]
        b2 = board_of(table=table, results=dict(res, **{"gh.prs": ok("gh.prs", prs2)}))
        self.assertEqual(view(b2, "S-0").chip, "PR #2 ✓合入 · 批准")
        self.assertNotIn("合同 PR", b2.header.doubt)

    def test_shared_pr_and_body_fallback(self):
        table = "## W1\n- [x] S-1 a — PR #5 合入\n- [x] S-2 b\n- [x] S-3 c\n"
        prs = [pr(5, "feat: S-1 / S-2", ago(50), ago(40), merged_by="a", body="also mentions S-3")]
        b = board_of(table=table, results={"gh.prs": ok("gh.prs", prs)})
        self.assertEqual(view(b, "S-2").status, Status.DONE)
        self.assertEqual(view(b, "S-3").status, Status.DONEQ)
        self.assertIn("共用 PR #5", b.header.doubt)
        self.assertIn("#5（S-1/S-2）", next(w for w in b.why if w.subject == "共用 PR").value)
        prs2 = [pr(6, "no id in title", ago(50), ago(40), merged_by="a", body="Trace：#7（S-3）")]
        self.assertEqual(view(board_of(table="## W1\n- [x] S-3 c\n", results={"gh.prs": ok("gh.prs", prs2)}), "S-3").status, Status.DONE)

    def test_pause_interval_and_gap_in_doubt(self):
        table = "## W1\n- [x] S-1 a\n- [x] S-2 b\n"
        quote = "> **2026-09-05 06:1x UTC / 14:1x 北京：产品负责人指令优雅暂停**"
        hist = history(("a" * 7, ago(350), ["S-1", "S-2"], [], []), ("b" * 7, ago(300), ["S-1", "S-2"], ["S-1"], []),
                       ("c" * 7, ago(240), ["S-1", "S-2"], ["S-1"], [quote]), ("d" * 7, ago(30), ["S-1", "S-2"], ["S-1", "S-2"], [quote]))
        res = {"git.tasktable_history": ok("git.tasktable_history", hist, Grade.INFERRED),
               "git.log": ok("git.log", log(commit("1" * 40, ago(320), "S-1 done"), commit("2" * 40, ago(40), "S-2 done"))),
               "tasktable.quotes": ok("tasktable.quotes", [quote], Grade.REPORTED)}
        b = board_of(table=table, results=res)
        self.assertIn("空档 280推 分", b.header.doubt)
        self.assertIn("（暂停 200报）", b.header.doubt)
        self.assertEqual(b.header.block, "无")
        pause = next(w for w in b.why if w.subject == "暂停")
        self.assertEqual(pause.status, "200报 分钟")
        self.assertEqual(pause.source, "git.tasktable_history")
        self.assertIn("归因暂停 200报 分钟", next(w for w in b.why if w.subject == "空档").value)
        res2 = dict(res, **{"git.tasktable_history": bad("git.tasktable_history", "git 不可用")})
        self.assertEqual(next(w for w in board_of(table=table, results=res2).why if w.subject == "暂停").source, "tasktable.quotes")

    def test_block_only_current_items(self):
        table = "## W1\n- [x] S-1 a — PR #1 合入\n- [ ] S-2 b\n- [ ] S-3 r — `abc1234` [t:review]\n"
        res = {"gh.prs": ok("gh.prs", [pr(1, "S-1", ago(300), ago(280), head="feat/x", merged_by="a")]),
               "git.log": ok("git.log", log(commit("2" * 40, ago(200), "S-2 wip"))),
               "gh.runs": ok("gh.runs", [run(ago(250), "success"), run(ago(10), "failure", name="Epic Full")])}
        b = board_of(table=table, results=res)
        self.assertIn("S-2 200实 分钟无证据", b.header.block)
        self.assertIn("CI 红：Epic Full", b.header.block)
        self.assertIn("审核结论失效 S-3", b.header.block)
        self.assertNotIn("空档", b.header.block)
        self.assertIn("空档", b.header.doubt)

    def test_window_note_and_warnings(self):
        b = board_of(table="## W1\n- [ ] S-1 a\n- [ ] 无编号\n- [ ] S-2 " + "字" * 20 + "\n")
        self.assertIn(infer.WINDOW_NOTE, b.header.warnings)
        self.assertIn("任务表超限 1实 行", b.header.warnings)
        cfg = {"tmux_configured": True, "window_pattern": "^hb-b[0-9]+$"}
        b2 = board_of(results={"tmux.windows": ok("tmux.windows", ["guardian", "hb-b1"])}, config=cfg)
        self.assertNotIn(infer.WINDOW_NOTE, b2.header.warnings)
        self.assertTrue(any(w.subject == "编排窗口" and w.status == "存活" for w in b2.why))
        b3 = board_of(results={"tmux.windows": ok("tmux.windows", ["guardian"])}, config=cfg)
        self.assertIn("编排窗口不在", b3.header.block)

    def test_evidence_line_extra_rows_and_unknown_propagation(self):
        """R1-21：[[evidence]] 附加证据进「外部证据」行；依赖不可得逐项传播。"""
        cfg = {"evidence": [{"key": "healthy", "result_key": "config.healthy", "label": "生产 healthy"}, {"key": "hosts", "result_key": "config.hosts", "label": "主机"}]}
        res = {"git.log": ok("git.log", log(commit("1" * 40, ago(12), "S-1 wip"))), "config.healthy": ok("config.healthy", 3),
               "config.hosts": bad("config.hosts", "超时（20 秒）"), "gh.runs": bad("gh.runs", "命令不可用：gh")}
        b = board_of(results=res, config=cfg)
        self.assertIn("12实 分钟前 · commit 1111111（S-1）", b.header.evidence)
        self.assertIn("· 未知：gh.runs", b.header.evidence)
        self.assertIn("· 生产 healthy 3实", b.header.evidence)
        self.assertIn("· 主机 未知（超时）", b.header.evidence)
        rows = {w.subject: w for w in b.why}
        self.assertEqual((rows["外部证据·生产 healthy"].source, rows["外部证据·主机"].available), ("config.healthy", False))

    def test_git_log_mode_all_warns(self):
        """R1-1：找不到分支回落 --all → 角标推＋告警；触顶 → 告警。"""
        b = board_of(branch="", results={"git.log": ok("git.log", log(commit("1" * 40, ago(12), "S-1 wip"), mode="all", truncated=True), Grade.INFERRED)})
        self.assertTrue(any(w.startswith("证据可能串线") for w in b.header.warnings))
        self.assertTrue(any(w.startswith("git.log 触顶") for w in b.header.warnings))
        self.assertEqual(view(b, "S-1").status, Status.RUNNING)

    def test_conf_none_and_missing_attrs(self):
        for conf in (None, types.SimpleNamespace(), object()):
            b = infer.infer(snap(), conf)
            b.validate()
            self.assertEqual((len(b.steps), len(b.modules)), (5, 3))

    def test_why_sources_are_keys_only(self):
        """R1-23 / §7.6：来源列只写证据键或结构名，不带 sha / PR 号 / 命令原文。"""
        table = "## W1\n- [x] S-1 a — PR #1 合入\n- [x] S-2 b\n- [ ] S-3 c\n- [ ] S-4 d [t:human]\n- [ ] S-5 e — `abc1234` [t:review]\n"
        res = {"gh.prs": ok("gh.prs", [pr(1, "S-1", ago(90), ago(80), merged_by="a"), batch_pr()]), "git.log": ok("git.log", log(commit("3" * 40, ago(100), "S-3 wip")))}
        b = board_of(table=table, results=res)
        allowed = set(infer.KEY_ETYPE) | {"任务表", "步骤聚合", "tasktable.quotes", "config.staging", "config.production"}
        for w in b.why + [x for v in b.steps for x in v.why] + [x for m in b.modules for x in m.why]:
            self.assertIn(w.source, allowed, (w.subject, w.source))


class RegistryTableTest(unittest.TestCase):
    """R1-24：每个 Status / 阶段各一条最小断言；登记表与推断共用 STATUS_RULE。"""

    def scenario(self, status):
        prs = [pr(3, "x", ago(50), ago(40), merged_by="a")]
        table = {
            Status.TODO: ("## W1\n- [ ] S-1 a\n- [ ] S-2 b\n", {}),
            Status.READY: ("## W1\n- [ ] S-2 b\n", {}),
            Status.RUNNING: ("## W1\n- [ ] S-2 b\n", {"git.log": ok("git.log", log(commit("2" * 40, ago(10), "S-2 wip")))}),
            Status.WATCH: ("## W1\n- [ ] S-2 b\n", {"git.log": ok("git.log", log(commit("2" * 40, ago(70), "S-2 wip")))}),
            Status.STALLED: ("## W1\n- [ ] S-2 b\n", {"git.log": ok("git.log", log(commit("2" * 40, ago(200), "S-2 wip")))}),
            Status.HUMAN: ("## W1\n- [ ] S-2 b [t:human]\n", {}),
            Status.DONE: ("## W1\n- [x] S-2 b — PR #3 合入\n", {"gh.prs": ok("gh.prs", prs)}),
            Status.DONEQ: ("## W1\n- [x] S-2 b\n", {}),
            Status.STALE: ("## W1\n- [ ] S-2 b — `abc1234` [t:review]\n", {}),
            Status.UNKNOWN: ("## W1\n- [ ] S-2 b\n", {"gh.prs": bad("gh.prs")}),
        }[status]
        return board_of(table=table[0], results=table[1])

    def test_every_status_reachable_and_registered(self):
        for status in Status:
            b = self.scenario(status)
            v = view(b, "S-2")
            self.assertEqual(v.status, status, status)
            self.assertEqual(v.why[0].status, registry.STATUS_LABEL[status])
            self.assertTrue(v.why[0].value.startswith(registry.STATUS_RULE[status]), status)
            self.assertIn(v.why[0].evidence, registry.EVIDENCE_REGISTRY[status], (status, v.why[0].evidence))
        self.assertEqual(registry.check_complete(), [])

    def test_every_stage_value(self):
        cfg = {"stages": [{"key": "staging", "result_key": "config.staging", "label": ""}, {"key": "production", "result_key": "config.production", "label": ""}]}
        tags = ok("gh.tags", [{"name": "v1", "sha": "m" * 40, "at": ""}])
        cases = {
            ("merged", True): {"gh.prs": ok("gh.prs", [batch_pr()])},
            ("merged", False): {"gh.prs": ok("gh.prs", [batch_pr(merged=False)])},
            ("merged", None): {"gh.prs": bad("gh.prs")},
            ("published", True): {"gh.prs": ok("gh.prs", [batch_pr()]), "gh.tags": tags},
            ("published", False): {"gh.prs": ok("gh.prs", [batch_pr()]), "gh.tags": ok("gh.tags", [])},
            ("published", None): {"gh.prs": ok("gh.prs", [batch_pr()]), "gh.tags": bad("gh.tags")},
            ("staging", True): {"gh.prs": ok("gh.prs", [batch_pr()]), "gh.tags": tags, "config.staging": ok("config.staging", "v1")},
            ("staging", False): {"gh.prs": ok("gh.prs", [batch_pr()]), "gh.tags": tags, "config.staging": ok("config.staging", "v0")},
            ("staging", None): {"gh.prs": ok("gh.prs", [batch_pr()]), "gh.tags": tags, "config.staging": bad("config.staging", "超时")},
            ("production", True): {"gh.prs": ok("gh.prs", [batch_pr()]), "gh.tags": tags, "config.production": ok("config.production", "v1")},
            ("production", False): {"gh.prs": ok("gh.prs", [batch_pr()]), "gh.tags": tags, "config.production": ok("config.production", "v0")},
            ("production", None): {"gh.prs": ok("gh.prs", [batch_pr()]), "gh.tags": tags, "config.production": bad("config.production", "超时")},
            ("closed", True): {"gh.issue": ok("gh.issue", issue(state="CLOSED", closed=ago(5)))},
            ("closed", False): {},
            ("closed", None): {"gh.issue": bad("gh.issue")},
        }
        for (key, want), res in cases.items():
            st = stage(board_of(results=res, config=cfg), key)
            self.assertIn(key, registry.STAGE_REGISTRY)
            if want is None:
                self.assertFalse(st.value.available, (key, want))
            else:
                self.assertTrue(st.value.available, (key, want))
                self.assertIs(st.value.value, want, (key, want))

    def test_markdown_stable(self):
        md = registry.render_markdown()
        for s in Status:
            self.assertIn("`%s`" % s.value, md)
            self.assertIn(registry.STATUS_RULE[s], md)
        self.assertEqual(md, registry.render_markdown())


if __name__ == "__main__":
    unittest.main()
