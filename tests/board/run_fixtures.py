#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""夹具回放单测（S-5；接口约定 §10）。

    python3 -B tests/board/run_fixtures.py                 # 全部案例
    python3 -B tests/board/run_fixtures.py -k trace1        # 只跑某个案例

对每个案例跑 `board.py --fixture <dir> --dump --view simple|complex [--why] --width 150 --height 52`，
与 `expected-*.txt` 逐行比对（不一致时打印 unified diff）；再按 make_fixtures.CHECKS 做逐项子串断言
——expected 即使被盲目重生成，人工核对过的断言点也不会跟着一起变绿。
全程零网络：默认只给 `PATH=/usr/bin:/bin`，另有一个用例把 `gh` / `git` / `tmux` 换成必定失败的假脚本再跑一遍。
"""
from __future__ import annotations

import difflib
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BOARD = os.path.join(ROOT, "plugin", "scripts", "board.py")
sys.path.insert(0, HERE)

import make_fixtures as mf  # noqa: E402

WIDTH, HEIGHT = mf.WIDTH, mf.HEIGHT
SAFE_PATH = "/usr/bin:/bin"
EXPECTED = {"simple": "expected-simple.txt", "complex": "expected-complex.txt", "why": "expected-why.txt"}
FAKE = "#!/bin/sh\necho \"夹具回放不许联网：$0\" >&2\nexit 1\n"
_cache: dict = {}


def board_dump(case, view, why, path=SAFE_PATH):
    """跑一帧 dump；`path` 是子进程唯一的 PATH（python3 用绝对路径调用，不受影响）。"""
    key = (case, view, why, path)
    if key in _cache:
        return _cache[key]
    argv = [sys.executable, "-B", BOARD, "--fixture", os.path.join(mf.FIXTURES, case), "--dump",
            "--view", view, "--width", str(WIDTH), "--height", str(HEIGHT)]
    if why:
        argv.append("--why")
    env = dict(os.environ)
    env["PATH"] = path
    proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120, env=env)
    _cache[key] = (proc.returncode, proc.stdout, proc.stderr)
    return _cache[key]


def read_expected(case, kind):
    with open(os.path.join(mf.FIXTURES, case, EXPECTED[kind]), encoding="utf-8") as fh:
        return fh.read()


class FixtureReplay(unittest.TestCase):
    """每个案例三帧（简易版 / 复杂版 / 简易版＋证据链）与 expected 逐行一致。"""

    maxDiff = None

    def compare(self, case, kind):
        view, why = ("simple", True) if kind == "why" else (kind, False)
        code, out, err = board_dump(case, view, why)
        self.assertEqual(code, 0, "board.py 非零退出（%s %s）：%s" % (case, kind, err.strip()[:500]))
        want = read_expected(case, kind)
        if out != want:
            diff = "\n".join(difflib.unified_diff(want.splitlines(), out.splitlines(),
                                                  fromfile="%s/%s" % (case, EXPECTED[kind]), tofile="board.py 实际输出",
                                                  lineterm="", n=2))
            self.fail("夹具 %s 的 %s 帧与 expected 不一致：\n%s" % (case, kind, diff[:8000]))


def _replay(case, kind):
    def test(self):
        self.compare(case, kind)

    test.__doc__ = "夹具 %s · %s 帧" % (case, kind)
    return test


for _case in mf.ALL_CASES:
    for _kind in ("simple", "complex", "why"):
        setattr(FixtureReplay, "test_%s_%s" % (_case.replace("-", "_"), _kind), _replay(_case, _kind))


class Assertions(unittest.TestCase):
    """make_fixtures.CHECKS 的逐项人工核对断言（与 expected 分开，防止盲目重生成掩盖回归）。"""

    def test_checks_cover_every_case(self):
        self.assertEqual(sorted(mf.CHECKS), sorted(mf.ALL_CASES), "每个案例都要有人工核对断言")
        for case in mf.ALL_CASES:
            self.assertTrue(mf.CHECKS[case], "案例 %s 的断言表为空" % case)
            self.assertTrue(mf.SUMMARY.get(case), "案例 %s 缺一句话说明" % case)

    def test_readme_lists_every_check(self):
        for case in mf.ALL_CASES:
            with open(os.path.join(mf.FIXTURES, case, "README.md"), encoding="utf-8") as fh:
                text = fh.read()
            for item, needle, _view, _verdict in mf.CHECKS[case]:
                self.assertIn(item, text, "%s 的 README 缺核对项 %s" % (case, item))
                self.assertIn(needle, text, "%s 的 README 缺断言原文 %s" % (case, item))

    def test_needles_present(self):
        for case in mf.ALL_CASES:
            for item, needle, view, _verdict in mf.CHECKS[case]:
                code, out, err = board_dump(case, "simple" if view == "why" else view, view == "why")
                self.assertEqual(code, 0, err.strip()[:300])
                self.assertIn(needle, out, "夹具 %s 的断言「%s」不成立" % (case, item))


class Hygiene(unittest.TestCase):
    """夹具本身的卫生：被测模块来自本工作树；快照与 expected 不含本机事实。"""

    def test_engine_under_this_worktree(self):
        sys.path.insert(0, os.path.join(ROOT, "plugin", "scripts"))
        from boardlib import infer, model
        for mod in (model, infer):
            self.assertTrue(os.path.abspath(mod.__file__).startswith(ROOT + os.sep),
                            "被测模块不在本工作树：%s" % mod.__file__)

    def test_no_machine_facts(self):
        bad = ("/" + "home" + "/", "bi" + "ai-", "bi" + "plus", "TZ" + "-server")   # 拼接写法：本文件自身不能命中禁词扫描
        for case in mf.ALL_CASES:
            case_dir = os.path.join(mf.FIXTURES, case)
            for name in sorted(os.listdir(case_dir)):
                with open(os.path.join(case_dir, name), encoding="utf-8") as fh:
                    text = fh.read()
                for needle in bad:
                    self.assertNotIn(needle, text, "%s/%s 含本机事实 %r" % (case, name, needle))

    def test_no_trailing_blank(self):
        for case in mf.ALL_CASES:
            case_dir = os.path.join(mf.FIXTURES, case)
            for name in sorted(os.listdir(case_dir)):
                with open(os.path.join(case_dir, name), encoding="utf-8") as fh:
                    for k, line in enumerate(fh.read().splitlines(), 1):
                        self.assertEqual(line, line.rstrip(), "%s/%s 第 %d 行有行尾空白" % (case, name, k))


class NoNetwork(unittest.TestCase):
    """把 gh / git / tmux 换成必定失败的假脚本，输出必须一字不变——证明回放不依赖外部命令。"""

    def test_fake_tools(self):
        with tempfile.TemporaryDirectory(prefix="board-fixture-") as tmp:
            for name in ("gh", "git", "tmux", "ssh", "curl"):
                path = os.path.join(tmp, name)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(FAKE)
                os.chmod(path, 0o755)
            for case in ("trace1-replay", "unknown-gh", "stage-published"):
                code, out, err = board_dump(case, "simple", False, path=tmp)
                self.assertEqual(code, 0, "假 PATH 下 board.py 非零退出（%s）：%s" % (case, err.strip()[:300]))
                self.assertEqual(out, read_expected(case, "simple"), "假 PATH 下 %s 的输出变了" % case)
                self.assertNotIn("不许联网", err, "%s 调用了外部命令" % case)


if __name__ == "__main__":
    unittest.main(verbosity=2)
