# -*- coding: utf-8 -*-
"""TUI 主循环 pty 测试：固定 150×52、TERM=xterm-256color，起 run_fake_tui.py，写按键、看输出、看退出码。

三组：① 正常：十连按 ↓、v、r、q；② 首轮 build 超时 → 看门狗告警，r 再刷成功，q；③ build 每轮抛异常 → 告警，r 再告警，q。
总时长目标 < 30 秒。
"""
from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import struct
import sys
import termios
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_FAKE = os.path.join(HERE, "run_fake_tui.py")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class PtySession:
    def __init__(self, extra, cols=150, rows=52):
        pid, fd = pty.fork()
        if pid == 0:  # 子进程
            env = dict(os.environ, TERM="xterm-256color", PYTHONDONTWRITEBYTECODE="1")
            os.execve(sys.executable, [sys.executable, "-B", RUN_FAKE] + extra, env)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.pid, self.fd, self.chunks, self.eof = pid, fd, [], False

    def text(self) -> str:
        return ANSI.sub("", b"".join(self.chunks).decode("utf-8", "replace"))

    def _pump(self, wait):
        r, _, _ = select.select([self.fd], [], [], wait)
        if not r:
            return
        try:
            chunk = os.read(self.fd, 65536)
        except OSError:
            chunk = b""
        if not chunk:
            self.eof = True
        else:
            self.chunks.append(chunk)

    def wait_for(self, pattern, timeout=15.0) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not self.eof:
            if re.search(pattern, self.text()):
                return self.text()
            self._pump(0.1)
        raise AssertionError("等 %r 超时；输出尾部：%r" % (pattern, self.text()[-800:]))

    def write(self, data: bytes):
        os.write(self.fd, data)

    def resize(self, cols, rows):
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def finish(self, timeout=10.0) -> int:
        deadline = time.monotonic() + timeout
        while not self.eof and time.monotonic() < deadline:
            self._pump(0.1)
        _, status = os.waitpid(self.pid, 0)
        os.close(self.fd)
        return os.waitstatus_to_exitcode(status)


class TuiPtyTest(unittest.TestCase):
    def test_keys_view_refresh_quit(self):
        s = PtySession(["--sample", "six", "--view", "complex"])
        s.wait_for(r"第 1 轮")                          # 首帧
        s.wait_for(r"视图 复杂版")
        s.write(b"\x1b[B" * 10)                          # 一次写入十个 ↓
        s.wait_for(r"↕ 10/\d+")                          # 十连按移了十行
        s.write(b"v")
        s.wait_for(r"视图 简易版")                       # v 后视图切换标记
        s.write(b"r")
        s.wait_for(r"第 2 轮")                           # r 触发了新一轮 build
        s.resize(100, 40)                                # SIGWINCH：简易版六模块在 40 行放不下 → 出现滚动指示
        s.wait_for(r"↕ 0/\d+")
        s.write(b"q")
        self.assertEqual(s.finish(), 0)
        out = s.text()
        self.assertIn("\x1b[?1049l", b"".join(s.chunks).decode("utf-8", "replace"))   # 退出恢复主屏
        self.assertNotIn("Traceback", out)

    def test_watchdog_timeout_then_refresh_works(self):
        s = PtySession(["--sample", "simple", "--fail", "timeout", "--delay", "30", "--timeout", "1", "--no-anim"])
        s.wait_for(r"采集中")
        s.wait_for(r"刷新超时", timeout=20)              # 看门狗：1 s + 宽限 5 s
        s.write(b"r")
        s.wait_for(r"第 2 轮")                           # 下一轮照常起线程并成功
        s.write(b"q")
        self.assertEqual(s.finish(), 0)
        self.assertNotIn("Traceback", s.text())

    def test_build_exception_is_reported_and_keys_still_work(self):
        s = PtySession(["--sample", "simple", "--fail", "exception", "--no-anim"])
        s.wait_for(r"刷新异常：RuntimeError: 注入异常 #1")
        s.write(b"\x1b[B\x1b[B")
        s.write(b"r")
        s.wait_for(r"注入异常 #2")
        s.write(b"v")
        s.wait_for(r"视图 复杂版")
        s.write(b"\x03")                                # Ctrl-C 也要干净退出（退出码 0、终端恢复）
        self.assertEqual(s.finish(), 0)
        self.assertNotIn("Traceback", s.text())


class RefresherTest(unittest.TestCase):
    """不经 pty 的看门狗单测：异常回主循环、超时作废、作废后仍能起新线程、迟到结果被丢弃。"""

    def setUp(self):
        sys.path.insert(0, os.path.join(HERE, "..", "..", "plugin", "scripts"))
        sys.path.insert(0, HERE)
        from boardlib import tui
        self.tui = tui
        self.grace = tui.WATCHDOG_GRACE
        tui.WATCHDOG_GRACE = 0.2

    def tearDown(self):
        self.tui.WATCHDOG_GRACE = self.grace

    def _poll_until(self, ref, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            r = ref.poll()
            if r is not None:
                return r
            time.sleep(0.02)
        self.fail("poll 超时")

    def test_exception_then_ok(self):
        import sample_boards
        build = sample_boards.fake_build("simple", fail="exception-once")
        ref = self.tui.Refresher(build, timeout=1)
        self.assertTrue(ref.start())
        kind, text = self._poll_until(ref)
        self.assertEqual(kind, "error")
        self.assertIn("注入异常 #1", text)
        self.assertFalse(ref.busy(), "finally 必须清句柄")
        self.assertTrue(ref.start())
        kind, board = self._poll_until(ref)
        self.assertEqual(kind, "ok")
        self.assertIn("第 2 轮", board.header.title)

    def test_watchdog_discards_late_result(self):
        import sample_boards
        build = sample_boards.fake_build("simple", fail="timeout", delay=1.0)
        ref = self.tui.Refresher(build, timeout=0.3)
        self.assertTrue(ref.start())
        self.assertFalse(ref.start(), "同一时刻只有一轮")
        kind, _ = self._poll_until(ref)
        self.assertEqual(kind, "timeout")
        self.assertFalse(ref.busy())
        self.assertTrue(ref.start(), "作废后下一轮照常起线程")
        kind, board = self._poll_until(ref)
        self.assertEqual(kind, "ok")
        self.assertIn("第 2 轮", board.header.title)
        time.sleep(1.2)                                  # 首轮迟到返回：轮次号不符，必须被丢弃
        self.assertIsNone(ref.poll())
        self.assertEqual(build.calls[0], 2)


if __name__ == "__main__":
    unittest.main()
