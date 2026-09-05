#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 sample_boards 的假 build() 跑 tui.run（test_tui_pty.py 用 pty 起它；也可在 tmux 里手工试）。

    python3 -B tests/board/run_fake_tui.py --sample six --view complex
    python3 -B tests/board/run_fake_tui.py --fail timeout --delay 30 --timeout 1 --no-anim   # 看门狗告警后按 r 再刷一轮
    python3 -B tests/board/run_fake_tui.py --fail exception --no-anim                        # 每轮抛异常，头部告警、仍响应按键

不读任何仓库文件（--repo-root 指向不存在的目录，任务表 mtime 监视自然关闭）。
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "plugin", "scripts"))
sys.path.insert(0, HERE)

import sample_boards  # noqa: E402
from boardlib import tui  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--sample", default="six", choices=sorted(sample_boards.BOARDS))
    ap.add_argument("--delay", type=float, default=0.0, help="每轮 build 睡眠秒数（--fail timeout 时只在首轮睡）")
    ap.add_argument("--fail", default="none", choices=("none", "exception", "exception-once", "timeout"))
    ap.add_argument("--view", choices=("simple", "complex"), default="simple")
    ap.add_argument("--width", type=int, default=150)
    ap.add_argument("--height", type=int, default=52)
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--no-anim", action="store_true")
    ap.add_argument("--repo-root", default=os.path.join(os.devnull, "nowhere"))
    ap.add_argument("--as-job", action="store_true",
                    help="模拟 shell 作业控制：TUI 在子进程里自成前台进程组，本进程留在会话里等它（pty 直接起的进程是孤儿进程组，内核会丢弃 TSTP）")
    a = ap.parse_args(argv)
    a.trace, a.fixture = None, None
    if a.as_job:
        code = _as_job()
        if code is not None:
            return code
    build = sample_boards.fake_build(a.sample, delay=a.delay, fail=a.fail)
    return tui.run(a, build, source=build)          # build.cancel() 充当 LiveSource.cancel()（账本 R2-5）


def _as_job():
    """父进程：把子进程放进新进程组并设为终端前台，打印 TUI_PID 后等它退出；子进程：等自己成为前台后返回 None 继续跑 TUI。"""
    import signal
    import time
    fd = sys.stdin.fileno()
    pid = os.fork()
    if pid == 0:
        os.setpgid(0, 0)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and os.tcgetpgrp(fd) != os.getpgrp():
            time.sleep(0.01)
        return None
    os.setpgid(pid, pid)
    signal.signal(signal.SIGTTOU, signal.SIG_IGN)
    os.tcsetpgrp(fd, pid)
    sys.stdout.write("TUI_PID=%d\n" % pid)
    sys.stdout.flush()
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


if __name__ == "__main__":
    sys.exit(main())
