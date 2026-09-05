# -*- coding: utf-8 -*-
"""键盘字节流解析（https://github.com/Moshuiwang/lingxi/issues/580；接口约定 §8）。归属：S-3。

必须实现：
    class KeyParser:
        feed(data: bytes) -> list[str]   # 把一次读到的字节拆成多个按键逐个返回；尾部半个转义序列留到下次 feed 拼接
        识别：\x1b[A/B/C/D、\x1bOA/OB/OC/OD、\x1b[5~/6~、\x1b[H/F、\x1b[1~/4~/7~/8~、\x1bOH/OF、普通可打印字符、\x03
"""
from __future__ import annotations


class KeyParser:
    def feed(self, data: bytes) -> list[str]:
        raise NotImplementedError("S-3：键盘解析待实现")
