# -*- coding: utf-8 -*-
"""状态推断（接口约定 §7）。归属：S-2。只判断、不取数据；每个判定都要留 Why。

必须实现：
    infer(snapshot: Snapshot, conf) -> Board
        - 步骤九色＋未知（§7.1）、模块聚合与三行文案（§7.2）、轮数与边框档位、时长（§7.3）、
          五级阶段（§7.4）、头六项（§7.5）、来源角标、Why 证据链（§7.6）
        - 末尾调用 board.validate()
"""
from __future__ import annotations


def infer(snapshot, conf):
    raise NotImplementedError("S-2：状态推断待实现")
