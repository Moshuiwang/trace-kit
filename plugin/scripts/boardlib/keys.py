# -*- coding: utf-8 -*-
"""键盘字节流解析（https://github.com/Moshuiwang/lingxi/issues/580；接口约定 §8）。归属：S-3。

    parser = KeyParser()
    parser.feed(b"\\x1b[B\\x1b[B")  -> ["DOWN", "DOWN"]      # 一次读到多个序列逐个分发
    parser.feed(b"\\x1b[") ; parser.feed(b"B") -> [] ; ["DOWN"]   # 半个序列跨两次读拼接
    parser.flush()                 -> 只在半序列**过期**后才把它按「孤立 Esc ＋ 普通字符」清出
    parser.wait_hint()             -> 距离下一个期限还有几秒（None＝没有悬而未决的字节），主循环据此缩短 select

按键名：UP DOWN LEFT RIGHT PGUP PGDN HOME END ESC ENTER TAB BACKSPACE CTRL_C（及其他 CTRL_x）；普通可打印字符原样返回
（含 UTF-8 多字节）；bracketed paste 的整段载荷收成一个 "PASTE" 事件（载荷丢弃、不当命令）。

半序列期限（账本 R2-7）：期限是**固定的字节间隔**，与主循环的动画 tick 无关——
    - 孤立 `\\x1b`：ESC_DEADLINE（50 ms）内没有后续字节才算 Esc 键（它可能是被截断的转义序列开头）；
    - 已确认的前缀（`\\x1b[` / `\\x1bO` / `\\x1b]` …）：每收到一个字节把 SEQ_DEADLINE（500 ms）重新起算；过期才由 flush 清出。
    识别不了的完整序列（例如 `\\x1b[1;5A`）静默丢弃，不会污染成普通字符。
有界消费（账本 R2-8 / R2-9）：CSI 超过 CSI_MAX 字节仍无终结字节、OSC / DCS / APC / PM / SOS 超过 STRING_MAX 仍无 BEL / ST，
整段丢弃并重置；粘贴载荷超过 PASTE_MAX 只丢弃载荷，仍等到结束标记。
"""
from __future__ import annotations

import codecs
import time

ESC_DEADLINE = 0.05      # 孤立 Esc 的等待期限（秒）
SEQ_DEADLINE = 0.5       # 已确认转义前缀的字节间期限（秒）
PASTE_DEADLINE = 2.0     # 粘贴没有结束标记时的字节间期限（秒）
CSI_MAX = 64             # CSI / SS3 最大长度（字节）
STRING_MAX = 1024        # OSC / DCS / APC / PM / SOS 最大长度（字节）
PASTE_MAX = 65536        # 粘贴载荷上限（字节）；超过只丢弃载荷

CSI_FINAL = {b"A": "UP", b"B": "DOWN", b"C": "RIGHT", b"D": "LEFT", b"H": "HOME", b"F": "END"}
CSI_TILDE = {b"1": "HOME", b"7": "HOME", b"4": "END", b"8": "END", b"5": "PGUP", b"6": "PGDN"}
SS3 = {b"A": "UP", b"B": "DOWN", b"C": "RIGHT", b"D": "LEFT", b"H": "HOME", b"F": "END"}
CONTROL = {3: "CTRL_C", 13: "ENTER", 10: "ENTER", 9: "TAB", 127: "BACKSPACE", 8: "BACKSPACE", 27: "ESC"}
STRING_INTRO = {0x5D, 0x50, 0x5F, 0x5E, 0x58}    # ] P _ ^ X → OSC DCS APC PM SOS
PASTE_BEGIN, PASTE_END = b"\x1b[200~", b"\x1b[201~"
ESC = 0x1B


def _csi_name(params: bytes, final: bytes):
    if final == b"~":
        return CSI_TILDE.get(params.split(b";")[0])
    if params in (b"", b"1"):
        return CSI_FINAL.get(final)
    return None


class KeyParser:
    def __init__(self, clock=time.monotonic):
        self.buf = b""
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.clock = clock
        self.pending_since = None     # 缓冲区里半序列最后一个字节到达的时刻
        self.paste = None             # 粘贴模式：已收到的载荷长度（int）；None＝不在粘贴中

    # ---------- 对外 ----------
    def feed(self, data: bytes, now=None) -> list[str]:
        now = self.clock() if now is None else now
        self.buf += data
        keys = []
        while self.buf:
            if self.paste is not None:
                if not self._paste_step(keys):
                    break
                continue
            if self.buf[0] != ESC:
                end = self.buf.find(b"\x1b")
                chunk, self.buf = (self.buf, b"") if end < 0 else (self.buf[:end], self.buf[end:])
                keys.extend(self._plain(chunk))
                continue
            key, used = self._escape(self.buf)
            if used == 0:                       # 半个序列：留到下次 feed
                break
            self.buf = self.buf[used:]
            if key == "PASTE_BEGIN":
                self.paste = 0
            elif key is not None:
                keys.append(key)
        self.pending_since = now if (self.buf or self.paste is not None) else None
        return keys

    def flush(self, now=None) -> list[str]:
        """悬而未决的字节过了期限才清出（孤立 Esc → "ESC"，其余按普通字符）；未过期返回 []。"""
        now = self.clock() if now is None else now
        if self.paste is not None:
            if self.pending_since is not None and now - self.pending_since >= PASTE_DEADLINE:
                self.paste, self.buf, self.pending_since = None, b"", None
                return ["PASTE"]
            return []
        if not self.buf:
            return []
        if self.pending_since is not None and now - self.pending_since < self._deadline():
            return []
        buf, self.buf, self.pending_since = self.buf, b"", None
        keys = []
        while buf:
            if buf[0] == ESC:
                keys.append("ESC")
                buf = buf[1:]
            else:
                end = buf.find(b"\x1b")
                chunk, buf = (buf, b"") if end < 0 else (buf[:end], buf[end:])
                keys.extend(self._plain(chunk))
        return keys

    def wait_hint(self, now=None):
        """距离下一个期限的秒数；没有悬而未决的字节返回 None。"""
        if self.pending_since is None or (not self.buf and self.paste is None):
            return None
        now = self.clock() if now is None else now
        limit = PASTE_DEADLINE if self.paste is not None else self._deadline()
        return max(0.0, limit - (now - self.pending_since))

    # ---------- 内部 ----------
    def _deadline(self) -> float:
        return ESC_DEADLINE if self.buf == b"\x1b" else SEQ_DEADLINE

    def _paste_step(self, keys) -> bool:
        """粘贴模式消费缓冲区；返回 False 表示还没收到结束标记（等下次 feed）。"""
        end = self.buf.find(PASTE_END)
        if end < 0:
            keep = len(PASTE_END) - 1                      # 结束标记可能被截断在尾部
            self.paste += max(0, len(self.buf) - keep)
            self.buf = self.buf[-keep:] if len(self.buf) > keep else self.buf
            if self.paste > PASTE_MAX:                     # 超长：只记长度，不留载荷
                self.paste = PASTE_MAX + 1
            return False
        self.buf = self.buf[end + len(PASTE_END):]
        self.paste = None
        keys.append("PASTE")
        return True

    def _plain(self, chunk: bytes) -> list[str]:
        out = []
        for ch in self.decoder.decode(chunk):
            code = ord(ch)
            if code in CONTROL:
                out.append(CONTROL[code])
            elif code < 32:
                out.append("CTRL_%s" % chr(code + 64))
            elif code == 0xFFFD:
                continue
            else:
                out.append(ch)
        return out

    @staticmethod
    def _escape(buf: bytes):
        """解析以 ESC 开头的缓冲区：返回 (按键名或 None, 消耗字节数)；消耗 0 表示序列未完整。"""
        if len(buf) == 1:
            return None, 0
        b1 = buf[1]
        if b1 == 0x5B:                                     # CSI
            if buf.startswith(PASTE_BEGIN):
                return "PASTE_BEGIN", len(PASTE_BEGIN)
            k = 2
            while k < len(buf) and 0x30 <= buf[k] <= 0x3F:      # 参数字节
                k += 1
            while k < len(buf) and 0x20 <= buf[k] <= 0x2F:      # 中间字节
                k += 1
            if k >= len(buf):
                return (None, len(buf)) if len(buf) > CSI_MAX else (None, 0)   # 超长无终结：整段丢弃
            if not (0x40 <= buf[k] <= 0x7E):                    # 不是合法终结字节：当孤立 Esc
                return "ESC", 1
            return _csi_name(buf[2:k], buf[k:k + 1]), k + 1
        if b1 == 0x4F:                                     # SS3
            if len(buf) < 3:
                return None, 0
            if 0x40 <= buf[2] <= 0x7E:
                return SS3.get(buf[2:3]), 3
            return "ESC", 1
        if b1 in STRING_INTRO:                             # OSC / DCS / APC / PM / SOS：吃到 BEL 或 ST
            k = 2
            while k < len(buf):
                if buf[k] == 0x07:
                    return None, k + 1
                if buf[k] == ESC:
                    if k + 1 < len(buf):
                        return (None, k + 2) if buf[k + 1] == 0x5C else ("ESC", 1)
                    break
                k += 1
            return (None, len(buf)) if len(buf) > STRING_MAX else (None, 0)
        return "ESC", 1        # ESC 后面接普通字节：先发 ESC，后面的字节照常解析
