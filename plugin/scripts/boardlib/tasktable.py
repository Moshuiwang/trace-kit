# -*- coding: utf-8 -*-
"""任务表解析（接口约定 §5）。归属：S-2。

必须实现：
    parse(text: str, path: str = "") -> TaskTable
        - `## ` 章节 → Section；Step 行 → Step（编号、勾选、标题、标签块 t:/needs:/own:/est:、指针）
        - 无法解析的 `- [` 行进 unparsed；超长行进 overlong；绝不抛异常退出
    default_needs(table: TaskTable) -> None   # 无 needs: 标签时按章节顺序补默认依赖
"""
from __future__ import annotations

from .model import TaskTable


def parse(text: str, path: str = "") -> TaskTable:
    raise NotImplementedError("S-2：任务表解析待实现")
