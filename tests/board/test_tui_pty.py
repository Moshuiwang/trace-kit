# -*- coding: utf-8 -*-
"""TUI 主循环 pty 测试：固定 150×52、TERM=xterm-256color，起 run_fake_tui.py，写按键 / 发信号、只看新增输出、比对 slave termios。

场景：① 十连按 ↓、v、r、SIGWINCH、q；② 首轮 build 超时 → 看门狗取消旧轮，r 再刷成功，q；③ build 每轮抛异常 → 告警，仍响应按键，Ctrl-C 退出；
④ SIGTERM 受控退出（退出码 143、终端恢复）；⑤ SIGTSTP 前恢复终端、SIGCONT 后重进；⑥ Ctrl-S 流控后 q 仍能退出；⑦ 粘贴 `query` 不当命令。
收尸用 WNOHANG 轮询＋期限后 TERM / KILL（账本 R2-15）；wait_for 只看 mark() 之后的新增输出（账本 R2-16）。
"""
from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import signal
import struct
import sys
import termios
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_FAKE = os.path.join(HERE, "run_fake_tui.py")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ENTER_ALT, LEAVE_ALT = "\x1b[?1049h", "\x1b[?1049l"


class PtySession:
    def __init__(self, extra, cols=150, rows=52):
        pid, fd = pty.fork()
        if pid == 0:  # 子进程
            env = dict(os.environ, TERM="xterm-256color", PYTHONDONTWRITEBYTECODE="1")
            os.execve(sys.executable, [sys.executable, "-B", RUN_FAKE] + extra, env)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        ptn = struct.unpack("I", fcntl.ioctl(fd, getattr(termios, "TIOCGPTN", 0x80045430), b"\0" * 4))[0]   # Linux 常量
        self.slave = os.open("/dev/pts/%d" % ptn, os.O_RDWR | os.O_NOCTTY)   # 父进程也持有 slave：随时可读 termios
        self.pid, self.fd, self.chunks, self.offset, self.status = pid, fd, [], 0, None
        self.final_lflag = None          # finish() 在关 fd 前采样的退出后 lflag
        self.tui_pid = None              # --as-job 时真正跑 TUI 的进程号

    # ---- 输出 ----
    def raw(self) -> str:
        return b"".join(self.chunks).decode("utf-8", "replace")

    def text(self) -> str:
        return ANSI.sub("", self.raw())

    def mark(self):
        """记下当前输出长度：之后的 wait_for 只看新增部分（账本 R2-16）。"""
        self.offset = len(self.raw())

    def _pump(self, wait):
        r, _, _ = select.select([self.fd], [], [], wait)
        if not r:
            return
        try:
            chunk = os.read(self.fd, 65536)
        except OSError:
            chunk = b""
        if chunk:
            self.chunks.append(chunk)

    def _exited(self) -> bool:
        if self.status is None:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                self.status = status
        return self.status is not None

    def wait_for(self, pattern, timeout=15.0, raw=False) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            new = self.raw()[self.offset:] if raw else ANSI.sub("", self.raw()[self.offset:])
            if re.search(pattern, new):
                return new
            if self._exited():
                self._pump(0.2)
                new = self.raw()[self.offset:] if raw else ANSI.sub("", self.raw()[self.offset:])
                if re.search(pattern, new):
                    return new
                raise AssertionError("进程已退出仍未见 %r；新增输出尾部：%r" % (pattern, new[-600:]))
            self._pump(0.1)
        raise AssertionError("等 %r 超时；新增输出尾部：%r" % (pattern, (self.raw()[self.offset:] if raw else ANSI.sub("", self.raw()[self.offset:]))[-600:]))

    # ---- 输入 / 信号 / termios ----
    def write(self, data: bytes):
        os.write(self.fd, data)

    def resize(self, cols, rows):
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def kill(self, sig):
        os.kill(self.tui_pid or self.pid, sig)

    def read_tui_pid(self) -> int:
        m = re.search(r"TUI_PID=(\d+)", self.wait_for(r"TUI_PID=\d+", raw=True))
        self.tui_pid = int(m.group(1))
        return self.tui_pid

    def tui_state(self) -> str:
        """/proc/<tui_pid>/stat 的状态字母：T＝已停住。"""
        try:
            with open("/proc/%d/stat" % (self.tui_pid or self.pid)) as fh:
                return fh.read().rsplit(")", 1)[1].split()[0]
        except OSError:
            return "?"

    def lflag(self) -> int:
        return termios.tcgetattr(self.slave)[3]

    def iflag(self) -> int:
        return termios.tcgetattr(self.slave)[0]

    def wait_stopped(self, timeout=10.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.tui_state() == "T":
                return True
            if self._exited():
                return False
            self._pump(0.1)
        return False

    # ---- 收尸（账本 R2-15：WNOHANG 轮询，期限后 TERM / KILL，任何路径都关 fd）----
    def finish(self, timeout=10.0) -> int:
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and not self._exited():
                self._pump(0.1)
            if self.status is None:
                for sig, grace in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 3.0)):
                    try:
                        os.kill(self.pid, sig)
                    except ProcessLookupError:
                        break
                    until = time.monotonic() + grace
                    while time.monotonic() < until and not self._exited():
                        self._pump(0.1)
                    if self.status is not None:
                        break
                if self.status is None:
                    _, self.status = os.waitpid(self.pid, 0)
                self._pump(0.2)
                raise AssertionError("TUI 在 %.0f 秒内没有退出，已强制收尸（退出状态 %r）" % (timeout, self.status))
            self._pump(0.3)
            self.final_lflag = termios.tcgetattr(self.slave)[3]
            return os.waitstatus_to_exitcode(self.status)
        finally:
            for fd in (self.fd, self.slave):
                try:
                    os.close(fd)
                except OSError:
                    pass


def _no_traceback(tc, s):
    tc.assertNotIn("Traceback", s.text())


class TuiPtyTest(unittest.TestCase):
    def test_keys_view_refresh_resize_quit(self):
        s = PtySession(["--sample", "six", "--view", "complex"])
        s.wait_for(r"第 1 轮")                                    # 首帧
        s.wait_for(r"视图 复杂版")
        self.assertFalse(s.lflag() & termios.ICANON, "进入 TUI 后应为 cbreak")
        self.assertFalse(s.iflag() & termios.IXON, "IXON 应关闭，Ctrl-S 不冻结 pane（R2-2）")
        s.mark()
        s.write(b"\x1b[B" * 10)                                    # 一次写入十个 ↓
        s.wait_for(r"↕ 10/\d+")                                    # 十连按移了十行（只看新增输出）
        s.mark()
        s.write(b"v")
        s.wait_for(r"视图 简易版")                                 # v 后视图切换标记
        s.mark()
        s.write(b"r")
        s.wait_for(r"第 2 轮")                                     # r 触发了新一轮 build
        s.mark()
        s.resize(100, 40)                                          # SIGWINCH：简易版六模块在 40 行放不下 → 新输出里出现滚动指示
        s.wait_for(r"↕ 0/\d+")
        s.wait_for(r"简易版 \d+ 行超一屏")
        s.mark()
        s.write(b"q")
        self.assertEqual(s.finish(), 0)
        self.assertGreater(s.raw().rfind(LEAVE_ALT), s.raw().rfind(ENTER_ALT), "退出必须离开备用屏")
        self.assertTrue(s.final_lflag & termios.ICANON, "退出后 termios 应恢复")
        _no_traceback(self, s)

    def test_watchdog_cancels_old_round_then_refresh_works(self):
        s = PtySession(["--sample", "simple", "--fail", "timeout", "--delay", "30", "--timeout", "1", "--no-anim"])
        s.wait_for(r"采集中")
        s.wait_for(r"刷新超时", timeout=20)                        # 看门狗：1 s + 宽限 5 s；同时 cancel() 旧轮
        s.mark()
        s.write(b"r")
        s.wait_for(r"第 2 轮")                                     # 旧轮被取消结束后，新轮照常起线程并成功
        s.mark()
        s.write(b"q")
        self.assertEqual(s.finish(), 0)
        _no_traceback(self, s)

    def test_build_exception_is_reported_and_ctrl_c_quits(self):
        s = PtySession(["--sample", "simple", "--fail", "exception", "--no-anim"])
        s.wait_for(r"刷新异常：RuntimeError: 注入异常 #1")
        s.mark()
        s.write(b"\x1b[B\x1b[B")
        s.write(b"r")
        s.wait_for(r"注入异常 #2")
        s.mark()
        s.write(b"v")
        s.wait_for(r"视图 复杂版")
        s.write(b"\x03")                                           # Ctrl-C 也要干净退出（退出码 0、终端恢复）
        self.assertEqual(s.finish(), 0)
        self.assertTrue(s.final_lflag & termios.ICANON)
        _no_traceback(self, s)

    def test_r2_1_sigterm_restores_terminal(self):
        s = PtySession(["--sample", "six", "--no-anim"])
        s.wait_for(r"第 1 轮")
        self.assertFalse(s.lflag() & termios.ICANON)
        s.mark()
        s.kill(signal.SIGTERM)
        code = s.finish()
        self.assertEqual(code, 143, "TERM 受控退出：128 + 15")
        self.assertIn(LEAVE_ALT, s.raw()[s.offset:])
        self.assertTrue(s.final_lflag & termios.ICANON, "TERM 后 termios 应恢复")
        self.assertTrue(s.final_lflag & termios.ECHO)
        _no_traceback(self, s)

    def test_r2_1_tstp_restores_and_cont_reenters(self):
        s = PtySession(["--sample", "six", "--no-anim", "--as-job"])   # 前台进程组不孤儿，TSTP 才会真的停
        s.read_tui_pid()
        s.wait_for(r"第 1 轮")
        s.mark()
        s.kill(signal.SIGTSTP)
        self.assertTrue(s.wait_stopped(), "TSTP 后进程应真正停住")
        s._pump(0.3)
        self.assertIn(LEAVE_ALT, s.raw()[s.offset:], "挂起前必须离开备用屏")
        self.assertTrue(s.lflag() & termios.ICANON, "挂起前必须恢复 termios")
        s.mark()
        s.kill(signal.SIGCONT)
        s.wait_for(re.escape(ENTER_ALT), raw=True)                 # 恢复后重进备用屏
        s.wait_for(r"第 1 轮")                                     # 并整屏重画
        self.assertFalse(s.lflag() & termios.ICANON, "恢复后应回到 cbreak")
        s.mark()
        s.write(b"q")
        self.assertEqual(s.finish(), 0)
        self.assertTrue(s.final_lflag & termios.ICANON)
        _no_traceback(self, s)

    def test_r2_2_flow_control_does_not_freeze(self):
        s = PtySession(["--sample", "six"])
        s.wait_for(r"第 1 轮")
        s.mark()
        s.write(b"\x13")                                           # Ctrl-S：IXON 已关，只是个被忽略的按键
        s.write(b"\x1b[B")
        time.sleep(0.3)
        s.write(b"q")
        self.assertEqual(s.finish(timeout=8.0), 0)
        self.assertTrue(s.final_lflag & termios.ICANON)
        _no_traceback(self, s)

    def test_r2_8_paste_is_not_a_command(self):
        s = PtySession(["--sample", "six", "--no-anim"])
        s.wait_for(r"第 1 轮")
        s.mark()
        s.write(b"\x1b[200~query\x1b[201~")                        # 粘贴 query：不得退出、不得切视图
        time.sleep(0.8)
        self.assertFalse(s._exited(), "粘贴载荷里的 q 触发了退出")
        self.assertNotIn("视图 复杂版", s.text()[s.offset:])
        s.write(b"q")
        self.assertEqual(s.finish(), 0)
        _no_traceback(self, s)


class RefresherTest(unittest.TestCase):
    """不经 pty 的看门狗单测：异常回主循环、超时作废＋取消、作废后仍能起新线程、迟到结果被丢弃、结果未消费不起新轮、旧轮未结束不起新轮。"""

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

    def test_watchdog_cancels_and_discards_late_result(self):
        import sample_boards
        build = sample_boards.fake_build("simple", fail="timeout", delay=1.0)
        ref = self.tui.Refresher(build, timeout=0.3, cancel=build.cancel)
        self.assertTrue(ref.start())
        self.assertFalse(ref.start(), "同一时刻只有一轮")
        kind, _ = self._poll_until(ref)
        self.assertEqual(kind, "timeout")
        self.assertEqual(build.cancels[0], 1, "看门狗必须调用 cancel()（R2-5）")
        self.assertFalse(ref.busy())
        self.assertFalse(ref.blocked(), "cancel 后旧轮应已结束")
        build.reset()
        self.assertTrue(ref.start(), "作废后下一轮照常起线程")
        kind, board = self._poll_until(ref)
        self.assertEqual(kind, "ok")
        self.assertIn("第 2 轮", board.header.title)
        time.sleep(0.3)
        self.assertIsNone(ref.poll(), "首轮迟到结果必须被丢弃")
        self.assertEqual(build.calls[0], 2)

    def test_r2_5_no_cancel_blocks_new_round_until_old_ends(self):
        import threading
        import sample_boards
        gate, calls = threading.Event(), [0]

        def build():
            calls[0] += 1
            if calls[0] == 1:
                gate.wait(10)
            return sample_boards.board_simple()

        ref = self.tui.Refresher(build, timeout=0.2)               # 没有 cancel：只能等旧轮自己结束
        self.assertTrue(ref.start())
        kind, text = self._poll_until(ref)
        self.assertEqual(kind, "timeout")
        self.assertIn("上一轮未结束", text)
        self.assertTrue(ref.blocked())
        self.assertFalse(ref.start(), "旧轮未结束不得起新轮（R2-5）")
        gate.set()
        deadline = time.monotonic() + 3
        while ref.blocked() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(ref.blocked())
        self.assertTrue(ref.start())
        kind, _ = self._poll_until(ref)
        self.assertEqual(kind, "ok")

    def test_r2_4_unconsumed_result_is_not_clobbered(self):
        import sample_boards
        build = sample_boards.fake_build("simple")
        ref = self.tui.Refresher(build, timeout=1)
        self.assertTrue(ref.start())
        deadline = time.monotonic() + 3
        while ref.busy() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(ref.busy())
        self.assertFalse(ref.start(), "结果尚未被 poll 消费：不得起新轮把它清掉（R2-4）")
        kind, board = self._poll_until(ref)
        self.assertEqual(kind, "ok")
        self.assertIn("第 1 轮", board.header.title)
        self.assertTrue(ref.start())


if __name__ == "__main__":
    unittest.main()
