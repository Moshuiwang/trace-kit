# -*- coding: utf-8 -*-
"""渲染（接口约定 §8）。归属：S-3。样稿 sample/board-v0 的 Canvas / Lines / layout / draw_graph 可演化迁入。

必须实现：
    frame(board: Board, view: str, W: int, H: int, scroll: int, phase: int = 0) -> tuple[list[str], list, int]
        （返回 ANSI 行、动效单元、可视高度；与样稿 render() 同形）
    dump(board: Board, view: str, W: int = 150, H: int = 52, why: bool = False) -> str   # 纯文本，无 ANSI
    入口先调用 board.validate()
"""
from __future__ import annotations


def dump(board, view, W=150, H=52, why=False):
    raise NotImplementedError("S-3：渲染待实现")
