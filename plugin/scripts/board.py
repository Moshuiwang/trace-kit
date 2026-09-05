#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trace 看板：从任务表与 git / gh / tmux 证据画出当前 Trace 的进度图（tmux 里的 TUI）。

出处：trace-kit #12 v3（v2 十二条设计裁定不变）；https://github.com/Moshuiwang/lingxi/issues/577（#578–#582、#589）。只读；Python 3 标准库 + gh / git / tmux。
用法见 plugin/skills/board/SKILL.md；接口见 Trace #17 目录下的接口约定。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True  # 账本 R1-28：插件代码可能位于目标仓库内，绝不写 __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from boardlib import collect, config as cfg, infer, model, registry, render, tui  # noqa: E402


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="board.py", allow_abbrev=False, description="Trace 看板（tmux TUI）")
    ap.add_argument("--repo-root", default=".", help="项目仓库根（含 docs/traces/）")
    ap.add_argument("--trace", type=int, help="Trace Issue 号；缺省取 docs/traces/ 下编号最大的目录")
    ap.add_argument("--config", help="证据源配置 TOML")
    ap.add_argument("--branch", help="批次分支；缺省按配置 / PR 推断")
    ap.add_argument("--view", choices=("simple", "complex"), default="simple", help="默认简易版；TUI 内 v 切换")
    ap.add_argument("--dump", action="store_true", help="打印一帧纯文本后退出")
    ap.add_argument("--why", action="store_true", help="与 --dump 连用：追加证据链")
    ap.add_argument("--now", help="报告时刻（ISO8601，UTC）；夹具与回放用")
    ap.add_argument("--width", type=int)
    ap.add_argument("--height", type=int)
    ap.add_argument("--interval", type=int, default=300, help="自动刷新秒数")
    ap.add_argument("--timeout", type=int, default=60, help="整轮采集上限秒数")
    ap.add_argument("--no-anim", action="store_true")
    ap.add_argument("--fixture", help="从夹具目录回放（零网络）")
    ap.add_argument("--record", help="真实采集一次并写 snapshot.json 到该目录")
    ap.add_argument("--registry", action="store_true", help="打印状态 → 证据登记表（Markdown）")
    return ap.parse_args(argv)


def _now(args):
    if args.now:
        ts = model.parse_ts(args.now)
        if ts is None:
            sys.exit("--now 不是 ISO8601：%s" % args.now)
        return ts
    return None  # 由 source 决定：Live → 当前时刻；Recorded → snapshot.now


def build_board(args, conf, source):
    now = _now(args)
    if now is None:
        now = getattr(source, "now", None) or datetime.now(timezone.utc)
    snap = collect.collect(args.repo_root, args.trace, args.branch, conf, now, source)
    board = infer.infer(snap, conf)
    board.validate()
    return board


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.registry:
        missing = registry.check_complete()
        if missing:
            sys.exit("登记表缺状态：%s" % ", ".join(missing))
        sys.stdout.write(registry.render_markdown())
        return 0
    try:
        conf = cfg.load(args.config)
    except cfg.ConfigError as exc:
        sys.exit("证据源配置错误：%s" % exc)
    if args.fixture:
        source = collect.RecordedSource(args.fixture)
        args.repo_root = args.fixture
    else:
        source = collect.LiveSource(args.repo_root, round_timeout=args.timeout)
    if args.record:
        rec, root = os.path.realpath(args.record), os.path.realpath(args.repo_root)
        if rec == root or rec.startswith(root + os.sep):          # 账本 R1-27：引擎对目标仓库只读，不在里面创建文件
            sys.exit("--record 目录不得在目标仓库内（%s 位于 --repo-root 之下）；请换一个仓库外的目录" % args.record)
        now = _now(args) or datetime.now(timezone.utc)
        snap = collect.collect(args.repo_root, args.trace, args.branch, conf, now, source)
        collect.write_snapshot(snap, args.record)
        print("已记录快照：%s" % os.path.join(args.record, "snapshot.json"))
        return 0
    if args.dump:
        board = build_board(args, conf, source)
        W, H = args.width or 150, args.height or 52
        sys.stdout.write(render.dump(board, args.view, W, H, why=args.why))
        return 0
    size = shutil.get_terminal_size((150, 52))
    args.width, args.height = args.width or size.columns, args.height or size.lines
    return tui.run(args, lambda: build_board(args, conf, source), source=source)   # source.cancel() 供看门狗取消旧轮（账本 R2-5）


if __name__ == "__main__":
    sys.exit(main())
