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
        """孤立 Esc：先留缓冲；后续不是 [ / O 就先发 ESC 再解析；超过 Esc 期限（50 ms）没后续才由 flush 发 ESC。"""
        p = KeyParser()
        self.assertEqual(p.feed(b"\x1b", now=0.0), [])
        self.assertEqual(p.flush(now=0.03), [])                 # 还在期限内：不发
        self.assertEqual(p.flush(now=0.06), ["ESC"])            # 过期：孤立 Esc
        self.assertEqual(p.feed(b"\x1b", now=1.0), [])
        self.assertEqual(p.feed(b"q", now=1.0), ["ESC", "q"])
        self.assertEqual(p.feed(b"\x1b\x1b[B", now=2.0), ["ESC", "DOWN"])
        self.assertEqual(p.feed(b"\x1b[", now=3.0), [])
        self.assertEqual(p.flush(now=3.6), ["ESC", "["])

    def test_r2_7_half_sequence_survives_animation_tick(self):
        """账本 R2-7：半个 CSI 相隔 200 ms（超过动画 tick 180 ms）到达也要拼上；期限是固定的 500 ms 字节间隔。"""
        p = KeyParser()
        self.assertEqual(p.feed(b"\x1b[", now=0.0), [])
        self.assertEqual(p.flush(now=0.2), [])                  # 动画 tick 时 flush：不得拆散
        self.assertEqual(p.feed(b"B", now=0.3), ["DOWN"])
        self.assertEqual(p.feed(b"\x1bO", now=1.0), [])
        self.assertEqual(p.flush(now=1.45), [])
        self.assertEqual(p.feed(b"A", now=1.49), ["UP"])
        self.assertEqual(p.feed(b"\x1b[5", now=2.0), [])
        self.assertEqual(p.flush(now=2.51), ["ESC", "[", "5"])  # 过期才清
        self.assertEqual(p.flush(now=2.52), [])

    def test_r2_7_wait_hint(self):
        p = KeyParser()
        self.assertIsNone(p.wait_hint(now=0.0))
        p.feed(b"\x1b", now=0.0)
        self.assertAlmostEqual(p.wait_hint(now=0.01), 0.04, places=3)
        p.feed(b"[", now=0.02)                                    # 已确认 CSI 前缀：期限换成 500 ms，从最后一个字节起算
        self.assertAlmostEqual(p.wait_hint(now=0.02), 0.5, places=3)
        p.feed(b"B", now=0.1)
        self.assertIsNone(p.wait_hint(now=0.1))

    def test_r2_8_bracketed_paste_is_not_a_command(self):
        """账本 R2-8：粘贴 `query` 不得触发 q / v / r；整段收成一个 PASTE 事件。"""
        p = KeyParser()
        self.assertEqual(p.feed(b"\x1b[200~query\x1b[201~v"), ["PASTE", "v"])
        self.assertEqual(p.feed(b"\x1b[200~qu"), [])
        self.assertEqual(p.feed(b"er"), [])
        self.assertEqual(p.feed(b"y\x1b[201~"), ["PASTE"])
        self.assertEqual(p.feed(b"\x1b[200~" + b"q" * 70000 + b"\x1b[201~r"), ["PASTE", "r"])   # 超长载荷有界丢弃

    def test_r2_8_osc_dcs_apc_consumed_to_terminator(self):
        p = KeyParser()
        self.assertEqual(p.feed(b"\x1b]0;title with q\x07v"), ["v"])           # OSC … BEL
        self.assertEqual(p.feed(b"\x1b]52;c;cXVlcnk=\x1b\\q"), ["q"])         # OSC … ST
        self.assertEqual(p.feed(b"\x1bPq#0;1;0/~\x1b\\r"), ["r"])             # DCS … ST
        self.assertEqual(p.feed(b"\x1b_anything\x1b\\a"), ["a"])              # APC … ST
        self.assertEqual(p.feed(b"\x1b]0;half"), [])                             # 半个 OSC 留缓冲
        self.assertEqual(p.feed(b"\x07q"), ["q"])

    def test_r2_9_overlong_sequence_dropped_and_reset(self):
        p = KeyParser()
        self.assertEqual(p.feed(b"\x1b[" + b"1;" * 40, now=0.0), [])          # 超过 64 字节仍无终结：整段丢弃
        self.assertEqual(p.flush(now=9.0), [])                                    # 缓冲已重置，没有残留
        self.assertEqual(p.feed(b"q"), ["q"])
        self.assertEqual(p.feed(b"\x1b]" + b"x" * 2000), [])                     # OSC 超过上限同样丢弃
        self.assertEqual(p.feed(b"v"), ["v"])

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
        self.assertEqual(KeyParser().feed(b"\x1b[200~x\x1b[201~"), ["PASTE"])   # R2-8：粘贴载荷不当按键

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
