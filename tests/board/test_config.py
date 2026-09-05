# -*- coding: utf-8 -*-
"""S-4 单测：证据源配置解析 / 通用 shell provider / 阶段比对（接口约定 §9）。

零网络；只用本机无害命令（printf / false / sleep）。运行：python3 -B -m unittest tests/board/test_config.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from datetime import timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugin", "scripts"))

from boardlib import config as cfg  # noqa: E402
from boardlib.model import Grade, ProviderResult, Val  # noqa: E402

VALID = """
[trace]
number = 123
branch = "batch/123-demo"

[repo]
slug = "owner/repo"

[orchestrator]
tmux_session = "<session>"
window_pattern = "^demo-b[0-9]+$"

[release]
workflow = "<publish-workflow>"

[stages.staging]
label = "预发"
command = "printf 'registry/app:20260101-abc\\n'"
parse = "regex:(?m)^\\\\S+:([^:\\\\s]+)$"
timeout = 20

[stages.production]
command = "printf 'registry/app:20260101-abc\\n'"
parse = "regex:(?m)^\\\\S+:([^:\\\\s]+)$"
timeout = 20
grade = "reported"

[budget.full_gate]
label = "完整门禁"
cap = 5
command = "printf '3\\n'"
parse = "int"
timeout = 25

[budget.docs_only]
label = "纯文档路由"
command = "printf '7\\n'"
parse = "int"

[[evidence]]
key = "prod_healthy"
label = "生产 healthy"
command = "printf 'a (healthy)\\nb\\n'"
parse = "count:healthy"
timeout = 25
"""


class _TmpMixin:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="board-config-")
        self.addCleanup(self.tmp.cleanup)

    def write(self, text: str, name: str = "board.toml") -> str:
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def load_err(self, text: str) -> str:
        with self.assertRaises(cfg.ConfigError) as ctx:
            cfg.load(self.write(text))
        return str(ctx.exception)


class LoadTests(_TmpMixin, unittest.TestCase):
    def test_module_lives_in_this_tree(self):
        self.assertTrue(os.path.abspath(cfg.__file__).startswith(ROOT), cfg.__file__)

    def test_none_is_empty_config(self):
        c = cfg.load(None)
        self.assertIsInstance(c, cfg.Config)
        for name in ("trace_number", "trace_branch", "repo_slug", "tmux_session", "window_pattern", "release_workflow", "path"):
            self.assertIsNone(getattr(c, name), name)
        self.assertEqual(c.stages, {})
        self.assertEqual(c.budgets, [])
        self.assertEqual(c.evidence, [])
        self.assertEqual(c.raw, {})
        self.assertEqual(c.specs(), [])

    def test_valid_config(self):
        path = self.write(VALID)
        c = cfg.load(path)
        self.assertEqual(c.path, path)
        self.assertEqual(c.trace_number, 123)
        self.assertEqual(c.trace_branch, "batch/123-demo")
        self.assertEqual(c.repo_slug, "owner/repo")
        self.assertEqual(c.tmux_session, "<session>")
        self.assertEqual(c.window_pattern, "^demo-b[0-9]+$")
        self.assertEqual(c.release_workflow, "<publish-workflow>")
        self.assertEqual(sorted(c.stages), ["production", "staging"])
        st = c.stages["staging"]
        self.assertEqual((st.key, st.kind, st.label, st.timeout, st.grade, st.cap), ("staging", "stage", "预发", 20, Grade.MEASURED, None))
        self.assertEqual(st.result_key, "config.staging")
        self.assertEqual(c.stages["production"].grade, Grade.REPORTED)
        self.assertEqual(c.stages["production"].label, "production")
        self.assertEqual([b.key for b in c.budgets], ["full_gate", "docs_only"])
        self.assertEqual((c.budgets[0].label, c.budgets[0].cap, c.budgets[0].kind), ("完整门禁", 5, "budget"))
        self.assertEqual((c.budgets[1].cap, c.budgets[1].timeout, c.budgets[1].parse), (None, None, "int"))
        self.assertEqual([e.key for e in c.evidence], ["prod_healthy"])
        self.assertEqual(c.evidence[0].parse, "count:healthy")
        self.assertEqual([s.key for s in c.specs()], ["staging", "production", "full_gate", "docs_only", "prod_healthy"])
        self.assertIsInstance(c.raw, dict)
        self.assertEqual(c.raw["trace"]["number"], 123)

    def test_default_parse_is_text(self):
        c = cfg.load(self.write("[budget.x]\ncommand = 'printf 1'\n"))
        self.assertEqual(c.budgets[0].parse, "text")
        self.assertEqual(c.budgets[0].label, "x")

    def test_template_loads(self):
        c = cfg.load(os.path.join(ROOT, "plugin", "templates", "board.toml"))
        self.assertEqual(sorted(c.stages), ["production", "staging"])
        self.assertTrue(c.budgets and c.evidence)
        self.assertEqual(c.budgets[0].cap, 5)
        self.assertEqual(c.evidence[0].parse, r"count:\(healthy\)")

    def test_unknown_top_level_key(self):
        msg = self.load_err("[foo]\nbar = 1\n")
        self.assertIn("foo", msg)
        self.assertIn("未知键", msg)

    def test_unknown_nested_key_has_path(self):
        msg = self.load_err("[stages.staging]\ncommand = 'x'\ntimeoutt = 1\n")
        self.assertIn("stages.staging.timeoutt", msg)

    def test_unknown_section_key_has_path(self):
        self.assertIn("trace.numberr", self.load_err("[trace]\nnumberr = 1\n"))
        self.assertIn("orchestrator.session", self.load_err("[orchestrator]\nsession = 'x'\n"))

    def test_unknown_evidence_key_has_index(self):
        msg = self.load_err("[[evidence]]\nkey = 'a'\ncommand = 'x'\nfoo = 1\n")
        self.assertIn("evidence[0].foo", msg)

    def test_type_errors_have_path(self):
        self.assertIn("trace.number", self.load_err("[trace]\nnumber = '606'\n"))
        self.assertIn("trace.number", self.load_err("[trace]\nnumber = 0\n"))
        self.assertIn("repo.slug", self.load_err("[repo]\nslug = 5\n"))
        self.assertIn("stages.staging.timeout", self.load_err("[stages.staging]\ncommand = 'x'\ntimeout = true\n"))
        self.assertIn("stages.staging.timeout", self.load_err("[stages.staging]\ncommand = 'x'\ntimeout = '20'\n"))
        self.assertIn("budget.g.cap", self.load_err("[budget.g]\ncommand = 'x'\ncap = -1\n"))
        self.assertIn("stages", self.load_err("stages = 1\n"))
        self.assertIn("evidence", self.load_err("evidence = 1\n"))

    def test_bad_grade_parse_regex(self):
        self.assertIn("stages.staging.grade", self.load_err("[stages.staging]\ncommand = 'x'\ngrade = 'guess'\n"))
        self.assertIn("stages.staging.parse", self.load_err("[stages.staging]\ncommand = 'x'\nparse = 'hex'\n"))
        self.assertIn("stages.staging.parse", self.load_err("[stages.staging]\ncommand = 'x'\nparse = 'regex:('\n"))
        self.assertIn("stages.staging.parse", self.load_err("[stages.staging]\ncommand = 'x'\nparse = 'count:'\n"))
        self.assertIn("orchestrator.window_pattern", self.load_err("[orchestrator]\nwindow_pattern = '['\n"))

    def test_unknown_stage_key(self):
        self.assertIn("stages.qa", self.load_err("[stages.qa]\ncommand = 'x'\n"))

    def test_stage_rejects_cap_and_key(self):
        self.assertIn("stages.staging.cap", self.load_err("[stages.staging]\ncommand = 'x'\ncap = 1\n"))
        self.assertIn("budget.g.key", self.load_err("[budget.g]\ncommand = 'x'\nkey = 'h'\n"))

    def test_missing_command_and_key(self):
        self.assertIn("budget.g.command", self.load_err("[budget.g]\nlabel = 'a'\n"))
        self.assertIn("evidence[0].key", self.load_err("[[evidence]]\ncommand = 'x'\n"))
        self.assertIn("stages.staging.command", self.load_err("[stages.staging]\ncommand = ''\n"))

    def test_duplicate_result_key(self):
        msg = self.load_err("[budget.x]\ncommand = 'a'\n[[evidence]]\nkey = 'x'\ncommand = 'b'\n")
        self.assertIn("evidence[0]", msg)
        self.assertIn("重复", msg)
        self.assertIn("budget.bad key", self.load_err("[budget.'bad key']\ncommand = 'a'\n"))

    def test_missing_file_and_syntax_error(self):
        with self.assertRaises(cfg.ConfigError) as ctx:
            cfg.load(os.path.join(self.tmp.name, "nope.toml"))
        self.assertIn("不存在", str(ctx.exception))
        msg = self.load_err("[trace\nnumber = 1\n")
        self.assertIn("TOML", msg)
        self.assertIn("line", msg)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.p = cfg.ShellProvider(per_cmd_timeout=10)

    def run_cmd(self, command: str, parse: str = "text", timeout=None, **kw) -> ProviderResult:
        return self.p.run(cfg.CommandSpec(key="k", command=command, parse=parse, timeout=timeout, **kw))

    def test_ok_int(self):
        r = self.run_cmd("printf '42\\n'", "int")
        self.assertTrue(r.ok, r.error)
        self.assertEqual(r.value, 42)
        self.assertEqual(r.key, "config.k")
        self.assertEqual(r.cmd, "printf '42\\n'")
        self.assertEqual(r.grade, Grade.MEASURED)
        self.assertEqual(r.error, "")
        self.assertIsNotNone(r.fetched_at)
        self.assertEqual(r.fetched_at.tzinfo, timezone.utc)

    def test_parse_text_default(self):
        r = self.run_cmd("printf '  v1.2 \\n\\n'")
        self.assertEqual((r.ok, r.value), (True, "v1.2"))

    def test_parse_lines(self):
        r = self.run_cmd("printf 'a\\n\\nb  \\n'", "lines")
        self.assertEqual((r.ok, r.value), (True, ["a", "b"]))

    def test_parse_regex(self):
        r = self.run_cmd("printf 'registry/app:20260101-abc\\nother:x\\n'", "regex:(?m)^\\S+:([^:\\s]+)$")
        self.assertEqual((r.ok, r.value), (True, "20260101-abc"))
        r = self.run_cmd("printf 'tag=v9\\n'", "regex:v[0-9]+")
        self.assertEqual((r.ok, r.value), (True, "v9"))
        r = self.run_cmd("printf 'nothing\\n'", "regex:v[0-9]+")
        self.assertFalse(r.ok)
        self.assertIn("解析失败", r.error)

    def test_parse_json(self):
        r = self.run_cmd("printf '{\"a\": {\"b\": [1, {\"c\": 7}]}}'", "json:a.b.1.c")
        self.assertEqual((r.ok, r.value), (True, 7))
        r = self.run_cmd("printf '[1, 2]'", "json:")
        self.assertEqual((r.ok, r.value), (True, [1, 2]))
        r = self.run_cmd("printf '{\"a\": 1}'", "json:a.b")
        self.assertFalse(r.ok)
        self.assertIn("解析失败", r.error)
        r = self.run_cmd("printf 'not json'", "json:a")
        self.assertFalse(r.ok)

    def test_parse_count(self):
        r = self.run_cmd("printf 'x (healthy)\\ny (starting)\\nz (healthy)\\n'", "count:healthy")
        self.assertEqual((r.ok, r.value), (True, 2))
        r = self.run_cmd("printf ''", "count:healthy")
        self.assertEqual((r.ok, r.value), (True, 0))
        r = self.run_cmd("printf 'Up 2h (healthy)\\nUp 1h (unhealthy)\\nUp 1m (health: starting)\\n'", r"count:\(healthy\)")
        self.assertEqual((r.ok, r.value), (True, 1), "unhealthy 不得计入 healthy")

    def test_parse_int_failure(self):
        r = self.run_cmd("printf 'abc\\n'", "int")
        self.assertFalse(r.ok)
        self.assertIn("解析失败（int）", r.error)
        self.assertIsNone(r.value)

    def test_nonzero_exit(self):
        r = self.run_cmd("false")
        self.assertFalse(r.ok)
        self.assertIn("退出码 1", r.error)
        self.assertIsNone(r.value)

    def test_stderr_tail_in_error(self):
        r = self.run_cmd("printf 'boom here\\n' >&2 && exit 3")
        self.assertFalse(r.ok)
        self.assertIn("退出码 3", r.error)
        self.assertIn("boom here", r.error)

    def test_missing_binary(self):
        r = self.run_cmd("no-such-command-board-xyz")
        self.assertFalse(r.ok)
        self.assertIn("退出码 127", r.error)

    def test_pipefail(self):
        r = self.run_cmd("false | true")
        self.assertFalse(r.ok)
        r = self.run_cmd("printf 'a\\nb\\n' | wc -l", "int")
        self.assertEqual((r.ok, r.value), (True, 2))

    def test_timeout(self):
        t0 = time.monotonic()
        r = self.run_cmd("sleep 3", timeout=1)
        elapsed = time.monotonic() - t0
        self.assertFalse(r.ok)
        self.assertIn("超时", r.error)
        self.assertIn("1 秒", r.error)
        self.assertLess(elapsed, 2.5, "超时后必须立即返回")

    def test_timeout_kills_process_group(self):
        t0 = time.monotonic()
        r = self.run_cmd("sleep 3; true", timeout=1)
        elapsed = time.monotonic() - t0
        self.assertFalse(r.ok)
        self.assertIn("超时", r.error)
        self.assertLess(elapsed, 2.5, "子进程组未被杀干净，管道拖住了返回")

    def test_provider_default_timeout(self):
        r = cfg.ShellProvider(per_cmd_timeout=1).run(cfg.CommandSpec(key="k", command="sleep 3"))
        self.assertFalse(r.ok)
        self.assertIn("超时（1 秒）", r.error)

    def test_grade_and_key_override(self):
        r = self.p.run(cfg.CommandSpec(key="k", command="printf 1", parse="int", grade=Grade.REPORTED), "config.custom")
        self.assertEqual((r.ok, r.value, r.grade, r.key), (True, 1, Grade.REPORTED, "config.custom"))

    def test_stdin_is_closed(self):
        r = self.run_cmd("cat", "text")
        self.assertTrue(r.ok, r.error)
        self.assertEqual(r.value, "")


class CompareTagTests(unittest.TestCase):
    def result(self, value, ok=True, grade=Grade.MEASURED) -> ProviderResult:
        return ProviderResult("config.staging", ok, value, "" if ok else "退出码 255", "ssh -n <host> …", None, grade)

    def test_equal(self):
        v = cfg.compare_tag("20260101-abc", self.result("20260101-abc"))
        self.assertIsInstance(v, Val)
        self.assertEqual((v.value, v.available, v.source, v.grade), (True, True, "config.staging", Grade.MEASURED))
        self.assertEqual(v.text(), "True实")

    def test_not_equal(self):
        v = cfg.compare_tag("20260101-abc", self.result("20260101-zzz"))
        self.assertEqual((v.value, v.available), (False, True))

    def test_unavailable_when_command_failed(self):
        v = cfg.compare_tag("20260101-abc", self.result(None, ok=False, grade=Grade.REPORTED))
        self.assertFalse(v.available)
        self.assertEqual(v.grade, Grade.REPORTED)
        self.assertEqual(v.text(), "未知")

    def test_unavailable_when_published_unknown(self):
        self.assertFalse(cfg.compare_tag(None, self.result("x")).available)
        self.assertFalse(cfg.compare_tag("", self.result("x")).available)
        self.assertFalse(cfg.compare_tag("x", self.result("")).available)
        self.assertFalse(cfg.compare_tag("x", self.result([])).available)
        self.assertFalse(cfg.compare_tag("x", None).available)

    def test_list_value_uses_first_and_strips(self):
        self.assertTrue(cfg.compare_tag(" v1 ", self.result(["", "v1\n", "v2"])).value)
        self.assertFalse(cfg.compare_tag("v1", self.result(["v2", "v1"])).value)


if __name__ == "__main__":
    unittest.main()
