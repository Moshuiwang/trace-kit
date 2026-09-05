# -*- coding: utf-8 -*-
"""状态推断单测（接口约定 §7；合成快照，零网络）。"""
import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "plugin", "scripts"))

from boardlib import infer, registry, tasktable  # noqa: E402
from boardlib.model import Grade, ProviderResult, Snapshot, Status, Tier  # noqa: E402

NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
T0 = NOW - timedelta(hours=6)  # Trace 起点


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def ago(minutes):
    return NOW - timedelta(minutes=minutes)


def ok(key, value, grade=Grade.MEASURED):
    return ProviderResult(key, True, value, "", "<test>", NOW, grade)


def bad(key, error="gh 不可用"):
    return ProviderResult(key, False, None, error, "<test>", NOW)


def commit(sha, at, subject, refs=""):
    return {"sha": sha, "at": iso(at), "authored": iso(at), "author": "t", "subject": subject, "refs": refs}


def pr(number, title, created, merged=None, head="feat/x", author="a", merged_by=None, reviews=(), body="", draft=False, merge_commit=""):
    return {
        "number": number, "title": title, "state": "MERGED" if merged else "OPEN", "isDraft": draft, "createdAt": iso(created),
        "mergedAt": iso(merged) if merged else "", "closedAt": iso(merged) if merged else "", "mergedBy": merged_by or "",
        "author": author, "reviews": [{"state": r, "author": "r", "submittedAt": ""} for r in reviews], "headRefName": head,
        "baseRefName": "main", "mergeCommit": merge_commit, "url": "", "body": body, "checks": [],
    }


def issue(comments=(), state="OPEN", closed=None, created=T0):
    return {"number": 7, "title": "t", "state": state, "createdAt": iso(created), "closedAt": iso(closed) if closed else "", "url": "",
            "comments": [{"id": i + 1, "createdAt": iso(at), "author": "a", "first_line": line, "url": ""} for i, (at, line) in enumerate(comments)]}


def run(at, conclusion, branch="feat/x", sha="", name="ci"):
    return {"id": 1, "name": name, "workflowName": name, "conclusion": conclusion, "status": "completed", "createdAt": iso(at), "updatedAt": iso(at),
            "headSha": sha, "headBranch": branch, "event": "push", "url": ""}


def history(*entries):
    return {"path": "docs/traces/7-demo/任务表.md", "commits": [{"sha": sha, "at": iso(at), "ids": ids, "checked": checked, "quotes": quotes}
                                                                for sha, at, ids, checked, quotes in entries]}


BASE_TABLE = "## W0\n- [x] S-0 合同\n## W1\n- [ ] S-1 实现\n- [ ] S-2 测试\n- [ ] S-3 审核 [t:review]\n## W2\n- [ ] S-4 人工闸 [t:human]\n"


def snap(table=BASE_TABLE, results=None, branch="batch/7-x", now=NOW, config=None):
    tt = tasktable.parse(table, "docs/traces/7-demo/任务表.md")
    res = {
        "git.log": ok("git.log", []),
        "git.tasktable_history": ok("git.tasktable_history", history(("aaaaaaa", T0, ["S-0", "S-1", "S-2", "S-3", "S-4"], ["S-0"], [])), Grade.INFERRED),
        "git.worktrees": ok("git.worktrees", []),
        "git.tags": ok("git.tags", []),
        "git.branches": ok("git.branches", [{"name": branch, "sha": "b" * 40, "at": iso(NOW)}] if branch else []),
        "git.contract": ok("git.contract", None),
        "tasktable.quotes": ok("tasktable.quotes", [], Grade.REPORTED),
        "gh.prs": ok("gh.prs", []),
        "gh.issue": ok("gh.issue", issue()),
        "gh.runs": ok("gh.runs", []),
        "gh.release_runs": bad("gh.release_runs", "未配置发布工作流"),
        "tmux.windows": bad("tmux.windows", "未配置编排 session"),
    }
    res.update(results or {})
    return Snapshot(now=now, repo="o/r", trace_no=7, trace_dir="docs/traces/7-demo", branch=branch, tasktable=tt, results=res, config=config or {})


def board_of(**kw):
    conf = kw.pop("conf", types.SimpleNamespace())
    return infer.infer(snap(**kw), conf)


def view(board, sid):
    return next(v for v in board.steps if v.step.id == sid)


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

    def test_done_with_commit_containing_id(self):
        b = board_of(table="## W1\n- [x] S-1 实现\n", results={"git.log": ok("git.log", [commit("c" * 40, ago(30), "feat: S-1 done")])})
        v = view(b, "S-1")
        self.assertEqual(v.status, Status.DONE)
        self.assertEqual(v.chip, "commit ccccccc ✓")

    def test_id_word_boundary(self):
        table = "## W1\n- [x] S-1 a\n- [x] S-1a b\n- [x] S-1-1 c\n"
        b = board_of(table=table, results={"git.log": ok("git.log", [commit("1" * 40, ago(30), "feat: S-1a and S-1-1 only")])})
        self.assertEqual(view(b, "S-1").status, Status.DONEQ)
        self.assertEqual(view(b, "S-1a").status, Status.DONE)
        self.assertEqual(view(b, "S-1-1").status, Status.DONE)
        b2 = board_of(table="## W1\n- [ ] S-2 a\n", results={"git.log": ok("git.log", [commit("2" * 40, ago(10), "wip", refs="wt/17-S-2")])})
        self.assertEqual(view(b2, "S-2").status, Status.RUNNING)

    def test_doneq_without_artifact(self):
        b = board_of(table="## W1\n- [x] S-1 实现\n")
        v = view(b, "S-1")
        self.assertEqual(v.status, Status.DONEQ)
        self.assertEqual(v.chip, "无 commit · 无 PR")
        self.assertEqual(v.chip_status, Status.DONEQ)
        self.assertIn("自述未证 1（S-1）", b.header.doubt)
        self.assertIsNone(v.started)

    def test_human(self):
        b = board_of()
        self.assertEqual(view(b, "S-4").status, Status.HUMAN)

    def test_running_watch_stalled_by_age(self):
        for minutes, want in ((30, Status.RUNNING), (75, Status.WATCH), (120, Status.STALLED)):
            b = board_of(table="## W1\n- [ ] S-1 实现\n", results={"git.log": ok("git.log", [commit("d" * 40, ago(minutes), "S-1 wip")])})
            v = view(b, "S-1")
            self.assertEqual(v.status, want, minutes)
            self.assertEqual(v.elapsed_min, minutes)
        b = board_of(table="## W1\n- [ ] S-1 实现\n", results={"git.log": ok("git.log", [commit("d" * 40, ago(120), "S-1 wip")])})
        self.assertIn("S-1 120 分钟无证据", b.header.block)

    def test_worktree_evidence(self):
        wt = [{"name": "S-1", "head": "e" * 40, "branch": "wt/7-S-1", "main": False, "last_at": iso(ago(5)), "last_subject": "x", "ahead": 2, "dirty": 0, "files": [], "error": ""}]
        b = board_of(table="## W1\n- [ ] S-1 实现\n", results={"git.worktrees": ok("git.worktrees", wt)})
        v = view(b, "S-1")
        self.assertEqual(v.status, Status.RUNNING)
        self.assertTrue(v.chip.startswith("wt S-1"))

    def test_ready_and_todo(self):
        b = board_of()
        self.assertEqual(view(b, "S-1").status, Status.READY)  # S-0 已勾选
        self.assertEqual(view(b, "S-2").status, Status.TODO)
        self.assertTrue(b.header.nxt.startswith("S-1 实现（ready）"))

    def test_stale_review_candidate_changed(self):
        table = "## W1\n- [ ] S-3 审核 候选 `abc1234` [t:review]\n"
        b = board_of(table=table)
        v = view(b, "S-3")
        self.assertEqual(v.status, Status.STALE)
        self.assertTrue(v.chip.startswith("候选 abc123"))
        self.assertTrue(v.rework)
        b2 = board_of(table="## W1\n- [ ] S-3 审核 候选 `bbbbbbb` [t:review]\n")
        self.assertNotEqual(view(b2, "S-3").status, Status.STALE)

    def test_now_before_first_check_is_unchecked(self):
        hist = history(("aaaaaaa", NOW + timedelta(hours=1), ["S-1"], ["S-1"], []))
        b = board_of(table="## W1\n- [x] S-1 实现\n", results={"git.tasktable_history": ok("git.tasktable_history", hist, Grade.INFERRED)})
        self.assertEqual(view(b, "S-1").status, Status.READY)


class UnknownTest(unittest.TestCase):
    """证据不可得 → 未知，不回落（https://github.com/Moshuiwang/lingxi/issues/579）。"""

    GH_DOWN = {"gh.prs": bad("gh.prs", "命令不可用：gh"), "gh.issue": bad("gh.issue", "命令不可用：gh"), "gh.runs": bad("gh.runs", "命令不可用：gh")}

    def test_gh_unavailable_everything_unknown_not_todo(self):
        b = board_of(results=self.GH_DOWN)
        self.assertEqual(view(b, "S-0").status, Status.UNKNOWN)
        self.assertEqual(view(b, "S-1").status, Status.UNKNOWN)
        self.assertEqual(view(b, "S-2").status, Status.UNKNOWN)
        self.assertEqual(view(b, "S-4").status, Status.HUMAN)  # 标签判定不依赖 gh
        self.assertEqual(view(b, "S-1").chip, "证据未知")
        stages = {s.key: s for s in b.header.stages}
        self.assertFalse(stages["merged"].value.available)
        self.assertFalse(stages["closed"].value.available)
        self.assertEqual(stages["published"].value.value, False)  # git.tags 可得，按自身证据判定
        m = b.modules[1]
        self.assertEqual(m.status, Status.UNKNOWN)
        self.assertFalse(m.rounds.review.available)
        self.assertIn("未知", m.rounds_line)
        self.assertIn("PR 未知", m.evidence_line)
        self.assertIn("PR 存疑未知", b.header.doubt)
        self.assertTrue(any(w.startswith("gh.prs 不可得") for w in b.header.warnings))
        self.assertTrue(all(not w.available for w in b.why if w.subject == "S-1" and w.status == "unknown"))

    def test_fresh_git_evidence_still_running_when_gh_down(self):
        res = dict(self.GH_DOWN)
        res["git.log"] = ok("git.log", [commit("f" * 40, ago(10), "S-1 wip"), commit("e" * 40, ago(200), "S-2 wip")])
        b = board_of(results=res)
        self.assertEqual(view(b, "S-1").status, Status.RUNNING)
        self.assertEqual(view(b, "S-2").status, Status.UNKNOWN)  # 旧证据 + 键不可得，不能断言卡住

    def test_git_unavailable_too(self):
        res = {k: bad(k, "命令不可用") for k in ("git.log", "git.tasktable_history", "git.worktrees", "git.tags", "git.branches", "git.contract", "gh.prs", "gh.issue", "gh.runs")}
        b = board_of(results=res)
        self.assertTrue(all(v.status in (Status.UNKNOWN, Status.HUMAN) for v in b.steps))
        self.assertTrue(all(not s.value.available for s in b.header.stages))
        self.assertEqual(b.header.evidence, "未知（证据不可得）")

    def test_recorded_missing_key(self):
        b = board_of(results={"gh.prs": ProviderResult("gh.prs", False, None, "夹具未记录")})
        self.assertEqual(view(b, "S-1").status, Status.UNKNOWN)


class ModuleTest(unittest.TestCase):
    def test_aggregation_priority(self):
        table = "## W1\n- [x] S-1 a — PR #1 合入\n- [ ] S-2 b\n- [ ] S-3 c\n"
        res = {"gh.prs": ok("gh.prs", [pr(1, "S-1", ago(90), ago(80), merged_by="a")]),
               "git.log": ok("git.log", [commit("1" * 40, ago(100), "S-2 wip"), commit("2" * 40, ago(5), "S-3 wip")])}
        m = board_of(table=table, results=res).modules[0]
        self.assertEqual(m.status, Status.STALLED)
        self.assertEqual(m.done, 1)
        self.assertEqual(m.total, 3)
        self.assertEqual(m.what, "W1 1/3")
        self.assertEqual(m.elapsed_min, 100)
        all_done = board_of(table="## W1\n- [x] S-1 a — PR #1 合入\n", results={"gh.prs": res["gh.prs"]}).modules[0]
        self.assertEqual(all_done.status, Status.DONE)
        self.assertEqual(all_done.actual_min, 10)
        mixed = board_of(table="## W1\n- [x] S-1 a — PR #1 合入\n- [x] S-2 b\n", results={"gh.prs": res["gh.prs"]}).modules[0]
        self.assertEqual(mixed.status, Status.DONEQ)
        self.assertEqual(board_of(table="## W1\n- [ ] S-1 a\n- [ ] S-2 b [t:human]\n").modules[0].status, Status.HUMAN)
        self.assertEqual(board_of(table="## A\n## B\n- [ ] S-1 a\n").modules[0].status, Status.TODO)

    def test_rounds_regex_and_tier(self):
        comments = [
            (ago(50), "## 审核①结论（候选 abc）— S-1"),
            (ago(40), "## 修复包已派发（S-1）"),
            (ago(30), "定向复核②结论：S-1 全部闭合"),
            (ago(20), "codex 外审结论账本（S-1）"),
            (ago(10), "## 审核③结论（无 Step）"),
            (ago(5), "里程碑收口 M2（S-1）"),
        ]
        b = board_of(table="## W1\n- [ ] S-1 a\n- [ ] S-2 b\n", results={"gh.issue": ok("gh.issue", issue(comments))})
        m = b.modules[0]
        self.assertEqual(m.rounds.review.value, 2)
        self.assertEqual(m.rounds.external.value, 1)
        self.assertEqual(m.rounds.fixpack.value, 1)
        self.assertEqual(m.tier, Tier.TWO)
        self.assertEqual(m.rounds_line, "审 2实 · 外 1实 · 修 1实 · CI 红0推 绿0推")
        self.assertIn("评论 5", m.evidence_line)
        self.assertIn("Trace 级 审 1实", b.header.stage)
        for n, want in ((0, Tier.NONE), (1, Tier.ONE), (3, Tier.THREE), (4, Tier.MORE), (9, Tier.MORE)):
            self.assertEqual(infer._tier(n), want)

    def test_ci_window_and_budget(self):
        table = "## W1\n- [x] S-1 a — PR #1 合入\n"
        runs = [run(ago(85), "success"), run(ago(82), "failure"), run(ago(300), "failure", branch="other")]
        res = {"gh.prs": ok("gh.prs", [pr(1, "S-1", ago(90), ago(80), head="feat/x", merged_by="a")]), "gh.runs": ok("gh.runs", runs)}
        b = board_of(table=table, results=res)
        m = b.modules[0]
        self.assertEqual((m.rounds.ci_red.value, m.rounds.ci_green.value), (1, 1))
        self.assertEqual(m.rounds.ci_red.grade, Grade.INFERRED)
        self.assertEqual([(l, v.value, cap) for l, v, cap in b.header.budget], [("PR", 1, None), ("CI 次数", 3, None)])

    def test_module_needs(self):
        table = "## A\n- [ ] S-1 a\n## B\n- [ ] S-2 b\n## C\n- [ ] S-3 c [needs:S-1]\n"
        mods = board_of(table=table).modules
        self.assertEqual([m.needs for m in mods], [[], [0], [0]])


class StageAndHeaderTest(unittest.TestCase):
    def test_five_levels_merged_published_closed(self):
        prs = [pr(9, "batch", ago(120), ago(60), head="batch/7-x", merged_by="a")]
        tags = [{"name": "v1.0.0", "at": iso(ago(50)), "object": "t" * 40, "commit": "c" * 40}]
        res = {"gh.prs": ok("gh.prs", prs), "git.tags": ok("git.tags", tags), "gh.issue": ok("gh.issue", issue(state="CLOSED", closed=ago(10)))}
        b = board_of(results=res)
        st = {s.key: s for s in b.header.stages}
        self.assertTrue(st["merged"].value.value)
        self.assertTrue(st["published"].value.value)
        self.assertFalse(st["staging"].configured)
        self.assertFalse(st["production"].configured)
        self.assertTrue(st["closed"].value.value)
        self.assertTrue(b.header.stage.startswith("已收口"))
        self.assertEqual(b.header.nxt, "无（Trace 已关闭）")

    def test_merged_false_when_branch_known_but_no_batch_pr(self):
        b = board_of(results={"gh.prs": ok("gh.prs", [pr(1, "S-1 kickoff", ago(300), ago(290), head="trace/7-kickoff", merged_by="a")])})
        st = {s.key: s for s in b.header.stages}
        self.assertIs(st["merged"].value.value, False)
        self.assertEqual(st["merged"].value.grade, Grade.INFERRED)
        b2 = board_of(branch="", results={"gh.prs": ok("gh.prs", [pr(1, "S-1 kickoff", ago(300), ago(290), head="trace/7-kickoff", merged_by="a")])})
        self.assertIs({s.key: s for s in b2.header.stages}["merged"].value.value, True)  # 分支未知 → 全部 PR 合入
        self.assertTrue(b2.header.stage.startswith("已合入主干 · 1/5 勾选"))

    def test_published_needs_release_run_when_configured(self):
        prs = [pr(9, "batch", ago(120), ago(60), head="batch/7-x", merged_by="a")]
        tags = [{"name": "v1.0.0", "at": iso(ago(50)), "object": "t" * 40, "commit": "c" * 40}]
        base = {"gh.prs": ok("gh.prs", prs), "git.tags": ok("git.tags", tags), "git.log": ok("git.log", [commit("c" * 40, ago(60), "release")])}
        cfg = {"release_workflow": "Publish"}
        b = board_of(results=dict(base, **{"gh.release_runs": bad("gh.release_runs", "超时")}), config=cfg)
        self.assertFalse({s.key: s for s in b.header.stages}["published"].value.available)
        b = board_of(results=dict(base, **{"gh.release_runs": ok("gh.release_runs", [run(ago(55), "success", "main", "c" * 40, "Publish")])}), config=cfg)
        self.assertTrue({s.key: s for s in b.header.stages}["published"].value.value)
        b = board_of(results=dict(base, **{"gh.release_runs": ok("gh.release_runs", [run(ago(55), "failure", "main", "c" * 40, "Publish")])}), config=cfg)
        self.assertEqual({s.key: s for s in b.header.stages}["published"].value.value, False)

    def test_staging_production_compare(self):
        prs = [pr(9, "batch", ago(120), ago(60), head="batch/7-x", merged_by="a")]
        tags = [{"name": "v1.0.0", "at": iso(ago(50)), "object": "t" * 40, "commit": "c" * 40}]
        cfg = {"stages": [{"key": "staging", "label": "", "grade": "measured"}, {"key": "production", "label": "", "grade": "measured"}]}
        res = {"gh.prs": ok("gh.prs", prs), "git.tags": ok("git.tags", tags),
               "config.stages.staging": ok("config.stages.staging", "v1.0.0\n"), "config.stages.production": bad("config.stages.production", "ssh 超时")}
        st = {s.key: s for s in board_of(results=res, config=cfg).header.stages}
        self.assertTrue(st["staging"].configured and st["staging"].value.value is True)
        self.assertTrue(st["production"].configured and not st["production"].value.available)
        res["config.stages.production"] = ok("config.stages.production", "v0.9.0")
        b = board_of(results=res, config=cfg)
        st = {s.key: s for s in b.header.stages}
        self.assertIs(st["production"].value.value, False)
        self.assertTrue(b.header.stage.startswith("预发已升级"))
        res["config.stages.production"] = ok("config.stages.production", "v1.0.0")
        b = board_of(results=res, config=cfg)
        self.assertTrue(b.header.stage.startswith("已上生产"))
        self.assertTrue(b.header.nxt.startswith("观察与收口"))

    def test_contract_pr_self_merged_zero_approval(self):
        table = "## W0\n- [x] S-0 合同 — PR #2 合入\n"
        prs = [pr(2, "合同", ago(300), ago(290), head="trace/7-kickoff", author="bot", merged_by="bot", merge_commit="a" * 40)]
        res = {"gh.prs": ok("gh.prs", prs), "git.contract": ok("git.contract", {"sha": "a" * 40, "at": iso(ago(290)), "subject": "docs (#2)", "path": "x"})}
        b = board_of(table=table, results=res)
        v = view(b, "S-0")
        self.assertEqual(v.status, Status.DONE)
        self.assertEqual(v.chip, "PR #2 ✓合入 · 自合 · 零批准")
        self.assertEqual(v.chip_status, Status.DONEQ)
        self.assertIn("合同 PR #2 自合 / 零批准", b.header.doubt)
        self.assertIn("1/1 PR 自合 · 零批准", b.header.doubt)
        prs2 = [pr(2, "合同", ago(300), ago(290), head="trace/7-kickoff", author="bot", merged_by="pm", reviews=("APPROVED",), merge_commit="a" * 40)]
        b2 = board_of(table=table, results=dict(res, **{"gh.prs": ok("gh.prs", prs2)}))
        self.assertEqual(view(b2, "S-0").chip, "PR #2 ✓合入 · 批准")
        self.assertEqual(view(b2, "S-0").chip_status, Status.DONE)
        self.assertNotIn("合同 PR", b2.header.doubt)

    def test_shared_pr_and_body_fallback(self):
        table = "## W1\n- [x] S-1 a — PR #5 合入\n- [x] S-2 b\n- [x] S-3 c\n"
        prs = [pr(5, "feat: S-1 / S-2", ago(50), ago(40), merged_by="a", body="also mentions S-3")]
        b = board_of(table=table, results={"gh.prs": ok("gh.prs", prs)})
        self.assertEqual(view(b, "S-2").status, Status.DONE)
        self.assertEqual(view(b, "S-3").status, Status.DONEQ)  # 正文只在指针与标题都为空时用
        self.assertIn("共用 PR #5（S-1/S-2）", b.header.doubt)
        prs2 = [pr(6, "no id in title", ago(50), ago(40), merged_by="a", body="Trace：#7（S-3）")]
        b2 = board_of(table="## W1\n- [x] S-3 c\n", results={"gh.prs": ok("gh.prs", prs2)})
        self.assertEqual(view(b2, "S-3").status, Status.DONE)

    def test_pause_interval_and_gap(self):
        table = "## W1\n- [x] S-1 a\n- [x] S-2 b\n"
        quote = "> **2026-09-05 06:1x UTC / 14:1x 北京：产品负责人指令优雅暂停**"
        hist = history(("a" * 7, ago(350), ["S-1", "S-2"], [], []), ("b" * 7, ago(300), ["S-1", "S-2"], ["S-1"], []),
                       ("c" * 7, ago(240), ["S-1", "S-2"], ["S-1"], [quote]), ("d" * 7, ago(30), ["S-1", "S-2"], ["S-1", "S-2"], [quote]))
        res = {"git.tasktable_history": ok("git.tasktable_history", hist, Grade.INFERRED),
               "git.log": ok("git.log", [commit("1" * 40, ago(320), "S-1 done"), commit("2" * 40, ago(40), "S-2 done")]),
               "tasktable.quotes": ok("tasktable.quotes", [quote], Grade.REPORTED)}
        b = board_of(table=table, results=res)
        self.assertIn("最大空档 280 分钟", b.header.block)
        self.assertIn("其中暂停 200 分钟报", b.header.block)
        pause = next(w for w in b.why if w.subject == "暂停")
        self.assertEqual(pause.status, "200 分钟（报）")
        self.assertTrue(pause.source.startswith("git.tasktable_history ccccccc"))
        gap = next(w for w in b.why if w.subject == "空档")
        self.assertIn("归因暂停 200 分钟", gap.value)
        # 无历史时退回行内时刻（自报级）：06:1x → 06:10
        res2 = dict(res, **{"git.tasktable_history": bad("git.tasktable_history", "git 不可用")})
        b2 = board_of(table=table, results=res2)
        pause2 = next(w for w in b2.why if w.subject == "暂停")
        self.assertIn("行内时刻", pause2.source)

    def test_window_note_and_warnings(self):
        b = board_of(table="## W1\n- [ ] S-1 a\n- [ ] 无编号\n- [ ] S-2 " + "字" * 20 + "\n")
        self.assertIn(infer.WINDOW_NOTE, b.header.warnings)
        self.assertIn("任务表未解析 1 行", b.header.warnings)
        self.assertIn("任务表超限 1 行", b.header.warnings)
        cfg = {"tmux_configured": True, "window_pattern": "^hb-b[0-9]+$"}
        b2 = board_of(results={"tmux.windows": ok("tmux.windows", ["guardian", "hb-b1"])}, config=cfg)
        self.assertNotIn(infer.WINDOW_NOTE, b2.header.warnings)
        self.assertIn("窗口 hb-b1 存活", b2.header.nxt)
        b3 = board_of(results={"tmux.windows": bad("tmux.windows", "tmux 不可用")}, config=cfg)
        self.assertIn(infer.WINDOW_NOTE, b3.header.warnings)
        self.assertIn("窗口 未知", b3.header.nxt)

    def test_conf_none_and_missing_attrs(self):
        for conf in (None, types.SimpleNamespace(), object()):
            b = infer.infer(snap(), conf)
            b.validate()
            self.assertEqual(len(b.steps), 5)
            self.assertEqual(len(b.modules), 3)

    def test_why_rows_and_registry_consistency(self):
        table = "## W1\n- [x] S-1 a — PR #1 合入\n- [x] S-2 b\n- [ ] S-3 c\n- [ ] S-4 d [t:human]\n- [ ] S-5 e [t:review] `abc1234`\n"
        res = {"gh.prs": ok("gh.prs", [pr(1, "S-1", ago(90), ago(80), merged_by="a")]), "git.log": ok("git.log", [commit("3" * 40, ago(100), "S-3 wip")])}
        b = board_of(table=table, results=res)
        for v in b.steps:
            self.assertIn(v.why[0].evidence, registry.EVIDENCE_REGISTRY[v.status], v.step.id)
            self.assertEqual(v.why[0].status, v.status.value)
        subjects = {w.subject for w in b.why}
        for s in ("S-1", "W1", "阶段·合入主干", "阶段·已发布", "阶段·收口", "PR 合并方式"):
            self.assertIn(s, subjects)
        self.assertEqual(registry.check_complete(), [])
        md = registry.render_markdown()
        for s in Status:
            self.assertIn("`%s`" % s.value, md)
        self.assertEqual(md, registry.render_markdown())


if __name__ == "__main__":
    unittest.main()
