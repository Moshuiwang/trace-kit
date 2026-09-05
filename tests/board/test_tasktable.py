# -*- coding: utf-8 -*-
"""任务表解析单测（接口约定 §5；零网络）。真实任务表读 tests/board/fixtures/tables/ 下的冻结副本（不读活文件），只断言结构。"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "plugin", "scripts"))
TABLES = os.path.join(ROOT, "tests", "board", "fixtures", "tables")

from boardlib import tasktable  # noqa: E402
from boardlib.model import StepType  # noqa: E402


def _frozen(name):
    with open(os.path.join(TABLES, name, "任务表.md"), encoding="utf-8") as fh:
        return fh.read()


class FrozenTablesTest(unittest.TestCase):
    """Trace #1 / 模板 / #17 三份任务表的冻结副本：旧格式零改动可解析（只断言结构与几个稳定指针）。"""

    def test_module_lives_in_this_tree(self):
        self.assertTrue(os.path.abspath(tasktable.__file__).startswith(ROOT))

    def test_trace1(self):
        t = tasktable.parse(_frozen("1-trace-kit-v0.1.0"))
        self.assertEqual((len(t.sections), len(t.steps), len(t.unparsed)), (5, 15, 0))
        self.assertEqual(sum(1 for s in t.steps if s.checked), 15)
        self.assertEqual([s.title for s in t.sections], ["W0 只读盘点", "W1 并行打包", "W2 集成与自验证", "W3 发布与收口", "收口后追加"])
        by = {s.id: s for s in t.steps}
        self.assertEqual(by["S-1"].prs, [2])
        self.assertEqual(by["S-1"].shas, ["8b27e68"])
        self.assertEqual(by["S-2e"].prs, [4])  # `PR #4 合入`
        self.assertEqual(by["S-5"].shas, ["dd53ecf", "b5bb404"])
        self.assertEqual(by["S-0b"].comments, [5503411104])
        self.assertEqual(by["S-0a"].title, "克隆 + 推送冒烟")
        self.assertEqual(by["S-2a"].needs, ["S-1"])  # 章节首条＝上一章节末条
        self.assertEqual(by["S-2b"].needs, ["S-2a"])  # 同章节上一条
        self.assertEqual(by["S-0a"].needs, [])
        self.assertTrue(all(s.type == StepType.IMPL for s in t.steps))
        self.assertTrue(t.overlong)  # 旧格式长标题只计数不截断

    def test_template(self):
        t = tasktable.parse(_frozen("template"))
        self.assertEqual((len(t.sections), len(t.steps), len(t.unparsed)), (3, 6, 0))
        self.assertEqual(sum(1 for s in t.steps if s.checked), 0)
        self.assertEqual([s.id for s in t.steps], ["S-0-1", "S-1-1", "S-1-2", "S-Z-1", "S-Z-2", "S-Z-3"])
        self.assertEqual(t.sections[1].title, "W1 <批次名>")

    def test_trace17(self):
        t = tasktable.parse(_frozen("17-看板v1"))
        self.assertEqual((len(t.sections), len(t.steps), len(t.unparsed)), (6, 21, 0))
        self.assertEqual(sum(1 for s in t.steps if s.checked), 3)
        self.assertEqual([s.title for s in t.sections], ["块 A", "Wave 0", "Wave 1", "Wave 2", "Wave 3", "收口"])
        self.assertEqual([len(sec.steps) for sec in t.sections], [1, 2, 6, 4, 5, 3])
        by = {s.id: s for s in t.steps}
        self.assertEqual(by["A-1"].title, "块 A 六项")
        self.assertEqual(by["S-2"].needs, ["S-1"])


class GrammarTest(unittest.TestCase):
    def test_tag_block_four_keys(self):
        t = tasktable.parse("## W1\n\n- [ ] S-1 做一件事（PR #3 合入）[t:review needs:S-0,S-9 own:alice est:45m]\n")
        s = t.steps[0]
        self.assertEqual(s.type, StepType.REVIEW)
        self.assertEqual(s.needs, ["S-0", "S-9"])
        self.assertEqual(s.owner, "alice")
        self.assertEqual(s.est_min, 45)
        self.assertEqual(s.title, "做一件事")
        self.assertEqual(s.prs, [3])

    def test_est_and_type_rules(self):
        t = tasktable.parse("## W1\n- [ ] S-1 a [est:2h]\n- [ ] S-2 b [est:abc]\n- [ ] S-3 c [t:bogus]\n- [ ] S-4 d [t:human]\n- [ ] S-5 e [est:30]\n")
        self.assertEqual([s.est_min for s in t.steps], [120, None, None, None, None])
        self.assertEqual(t.steps[2].type, StepType.IMPL)
        self.assertEqual(t.steps[3].type, StepType.HUMAN)

    def test_pointers(self):
        line = "- [x] S-1 标题 — PR #12 合入；#13 合并；`abcdef1`、`0123456789abcdef0123456789abcdef01234567`；" \
               "[评论](https://github.com/o/r/issues/1#issuecomment-99) 与 https://example.com/x?y=1\n"
        s = tasktable.parse("## W\n" + line).steps[0]
        self.assertEqual(s.prs, [12, 13])
        self.assertEqual(s.shas, ["abcdef1", "0123456789abcdef0123456789abcdef01234567"])
        self.assertEqual(s.comments, [99])
        self.assertEqual(len(s.urls), 2)
        self.assertTrue(s.checked)

    def test_title_split(self):
        cases = {
            "- [ ] S-1 一句话——指针": "一句话",
            "- [ ] S-1 一句话 — 指针": "一句话",
            "- [ ] S-1 一句话（指针）": "一句话",
            "- [ ] S-1 一句话": "一句话",
        }
        for line, want in cases.items():
            self.assertEqual(tasktable.parse("## W\n" + line + "\n").steps[0].title, want, line)

    def test_unparsed_and_overlong(self):
        text = "- [ ] S-0 在章节之前\n## W1（说明）\n- [ ] 无编号行\n- [x] A-1…A-6 范围\n- [ ] S-1234567 编号超长\n- [ ] S-2 " + "汉" * 19 + "\n- [X] S-3 大写勾选\n"
        t = tasktable.parse(text)
        self.assertEqual(t.sections[0].title, "W1")
        self.assertEqual([s.id for s in t.steps], ["S-1234567", "S-2", "S-3"])
        self.assertEqual([ln for ln, _ in t.unparsed], [1, 3, 4])
        self.assertEqual(len(t.overlong), 2)
        self.assertTrue(t.steps[2].checked)

    def test_default_needs_skips_empty_section(self):
        t = tasktable.parse("## A\n- [ ] S-1 a\n## B\n## C\n- [ ] S-2 b [needs:S-9]\n- [ ] S-3 c\n")
        by = {s.id: s for s in t.steps}
        self.assertEqual(by["S-2"].needs, ["S-9"])  # 显式保留
        self.assertEqual(by["S-3"].needs, ["S-2"])
        t2 = tasktable.parse("## A\n- [ ] S-1 a\n## B\n## C\n- [ ] S-2 b\n")
        self.assertEqual(t2.steps[1].needs, ["S-1"])

    def test_never_raises_on_garbage(self):
        for text in ("", "\n\n", "## \n- [ ]\n- [x] \n", "- [ ] S-1", "## W\n- [ ] S-1 x [t:]\n"):
            tasktable.parse(text)


if __name__ == "__main__":
    unittest.main()
