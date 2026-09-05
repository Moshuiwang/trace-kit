# -*- coding: utf-8 -*-
"""证据采集单测（接口约定 §6；零网络：LiveSource 只在临时仓里跑 git，PATH 里没有 gh）。账本 F-1 条目见用例名括号。"""
import json
import os
import shutil
import signal
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


def _write(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _make_repo(tmp):
    """三个提交：入库（含代码）→ S-0 完成（改代码＋勾选）→ 只改任务表（登记暂停）。"""
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "remote", "add", "origin", "https://github.com/example/demo.git")
    _write(repo, "docs/traces/3-demo/合同.md", "# 合同\n")
    _write(repo, "docs/traces/3-demo/任务表.md", TABLE.replace("- [x] S-0", "- [ ] S-0").replace("> 2026-09-05 03:1x UTC / 11:1x 北京：产品负责人指令优雅暂停\n\n", ""))
    _write(repo, "app.py", "print(1)\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "docs(#3): 三件套入库 (#1)", date="2026-09-05T02:00:00Z")
    _write(repo, "app.py", "print(2)\n")
    _write(repo, "docs/traces/3-demo/任务表.md", TABLE.replace("> 2026-09-05 03:1x UTC / 11:1x 北京：产品负责人指令优雅暂停\n\n", ""))
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "feat(#3): S-0 合同落地", date="2026-09-05T02:30:00Z")
    _write(repo, "docs/traces/3-demo/任务表.md", TABLE)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "docs(#3): 任务表登记暂停 S-1", date="2026-09-05T03:10:00Z")
    _git(repo, "tag", "v0.0.1")
    _git(repo, "branch", "batch/3-demo")
    return repo


@unittest.skipIf(GIT is None, "本机无 git")
class LiveSourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="board-collect-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = collect.LiveSource(self.tmp, per_cmd_timeout=5, round_timeout=5, env=_env(self.tmp, "python3", "git", "sleep", "cat", "bash"))

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

    def test_timeout_kills_whole_process_group(self):
        """R1-29：超时杀整个进程组——bash 起的孙进程（sleep）也要死，不能靠继承的管道拖住 communicate。"""
        marker = os.path.join(self.tmp, "child.pid")
        script = "sleep 30 & echo $! > %s; wait" % marker
        t0 = time.monotonic()
        r = self.src.run("k", ["bash", "-c", script], timeout=1)
        self.assertFalse(r.ok)
        self.assertIn("超时", r.error)
        self.assertLess(time.monotonic() - t0, 4)
        with open(marker) as fh:
            child = int(fh.read().strip())
        deadline = time.monotonic() + 3
        alive = True
        while time.monotonic() < deadline:
            try:
                os.kill(child, 0)
                time.sleep(0.05)
            except ProcessLookupError:
                alive = False
                break
        if alive:
            os.kill(child, signal.SIGKILL)
        self.assertFalse(alive, "孙进程 sleep 仍活着：进程组没被杀")

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
        self.assertFalse(any(t.is_alive() and t.name.startswith("board-") and not t.daemon for t in __import__("threading").enumerate()))

    def test_cancel_is_idempotent_and_per_round(self):
        """R1-29 / R2-5：cancel() 杀本轮进程组、置取消标志、幂等；旧轮取消不误杀新轮。"""
        started = __import__("threading").Event()
        holder = {}

        def slow_job():
            started.set()
            holder["res"] = self.src.run("slow", ["sleep", "30"], timeout=30)
            return holder["res"]

        import threading
        results = {}
        t = threading.Thread(target=lambda: results.update(self.src.run_all([("slow", slow_job)], deadline=time.monotonic() + 30)), daemon=True)
        t.start()
        started.wait(2)
        time.sleep(0.2)
        rid = self.src.current_round
        t0 = time.monotonic()
        self.src.cancel()
        self.src.cancel()  # 幂等
        t.join(5)
        self.assertFalse(t.is_alive())
        self.assertLess(time.monotonic() - t0, 5)
        self.assertFalse(results["slow"].ok)
        self.assertIn("已取消", results["slow"].error)
        # 旧轮已取消，新轮不受影响
        res = self.src.run_all([("ok", lambda: self.src.run("ok", [PY, "-c", "print(1)"]))], deadline=time.monotonic() + 5)
        self.assertTrue(res["ok"].ok)
        self.assertNotEqual(self.src.current_round, rid)
        self.src.cancel(rid)  # 对已结束的轮次调用无副作用

    def test_deadline_attribute_bounds_single_commands(self):
        """R1-30：source.deadline（绝对 monotonic）约束每条命令与 slug 探测的剩余预算。"""
        self.src.deadline = time.monotonic() + 0.5
        t0 = time.monotonic()
        r = self.src.run("k", ["sleep", "10"], timeout=10)
        self.assertFalse(r.ok)
        self.assertLess(time.monotonic() - t0, 3)
        self.src.deadline = time.monotonic() - 1
        r = self.src.run("k", [PY, "-c", "print(1)"])
        self.assertEqual(r.error, "整轮超时")


@unittest.skipIf(GIT is None, "本机无 git")
class CollectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="board-collect-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = _make_repo(self.tmp)
        self.env = _env(self.tmp, "python3", "git")
        self.conf = types.SimpleNamespace()

    def _snapshot(self, branch=None, now=None, trace_no=None):
        src = collect.LiveSource(self.repo, per_cmd_timeout=10, round_timeout=20, env=self.env)
        return collect.collect(self.repo, trace_no, branch, self.conf, now, src)

    def _tree_state(self):
        listing = sorted(os.path.relpath(os.path.join(d, f), self.repo) for d, _, fs in os.walk(self.repo) for f in fs if "/.git/" not in os.path.join(d, f) + "/")
        return listing, _git(self.repo, "status", "--porcelain"), _git(self.repo, "rev-parse", "HEAD")

    def test_collect_without_gh_is_unknown_not_crash(self):
        before = self._tree_state()
        snap = self._snapshot()
        self.assertEqual(self._tree_state(), before)  # 只读：不写目标仓库
        self.assertEqual((snap.trace_no, snap.trace_dir, snap.repo, snap.branch), (3, "docs/traces/3-demo", "example/demo", "batch/3-demo"))
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
        self.assertIn("无已证实的合并点", snap.results["gh.compare"].error)
        hist = snap.results["git.tasktable_history"].value
        self.assertEqual([c["checked"] for c in hist["commits"]], [[], ["S-0"], ["S-0"]])
        self.assertEqual(hist["commits"][2]["quotes"], ["> 2026-09-05 03:1x UTC / 11:1x 北京：产品负责人指令优雅暂停"])
        self.assertEqual(snap.results["git.contract"].value["subject"], "docs(#3): 三件套入库 (#1)")
        self.assertEqual(snap.results["git.tags"].value[0]["name"], "v0.0.1")
        self.assertEqual(snap.results["git.worktrees"].value[0]["name"], "repo")
        self.assertNotIn(self.tmp, snap.to_json())
        board = infer.infer(snap, self.conf)
        by = {v.step.id: v for v in board.steps}
        self.assertEqual(by["S-0"].status, Status.DONE)  # 提交 feat(#3): S-0 触及 app.py → 制品
        self.assertEqual(by["S-1"].status, Status.UNKNOWN)  # 只有只改任务表的提交 + gh 不可得 → 未知
        self.assertEqual(by["S-2"].status, Status.UNKNOWN)
        stages = {s.key: s for s in board.header.stages}
        self.assertFalse(stages["merged"].value.available)
        self.assertFalse(stages["closed"].value.available)

    def test_git_log_branch_mode_author_date_and_docs_only(self):
        """R1-1 / R1-19 / A-2：分支模式（批次分支＋worktree 分支）、%ad 作者时刻、只改 Trace 目录的提交标 docs_only。"""
        snap = self._snapshot()
        value = snap.results["git.log"].value
        self.assertEqual(value["mode"], "branch")
        self.assertEqual(value["refs"], ["batch/3-demo"])
        self.assertFalse(value["truncated"])
        by_subject = {c["subject"]: c for c in value["commits"]}
        self.assertEqual(by_subject["feat(#3): S-0 合同落地"]["docs_only"], False)
        self.assertEqual(by_subject["docs(#3): 任务表登记暂停 S-1"]["docs_only"], True)
        self.assertEqual(by_subject["feat(#3): S-0 合同落地"]["at"][:19], "2026-09-05T02:30:00")
        self.assertEqual(snap.results["git.log"].grade, Grade.MEASURED)
        snap2 = self._snapshot(branch="nope/branch")
        self.assertEqual(snap2.results["git.log"].value["mode"], "all")
        self.assertEqual(snap2.results["git.log"].grade, Grade.INFERRED)
        self.assertTrue(any(w.startswith("证据可能串线") for w in infer.infer(snap2, self.conf).header.warnings))

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
        self.assertEqual((replay.trace_no, replay.branch), (3, "batch/3-demo"))
        self.assertEqual(set(replay.results), set(snap.results))
        for key, r in snap.results.items():
            self.assertEqual((r.ok, r.value, r.error), (replay.results[key].ok, replay.results[key].value, replay.results[key].error), key)
        b1, b2 = infer.infer(snap, self.conf), infer.infer(replay, self.conf)
        self.assertEqual([v.status for v in b1.steps], [v.status for v in b2.steps])
        self.assertEqual(b1.header.block, b2.header.block)
        again = Snapshot.from_json(snap.to_json(), snap.tasktable)
        self.assertEqual(again.results["git.log"].value, snap.results["git.log"].value)

    def test_recorded_source_strict_validation(self):
        """R1-18：类型与必需字段非法 → 明确错误；now 非法不取墙钟。"""
        snap = self._snapshot()
        out = os.path.join(self.tmp, "fixture")
        collect.write_snapshot(snap, out)
        raw = json.load(open(os.path.join(out, "snapshot.json"), encoding="utf-8"))

        def write(mutate):
            d = json.loads(json.dumps(raw))
            mutate(d)
            with open(os.path.join(out, "snapshot.json"), "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False)

        def bad_ok(d):
            d["results"]["gh.prs"]["ok"] = "false"

        def missing_value(d):
            d["results"]["git.tags"]["ok"] = True
            d["results"]["git.tags"].pop("value")

        def bad_now(d):
            d["now"] = "昨天"

        def bad_grade(d):
            d["results"]["git.log"]["grade"] = "guess"

        for mutate, needle in ((bad_ok, "ok 必须是布尔值"), (missing_value, "缺 value"), (bad_now, "now 缺失或不是 ISO8601"), (bad_grade, "grade 非法")):
            write(mutate)
            with self.assertRaises(ValueError) as ctx:
                collect.RecordedSource(out)
            self.assertIn(needle, str(ctx.exception))

    def test_missing_tasktable_is_unavailable_not_empty(self):
        """R1-8：夹具缺任务表 → Snapshot 记不可得，头部全未知，模块区为空。"""
        snap = self._snapshot()
        out = os.path.join(self.tmp, "fixture")
        collect.write_snapshot(snap, out)
        os.remove(os.path.join(out, "任务表.md"))
        src = collect.RecordedSource(out)
        replay = collect.collect(out, None, None, self.conf, src.now, src)
        self.assertFalse(replay.tasktable.available)
        self.assertIn("任务表不可读", replay.config["tasktable_error"])
        board = infer.infer(replay, self.conf)
        self.assertEqual(board.modules, [])
        self.assertTrue(board.header.stage.startswith("未知（任务表不可得"))

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
        self.assertEqual([(l, cap) for l, _v, cap in board.header.budget], [("完整门禁", 5)])
        self.assertIn("主机 2 行实", board.header.evidence)

    def test_config_specs_internal_error_is_warning_not_silence(self):
        """R1-22：conf.specs() 抛非兼容性异常 → 记告警，不静默当作无声明。"""
        class Boom:
            def specs(self):
                raise RuntimeError("坏了")
        warnings = []
        self.assertEqual(collect.config_specs(Boom(), warnings), [])
        self.assertEqual(warnings, ["配置声明读取失败：RuntimeError"])

    def test_missing_trace_dir_does_not_crash(self):
        src = collect.LiveSource(self.repo, per_cmd_timeout=5, round_timeout=10, env=self.env)
        snap = collect.collect(self.repo, 42, None, self.conf, None, src)
        self.assertFalse(snap.tasktable.available)
        self.assertTrue(any("找不到 Trace 目录" in w for w in snap.config.get("warnings", [])))
        board = infer.infer(snap, self.conf)
        self.assertTrue(any("找不到 Trace 目录" in w for w in board.header.warnings))
        self.assertTrue(board.header.stage.startswith("未知（任务表不可得"))


class ParserTest(unittest.TestCase):
    def test_gh_json_reducers(self):
        prs = collect._parse_prs(json.dumps([{"number": 1, "title": "t", "state": "MERGED", "mergedBy": {"login": "a"}, "author": {"login": "a"},
                                               "reviews": [{"state": "APPROVED", "author": {"login": "b"}}], "mergeCommit": {"oid": "abc"},
                                               "headRefOid": "deadbeef", "statusCheckRollup": [{"name": "ci", "conclusion": "SUCCESS", "status": "COMPLETED"}],
                                               "body": "x " + "/" + "home" + "/someone/y"}]))
        self.assertEqual((prs[0]["mergedBy"], prs[0]["head_oid"], prs[0]["mergeCommit"]), ("a", "deadbeef", "abc"))
        self.assertEqual(prs[0]["reviews"][0]["state"], "APPROVED")
        self.assertEqual(prs[0]["checks"][0]["conclusion"], "SUCCESS")
        self.assertEqual(prs[0]["body"], "x ~/y")
        long_first = "x" * 300 + " S-2"
        iss = collect._parse_issue(json.dumps({"number": 1, "state": "OPEN", "comments": [{"body": "\n\n" + long_first + "\n正文", "createdAt": "2026-09-05T00:00:00Z",
                                                                                              "author": {"login": "a"}, "url": "https://x/issues/1#issuecomment-77"}]}))
        self.assertEqual(iss["comments"][0]["id"], 77)
        self.assertEqual(iss["comments"][0]["first_line"], long_first)  # R1-4：完整首行，不截 200
        runs = collect._parse_runs(json.dumps([{"databaseId": 5, "conclusion": "success", "headBranch": "main", "updatedAt": "2026-09-05T01:00:00Z"}]))
        self.assertEqual((runs[0]["id"], runs[0]["updatedAt"]), (5, "2026-09-05T01:00:00Z"))
        tags = collect._parse_gh_tags(json.dumps([{"name": "v1", "commit": {"sha": "abc"}}]))
        self.assertEqual(tags, [{"name": "v1", "sha": "abc", "at": "", "at_source": ""}])
        wt = collect._parse_worktree_list("worktree /a/b\nHEAD abc\nbranch refs/heads/main\n\nworktree /c\nHEAD def\ndetached\n")
        self.assertEqual([(w["branch"], w["head"]) for w in wt], [("main", "abc"), ("", "def")])
        blob = collect._parse_tasktable_blob(TABLE)
        self.assertEqual((blob["ids"], blob["checked"], len(blob["quotes"])), (["S-0", "S-1", "S-2"], ["S-0"], 1))

    def test_strict_parsers_reject_malformed(self):
        """R1-17：畸形行不再静默跳过——整键解析失败。"""
        for fn, text in ((collect._parse_git_log, "\x1eabc\x1f2026\n"), (collect._parse_tags, "v1\x1f2026\n"), (collect._parse_branches, "main\x1fabc\n"),
                         (collect._parse_prs, json.dumps([{"title": "no number"}])), (collect._parse_issue, "{}"), (collect._parse_gh_tags, json.dumps([{}])),
                         (collect._parse_runs, json.dumps({"not": "list"}))):
            with self.assertRaises(ValueError, msg=fn.__name__):
                fn(text)
        rec = "\x1e" + "\x1f".join(["a" * 40, "2026-09-05T02:00:00+00:00", "2026-09-05T02:00:00+00:00", "t", "docs(#3): x", ""]) + "\n\ndocs/traces/3-demo/任务表.md\n"
        rec += "\x1e" + "\x1f".join(["b" * 40, "2026-09-05T02:10:00+00:00", "2026-09-05T02:10:00+00:00", "t", "feat: y", "HEAD -> main"]) + "\n\napp.py\ndocs/traces/3-demo/验收.md\n"
        value = collect._parse_git_log(rec, "docs/traces/3-demo")
        self.assertEqual([(c["docs_only"], c["files_n"]) for c in value["commits"]], [(True, 1), (False, 2)])
        self.assertEqual(value["commits"][1]["refs"], "HEAD -> main")

    def test_fail_category(self):
        for error, want in (("退出码 255：ssh: connect to host x", "退出码 255"), ("超时（20 秒）", "超时"), ("解析失败（int）：x", "解析失败"),
                            ("命令不可用：gh（FileNotFoundError）", "命令不可用"), ("", "失败"), ("莫名其妙", "失败")):
            self.assertEqual(infer._fail_category(error), want, error)


if __name__ == "__main__":
    unittest.main()
