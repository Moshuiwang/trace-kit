# -*- coding: utf-8 -*-
"""tmux TUI 主循环（接口约定 §8）。归属：S-3。

必须实现：
    run(args, build: Callable[[], Board]) -> int
        - 后台线程刷新（build() 可能慢）：try/finally 清理线程状态＋看门狗（超过 args.timeout 视为失败，保留上一帧、头部告警）
        - 差异重画（只写有变化的行 / 格），SIGWINCH 重排，动效 0.18s 一格，`a` 开关
        - 键：v 切换视图、r 立即刷新、q / Ctrl-C 退出、↑↓ / PageUp / PageDown / Home / End 滚动（经 keys.KeyParser）
        - 任务表文件变化即时刷新；--interval 定时刷新
"""
from __future__ import annotations


def run(args, build):
    raise NotImplementedError("S-3：TUI 待实现")
