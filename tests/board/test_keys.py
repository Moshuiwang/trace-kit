# -*- coding: utf-8 -*-
"""键盘字节流解析单测（https://github.com/Moshuiwang/lingxi/issues/580 三条关卡＋孤立 Esc 策略）。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugin", "scripts"))

from boardlib.keys import KeyParser  # noqa: E402


class KeyParserTest(unittest.TestCase):
    def test_ten_downs_in_one_read(self):
        self.assertEqual(KeyParser().feed(b"\x1b[B" * 10), ["DOWN"] * 10)

    def test_half_sequence_across_two_reads(self):
        p = KeyParser()
        self.assertEqual(p.feed(b"\x1b["), [])
        self.assertEqual(p.feed(b"B"), ["DOWN"])
        self.assertEqual(p.feed(b"\x1b[5"), [])
        self.assertEqual(p.feed(b"~\x1b[A"), ["PGUP", "UP"])
        self.assertEqual(p.feed(b"\x1b"), [])
        self.assertEqual(p.feed(b"OB"), ["DOWN"])

    def test_lone_escape_policy(self):
        """孤立 Esc：先留缓冲；后续不是 [ / O 就先发 ESC 再解析；一直没后续则 flush 发 ESC。"""
        p = KeyParser()
        self.assertEqual(p.feed(b"\x1b"), [])
        self.assertEqual(p.flush(), ["ESC"])
        self.assertEqual(p.feed(b"\x1b"), [])
        self.assertEqual(p.feed(b"q"), ["ESC", "q"])
        self.assertEqual(p.feed(b"\x1b\x1b[B"), ["ESC", "DOWN"])
        self.assertEqual(p.feed(b"\x1b["), [])
        self.assertEqual(p.flush(), ["ESC", "["])

    def test_plain_and_control(self):
        self.assertEqual(KeyParser().feed(b"qv ra\x03\r\t\x7f"), ["q", "v", " ", "r", "a", "CTRL_C", "ENTER", "TAB", "BACKSPACE"])
        self.assertEqual(KeyParser().feed("中q".encode()), ["中", "q"])
        p = KeyParser()
        self.assertEqual(p.feed("中".encode()[:1]), [])
        self.assertEqual(p.feed("中".encode()[1:]), ["中"])

    def test_navigation_variants(self):
        seq = b"\x1b[5~\x1b[6~\x1b[H\x1b[F\x1b[1~\x1b[4~\x1b[7~\x1b[8~\x1bOH\x1bOF\x1bOA\x1bOB\x1bOC\x1bOD\x1b[C\x1b[D"
        want = ["PGUP", "PGDN", "HOME", "END", "HOME", "END", "HOME", "END", "HOME", "END", "UP", "DOWN", "RIGHT", "LEFT", "RIGHT", "LEFT"]
        self.assertEqual(KeyParser().feed(seq), want)

    def test_unknown_complete_sequence_dropped(self):
        self.assertEqual(KeyParser().feed(b"\x1b[1;5A\x1b[B"), ["DOWN"])
        self.assertEqual(KeyParser().feed(b"\x1b[200~x\x1b[201~"), ["x"])

    def test_long_press_stream(self):
        """长按：分成任意块的字节流，按键序列不变。"""
        stream = b"\x1b[B" * 40 + b"\x1b[A" * 3
        for size in (1, 2, 3, 5, 7, 64):
            p, got = KeyParser(), []
            for k in range(0, len(stream), size):
                got += p.feed(stream[k:k + size])
            got += p.flush()
            self.assertEqual(got, ["DOWN"] * 40 + ["UP"] * 3, "块大小 %d" % size)


if __name__ == "__main__":
    unittest.main()
