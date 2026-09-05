# -*- coding: utf-8 -*-
"""键盘字节流解析（https://github.com/Moshuiwang/lingxi/issues/580；接口约定 §8）。归属：S-3。

    parser = KeyParser()
    parser.feed(b"\\x1b[B\\x1b[B")  -> ["DOWN", "DOWN"]      # 一次读到多个序列逐个分发
    parser.feed(b"\\x1b[") ; parser.feed(b"B") -> [] ; ["DOWN"]   # 半个序列跨两次读拼接
    parser.flush()                 -> 把悬而未决的字节按「孤立 Esc」清出（主循环在 select 超时时调用）

按键名：UP DOWN LEFT RIGHT PGUP PGDN HOME END ESC ENTER TAB BACKSPACE CTRL_C（及其他 CTRL_x）；普通可打印字符原样返回（含 UTF-8 多字节）。

孤立 Esc 的策略：单独一个 `\\x1b` 结尾时**先留在缓冲区**（它可能是被截断的转义序列开头）；
下一次 feed 若接的不是 `[` / `O`，先发 "ESC" 再照常解析后面的字节；若一直没有后续字节，主循环在 select 超时后调 `flush()`
把它作为 "ESC" 发出。识别不了的完整序列（例如 `\\x1b[1;5A`）静默丢弃，不会污染成普通字符。
"""
from __future__ import annotations

import codecs

CSI_FINAL = {
    b"A": "UP", b"B": "DOWN", b"C": "RIGHT", b"D": "LEFT", b"H": "HOME", b"F": "END",
}
CSI_TILDE = {b"1": "HOME", b"7": "HOME", b"4": "END", b"8": "END", b"5": "PGUP", b"6": "PGDN"}
SS3 = {b"A": "UP", b"B": "DOWN", b"C": "RIGHT", b"D": "LEFT", b"H": "HOME", b"F": "END"}
CONTROL = {3: "CTRL_C", 13: "ENTER", 10: "ENTER", 9: "TAB", 127: "BACKSPACE", 8: "BACKSPACE", 27: "ESC"}


def _csi_name(params: bytes, final: bytes):
    if final == b"~":
        return CSI_TILDE.get(params.split(b";")[0])
    if params in (b"", b"1"):
        return CSI_FINAL.get(final)
    return None


class KeyParser:
    def __init__(self):
        self.buf = b""
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def feed(self, data: bytes) -> list[str]:
        self.buf += data
        keys = []
        while self.buf:
            b0 = self.buf[0]
            if b0 != 0x1B:
                end = self.buf.find(b"\x1b")
                chunk, self.buf = (self.buf, b"") if end < 0 else (self.buf[:end], self.buf[end:])
                keys.extend(self._plain(chunk))
                continue
            key, used = self._escape(self.buf)
            if used == 0:          # 半个序列：留到下次 feed
                break
            if key is not None:
                keys.append(key)
            self.buf = self.buf[used:]
        return keys

    def flush(self) -> list[str]:
        """select 超时时调用：缓冲区里悬着的 Esc / 半序列按「孤立 Esc ＋ 普通字符」清出。"""
        if not self.buf:
            return list(self._plain(b""))
        buf, self.buf = self.buf, b""
        keys = []
        while buf:
            if buf[0] == 0x1B:
                keys.append("ESC")
                buf = buf[1:]
            else:
                end = buf.find(b"\x1b")
                chunk, buf = (buf, b"") if end < 0 else (buf[:end], buf[end:])
                keys.extend(self._plain(chunk))
        return keys

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
        b1 = buf[1:2]
        if b1 == b"[":
            k = 2
            while k < len(buf) and 0x30 <= buf[k] <= 0x3F:      # 参数字节
                k += 1
            while k < len(buf) and 0x20 <= buf[k] <= 0x2F:      # 中间字节
                k += 1
            if k >= len(buf):
                return None, 0
            final = buf[k:k + 1]
            if not (0x40 <= buf[k] <= 0x7E):                    # 不是合法终结字节：当孤立 Esc
                return "ESC", 1
            params = buf[2:k]
            return _csi_name(params, final), k + 1
        if b1 == b"O":
            if len(buf) < 3:
                return None, 0
            if 0x40 <= buf[2] <= 0x7E:
                return SS3.get(buf[2:3]), 3
            return "ESC", 1
        return "ESC", 1        # ESC 后面接普通字节：先发 ESC，后面的字节照常解析
