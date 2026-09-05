# -*- coding: utf-8 -*-
"""证据采集单测（接口约定 §6；零网络：LiveSource 只在临时仓里跑 git，PATH 里没有 gh）。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "plugin", "scripts"))

from boardlib import collect, infer  # noqa: E402
from boardlib.model import Grade, ProviderResult, Snapshot, Status  # noqa: E402

PY = sys.executable
GIT = shutil.which("git")
TABLE = "# 任务表\n\n> 2026-09-05 03:1x UTC / 11:1x 北京：产品负责人指令优雅暂停\n\n## W0\n\n- [x] S-0 合同（PR #1 合入）\n\n## W1\n\n- [ ] S-1 实现\n- [ ] S-2 审核 [t:review]\n"


def _bin_dir(tmp, *tools):
    """只含指定工具的 PATH 目录（没有 gh / tmux）。"""
    d = os.path.join(tmp, "bin")
    os.makedirs(d, exist_ok=True)
    for name in tools:
        real = shutil.which(name)
        link = os.path.join(d, name)
        if real and not os.path.lexists(link):
            os.symlink(real, link)
    return d


def _env(tmp, *tools):
    return {"PATH": _bin_dir(tmp, *tools), "HOME": tmp, "LANG": "C.UTF-8", "GIT_CONFIG_NOSYSTEM": "1"}


def _git(repo, *args, date=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@x", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@x")
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    return subprocess.run([GIT, "-c", "commit.gpgsign=false", *args], cwd=repo, env=env, check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout


def _make_repo(tmp):
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "docs", "traces", "3-demo"))
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "remote", "add", "origin", "https://github.com/example/demo.git")
    with open(os.path.join(repo, "docs/traces/3-demo/合同.md"), "w", encoding="utf-8") as fh:
        fh.write("# 合同\n")
    with open(os.path.join(repo, "docs/traces/3-demo/任务表.md"), "w", encoding="utf-8") as fh:
        fh.write(TABLE.replace("- [x] S-0", "- [ ] S-0"))
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "docs(#3): 三件套入库 (#1)", date="2026-09-05T02:00:00Z")
    with open(os.path.join(repo, "docs/traces/3-demo/任务表.md"), "w", encoding="utf-8") as fh:
        fh.write(TABLE)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "docs(#3): 任务表 S-0 勾选", date="2026-09-05T02:30:00Z")
    _git(repo, "tag", "v0.0.1")
    _git(repo, "branch", "batch/3-demo")
    return repo


@unittest.skipIf(GIT is None, "本机无 git")
class LiveSourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="board-collect-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = collect.LiveSource(self.tmp, per_cmd_timeout=5, round_timeout=5, env=_env(self.tmp, "python3", "git", "sleep", "cat"))

    def test_module_lives_in_this_tree(self):
        self.assertTrue(os.path.abspath(collect.__file__).startswith(ROOT))

    def test_run_success_and_parse(self):
        r = self.src.run("k", [PY, "-c", "print('hi')"], parse=lambda out: out.strip().upper())
        self.assertTrue(r.ok)
        self.assertEqual(r.value, "HI")
        self.assertEqual(r.grade, Grade.MEASURED)
        self.assertIsNotNone(r.fetched_at)

    def test_run_failures(self):
        r = self.src.run("gh.prs", ["gh", "pr", "list"])
        self.assertFalse(r.ok)
        self.assertIn("命令不可用", r.error)
        r = self.src.run("k", [PY, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"])
        self.assertFalse(r.ok)
        self.assertIn("退出码 3", r.error)
        self.assertIn("boom", r.error)
        r = self.src.run("k", [PY, "-c", "print('x')"], parse=lambda out: json.loads(out))
        self.assertFalse(r.ok)
        self.assertIn("解析失败", r.error)
        t0 = time.monotonic()
        r = self.src.run("k", ["sleep", "5"], timeout=1)
        self.assertFalse(r.ok)
        self.assertIn("超时", r.error)
        self.assertLess(time.monotonic() - t0, 3)

    def test_stdin_is_devnull(self):
        r = self.src.run("k", ["cat"], timeout=2)  # 若继承终端 stdin 会挂住
        self.assertTrue(r.ok)
        self.assertEqual(r.value, "")

    def test_error_text_scrubbed(self):
        r = self.src.run("k", [PY, "-c", "import sys; sys.stderr.write('at %s/x'); sys.exit(1)" % self.tmp])
        self.assertNotIn(self.tmp, r.error)
        self.assertNotIn(os.path.expanduser("~"), r.cmd)

    def test_round_timeout_marks_unfinished_and_returns_promptly(self):
        jobs = [
            ("fast", lambda: self.src.run("fast", [PY, "-c", "print(1)"])),
            ("slow", lambda: self.src.run("slow", ["sleep", "30"], timeout=30)),
            ("boom", lambda: 1 / 0),
        ]
        t0 = time.monotonic()
        res = self.src.run_all(jobs, deadline=time.monotonic() + 1)
        self.assertLess(time.monotonic() - t0, 4)
        self.assertTrue(res["fast"].ok)
        self.assertFalse(res["slow"].ok)
        self.assertEqual(res["slow"].error, "整轮超时")
        self.assertFalse(res["boom"].ok)
        self.assertIn("内部错误", res["boom"].error)


@unittest.skipIf(GIT is None, "本机无 git")
class CollectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="board-collect-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = _make_repo(self.tmp)
        self.env = _env(self.tmp, "python3", "git")
        self.conf = types.SimpleNamespace()

    def _snapshot(self, branch=None, now=None):
        src = collect.LiveSource(self.repo, per_cmd_timeout=10, round_timeout=20, env=self.env)
        return collect.collect(self.repo, None, branch, self.conf, now, src)

    def _tree_state(self):
        listing = sorted(os.path.relpath(os.path.join(d, f), self.repo) for d, _, fs in os.walk(self.repo) for f in fs if "/.git/" not in os.path.join(d, f) + "/")
        return listing, _git(self.repo, "status", "--porcelain"), _git(self.repo, "rev-parse", "HEAD")

    def test_collect_without_gh_is_unknown_not_crash(self):
        before = self._tree_state()
        snap = self._snapshot()
        self.assertEqual(self._tree_state(), before)  # 只读：不写目标仓库
        self.assertEqual(snap.trace_no, 3)
        self.assertEqual(snap.trace_dir, "docs/traces/3-demo")
        self.assertEqual(snap.repo, "example/demo")
        self.assertEqual(snap.branch, "batch/3-demo")  # 本地 batch/<n>-* 分支
        self.assertEqual(len(snap.tasktable.steps), 3)
        for key in collect.BUILTIN_KEYS:
            self.assertIn(key, snap.results, key)
        for key in ("git.log", "git.tasktable_history", "git.worktrees", "git.tags", "git.branches", "git.contract", "tasktable.quotes"):
            self.assertTrue(snap.results[key].ok, (key, snap.results[key].error))
        for key in ("gh.prs", "gh.issue", "gh.runs", "gh.tags"):
            self.assertFalse(snap.results[key].ok)
            self.assertIn("命令不可用：gh", snap.results[key].error)
        self.assertEqual(snap.results["tmux.windows"].error, "未配置编排 session")
        self.assertEqual(snap.results["gh.release_runs"].error, "未配置发布工作流")
        hist = snap.results["git.tasktable_history"].value
        self.assertEqual([c["checked"] for c in hist["commits"]], [[], ["S-0"]])
        self.assertEqual(hist["commits"][1]["quotes"], ["> 2026-09-05 03:1x UTC / 11:1x 北京：产品负责人指令优雅暂停"])
        self.assertEqual(snap.results["git.contract"].value["subject"], "docs(#3): 三件套入库 (#1)")
        self.assertEqual(snap.results["git.tags"].value[0]["name"], "v0.0.1")
        self.assertEqual(snap.results["git.worktrees"].value[0]["name"], "repo")
        self.assertNotIn(self.tmp, snap.to_json())
        board = infer.infer(snap, self.conf)
        by = {v.step.id: v for v in board.steps}
        self.assertEqual(by["S-0"].status, Status.DONE)  # 勾选提交信息含 S-0
        self.assertEqual(by["S-1"].status, Status.UNKNOWN)  # gh 不可得 → 未知，不回落到待办
        self.assertEqual(by["S-2"].status, Status.UNKNOWN)
        stages = {s.key: s for s in board.header.stages}
        self.assertFalse(stages["merged"].value.available)
        self.assertFalse(stages["closed"].value.available)

    def test_record_and_replay_round_trip(self):
        snap = self._snapshot()
        out = os.path.join(self.tmp, "fixture")
        path = collect.write_snapshot(snap, out)
        self.assertTrue(os.path.isfile(path))
        self.assertTrue(os.path.isfile(os.path.join(out, "任务表.md")))
        src = collect.RecordedSource(out)
        self.assertEqual(src.now, snap.now)
        self.assertEqual(src.get("nope").error, "夹具未记录")
        replay = collect.collect(out, None, None, self.conf, src.now, src)
        self.assertEqual(replay.trace_no, 3)
        self.assertEqual(replay.branch, "batch/3-demo")
        self.assertEqual(set(replay.results), set(snap.results))
        for key, r in snap.results.items():
            self.assertEqual((r.ok, r.value, r.error), (replay.results[key].ok, replay.results[key].value, replay.results[key].error), key)
        b1, b2 = infer.infer(snap, self.conf), infer.infer(replay, self.conf)
        self.assertEqual([v.status for v in b1.steps], [v.status for v in b2.steps])
        self.assertEqual(b1.header.block, b2.header.block)
        again = Snapshot.from_json(snap.to_json(), snap.tasktable)
        self.assertEqual(again.results["git.log"].value, snap.results["git.log"].value)

    def test_git_unavailable_too(self):
        src = collect.LiveSource(self.repo, per_cmd_timeout=5, round_timeout=10, env={"PATH": os.path.join(self.tmp, "nothing")})
        snap = collect.collect(self.repo, 3, None, self.conf, None, src)
        self.assertFalse(snap.results["git.log"].ok)
        self.assertIn("命令不可用", snap.results["git.log"].error)
        board = infer.infer(snap, self.conf)
        self.assertTrue(all(v.status == Status.UNKNOWN for v in board.steps))

    def test_round_timeout_marks_keys(self):
        src = collect.LiveSource(self.repo, per_cmd_timeout=5, round_timeout=0, env=self.env)
        snap = collect.collect(self.repo, None, None, self.conf, None, src)
        self.assertTrue(any(r.error == "整轮超时" for r in snap.results.values()))
        infer.infer(snap, self.conf).validate()

    def test_resolve_helpers(self):
        self.assertEqual(collect.resolve_trace(self.repo), (3, "docs/traces/3-demo", "docs/traces/3-demo/任务表.md"))
        self.assertEqual(collect.resolve_trace(self.repo, 9), (9, "", ""))
        self.assertEqual(collect.resolve_trace(self.tmp), (0, "", ""))
        prs = [{"headRefName": "trace/5-kickoff", "state": "MERGED"}, {"headRefName": "batch/5-x", "state": "OPEN"}]
        self.assertEqual(collect.resolve_branch(prs, 5, None), "batch/5-x")
        self.assertEqual(collect.resolve_branch(prs[:1], 5, None), "")
        self.assertEqual(collect.resolve_branch([{"headRefName": "fix/5-open", "state": "OPEN"}], 5, None), "fix/5-open")
        self.assertEqual(collect.resolve_branch([], 5, None, branches=[{"name": "origin/batch/5-y"}]), "batch/5-y")
        self.assertEqual(collect.resolve_branch(prs, 5, types.SimpleNamespace(trace_branch="cfg/b")), "cfg/b")
        self.assertEqual(collect.resolve_branch(prs, 5, None, override="ov"), "ov")

    def test_config_specs_result_keys(self):
        """S-4 Config：结果键 config.<key>；budget 走 ShellProvider（bash 只读 printf），阶段未配置。"""
        from boardlib import config as cfg
        toml = os.path.join(self.tmp, "board.toml")
        with open(toml, "w", encoding="utf-8") as fh:
            fh.write('[release]\nworkflow = "Publish"\n[budget.full_gate]\nlabel = "完整门禁"\ncap = 5\ncommand = "printf 3"\nparse = "int"\n'
                     '[[evidence]]\nkey = "hosts"\nlabel = "主机"\ncommand = "printf \'a\\nb\\n\'"\nparse = "lines"\n')
        conf = cfg.load(toml)
        self.assertEqual([k for _, k, _, _ in collect.config_specs(conf)], ["full_gate", "hosts"])
        meta = collect.config_meta(conf)
        self.assertEqual(meta["budgets"][0]["result_key"], "config.full_gate")
        self.assertEqual(meta["release_workflow"], "Publish")
        env = _env(self.tmp, "python3", "git", "bash", "printf")
        src = collect.LiveSource(self.repo, per_cmd_timeout=10, round_timeout=20, env=env)
        snap = collect.collect(self.repo, None, None, conf, None, src)
        self.assertIn("config.full_gate", snap.results)
        self.assertIn("config.hosts", snap.results)
        self.assertEqual(snap.results["gh.release_runs"].error[:5], "命令不可用")
        board = infer.infer(snap, conf)
        labels = [(l, cap) for l, _v, cap in board.header.budget]
        self.assertEqual(labels, [("完整门禁", 5)])

    def test_missing_trace_dir_does_not_crash(self):
        src = collect.LiveSource(self.repo, per_cmd_timeout=5, round_timeout=10, env=self.env)
        snap = collect.collect(self.repo, 42, None, self.conf, None, src)
        self.assertEqual(snap.tasktable.steps, [])
        self.assertTrue(any("找不到 Trace 目录" in w for w in snap.config.get("warnings", [])))
        board = infer.infer(snap, self.conf)
        self.assertTrue(any("找不到 Trace 目录" in w for w in board.header.warnings))


class ParserTest(unittest.TestCase):
    def test_gh_json_reducers(self):
        prs = collect._parse_prs(json.dumps([{"number": 1, "title": "t", "state": "MERGED", "mergedBy": {"login": "a"}, "author": {"login": "a"},
                                               "reviews": [{"state": "APPROVED", "author": {"login": "b"}}], "mergeCommit": {"oid": "abc"},
                                               "statusCheckRollup": [{"name": "ci", "conclusion": "SUCCESS", "status": "COMPLETED"}],
                                               "body": "x " + "/" + "home" + "/someone/y"}]))
        self.assertEqual(prs[0]["mergedBy"], "a")
        self.assertEqual(prs[0]["reviews"][0]["state"], "APPROVED")
        self.assertEqual(prs[0]["mergeCommit"], "abc")
        self.assertEqual(prs[0]["checks"][0]["conclusion"], "SUCCESS")
        self.assertEqual(prs[0]["body"], "x ~/y")
        iss = collect._parse_issue(json.dumps({"number": 1, "state": "OPEN", "comments": [{"body": "\n\n## 审核①结论\n正文", "createdAt": "2026-09-05T00:00:00Z",
                                                                                              "author": {"login": "a"}, "url": "https://x/issues/1#issuecomment-77"}]}))
        self.assertEqual(iss["comments"][0]["id"], 77)
        self.assertEqual(iss["comments"][0]["first_line"], "## 审核①结论")
        runs = collect._parse_runs(json.dumps([{"databaseId": 5, "conclusion": "success", "headBranch": "main"}]))
        self.assertEqual(runs[0]["id"], 5)
        wt = collect._parse_worktree_list("worktree /a/b\nHEAD abc\nbranch refs/heads/main\n\nworktree /c\nHEAD def\ndetached\n")
        self.assertEqual([(w["branch"], w["head"]) for w in wt], [("main", "abc"), ("", "def")])
        blob = collect._parse_tasktable_blob(TABLE)
        self.assertEqual(blob["ids"], ["S-0", "S-1", "S-2"])
        self.assertEqual(blob["checked"], ["S-0"])
        self.assertEqual(len(blob["quotes"]), 1)


if __name__ == "__main__":
    unittest.main()
