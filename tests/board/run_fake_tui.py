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
    a = ap.parse_args(argv)
    a.trace, a.fixture = None, None
    return tui.run(a, sample_boards.fake_build(a.sample, delay=a.delay, fail=a.fail))


if __name__ == "__main__":
    sys.exit(main())
