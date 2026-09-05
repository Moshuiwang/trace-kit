# -*- coding: utf-8 -*-
"""登记表完整性与文档同源（S-5；https://github.com/Moshuiwang/lingxi/issues/579 关卡 1）。

- `registry.check_complete()` 必须为空：新增状态没登记进证据表 / 状态词 / 判定文案，本文件立刻红。
- `registry.render_markdown()` 必须与 `plugin/skills/board/SKILL.md`「状态与证据登记表」节逐字一致，
  也必须与 `board.py --registry` 的输出逐字一致（文档、常量、CLI 三处同源）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BOARD = os.path.join(ROOT, "plugin", "scripts", "board.py")
SKILL = os.path.join(ROOT, "plugin", "skills", "board", "SKILL.md")
SECTION = "## 状态与证据登记表"
sys.path.insert(0, os.path.join(ROOT, "plugin", "scripts"))

from boardlib import registry  # noqa: E402
from boardlib.model import EvidenceType, Status  # noqa: E402


def skill_tables() -> str:
    """SKILL.md 登记表节里的三张表（去掉说明文字与前后空行）。"""
    with open(SKILL, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    try:
        start = lines.index(SECTION)
    except ValueError:
        raise AssertionError("SKILL.md 缺「%s」节" % SECTION)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = lines[start + 1:end]
    first = next((i for i, ln in enumerate(body) if ln.startswith("| 状态 ")), None)
    assert first is not None, "SKILL.md 登记表节没有以「| 状态 |」开头的表格"
    return "\n".join(body[first:]).strip() + "\n"


class RegistryComplete(unittest.TestCase):
    def test_every_status_registered(self):
        self.assertEqual(registry.check_complete(), [], "有状态没登记进 EVIDENCE_REGISTRY / STATUS_LABEL / STATUS_RULE")

    def test_registry_uses_real_evidence_types(self):
        for status, evs in registry.EVIDENCE_REGISTRY.items():
            self.assertIsInstance(status, Status)
            self.assertTrue(evs, "状态 %s 的证据类型为空" % status.value)
            for ev in evs:
                self.assertIsInstance(ev, EvidenceType, "状态 %s 登记了非 EvidenceType：%r" % (status.value, ev))
        for table in (registry.STAGE_REGISTRY, registry.HEADER_REGISTRY):
            for key, (label, evs) in table.items():
                self.assertTrue(label, "登记项 %s 缺中文标签" % key)
                for ev in evs:
                    self.assertIsInstance(ev, EvidenceType, "登记项 %s 登记了非 EvidenceType：%r" % (key, ev))

    def test_missing_status_is_detected(self):
        """删掉一个状态的登记 → check_complete() 必须点名它（防止这张网被改成永远为空）。"""
        saved = registry.EVIDENCE_REGISTRY.pop(Status.STALE)
        try:
            self.assertIn(Status.STALE.value, registry.check_complete())
        finally:
            registry.EVIDENCE_REGISTRY[Status.STALE] = saved
        self.assertEqual(registry.check_complete(), [])


class RegistrySameSource(unittest.TestCase):
    maxDiff = None

    def test_markdown_matches_skill_doc(self):
        self.assertEqual(skill_tables(), registry.render_markdown(),
                         "plugin/skills/board/SKILL.md 的登记表节与 registry.render_markdown() 不一致："
                         "改引擎请用 `board.py --registry` 重生成该节")

    def test_registry_command_matches_markdown(self):
        proc = subprocess.run([sys.executable, "-B", BOARD, "--registry"], stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr.strip()[:400])
        self.assertEqual(proc.stdout, registry.render_markdown())


if __name__ == "__main__":
    unittest.main(verbosity=2)
