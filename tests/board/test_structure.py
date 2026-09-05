# -*- coding: utf-8 -*-
"""结构断言（S-5；https://github.com/Moshuiwang/lingxi/issues/582「写错状态字符串即报错」）。

`Board.validate()` 在 infer 末尾与 render 入口各调一次：状态串写错、档位写错、来源角标写错、
模块依赖索引越界，一律 `ValueError`，不静默画错的图。本文件把每一种写错都构造一遍。
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "plugin", "scripts"))
sys.path.insert(0, HERE)

import sample_boards  # noqa: E402
from boardlib import render  # noqa: E402
from boardlib.model import EvidenceType, Grade, Status, Tier, Val, Why  # noqa: E402


def board():
    return sample_boards.BOARDS["simple"]()


class ValidStructure(unittest.TestCase):
    def test_samples_validate(self):
        for name in sample_boards.BOARDS:
            sample_boards.BOARDS[name]().validate()

    def test_render_accepts_valid_board(self):
        text = render.dump(board(), "simple", 150, 52)
        self.assertIn("Trace 看板", text)


class BrokenStructure(unittest.TestCase):
    """每个用例只写坏一处，断言 validate() 报错且错误信息点名对象。"""

    def assert_invalid(self, b, needle):
        with self.assertRaises(ValueError) as ctx:
            b.validate()
        self.assertIn(needle, str(ctx.exception))

    def test_step_status_is_string(self):
        b = board()
        b.steps[0].status = "running"
        self.assert_invalid(b, "S-1")

    def test_step_status_typo(self):
        b = board()
        b.steps[1].status = "runing"
        self.assert_invalid(b, "S-2")

    def test_step_chip_status_is_string(self):
        b = board()
        b.steps[0].chip_status = "done"
        self.assert_invalid(b, "S-1")

    def test_module_status_is_string(self):
        b = board()
        b.modules[0].status = "done"
        self.assert_invalid(b, "状态不是 Status")

    def test_module_tier_is_int(self):
        b = board()
        b.modules[1].tier = 2
        self.assert_invalid(b, "档位不是 Tier")

    def test_module_tier_is_string(self):
        b = board()
        b.modules[1].tier = "2"
        self.assert_invalid(b, "档位不是 Tier")

    def test_rounds_value_is_plain_int(self):
        b = board()
        b.modules[0].rounds.review = 3
        self.assert_invalid(b, "轮数不是 Val/Grade")

    def test_rounds_grade_is_string(self):
        b = board()
        b.modules[0].rounds.ci_red = Val(1, "inferred", "gh.runs")
        self.assert_invalid(b, "轮数不是 Val/Grade")

    def test_module_needs_out_of_range(self):
        b = board()
        b.modules[2].needs = [len(b.modules)]
        self.assert_invalid(b, "依赖索引越界")

    def test_module_needs_negative(self):
        b = board()
        b.modules[2].needs = [-1]
        self.assert_invalid(b, "依赖索引越界")

    def test_budget_value_is_plain_number(self):
        b = board()
        b.header.budget = [("完整门禁", 3, 10)]
        self.assert_invalid(b, "预算条")

    def test_budget_grade_is_string(self):
        b = board()
        b.header.budget = [("完整门禁", Val(3, "measured", "gh.runs"), 10)]
        self.assert_invalid(b, "预算条")

    def test_stage_value_is_bool(self):
        b = board()
        b.header.stages[0].value = True
        self.assert_invalid(b, "阶段 merged 不是 Val")

    # ---- 账本 R1-25：递归校验阶段 grade、Why、Step.section ----
    def test_r1_25_stage_grade_is_string(self):
        b = board()
        b.header.stages[0].value = Val(True, "measured", "gh.prs")
        self.assert_invalid(b, "阶段 merged")

    def test_r1_25_why_status_not_string(self):
        b = board()
        b.modules[0].why.append(Why("Wave 1", Status.DONE, EvidenceType.PR_STATE, "gh.prs", "MERGED"))
        self.assert_invalid(b, "Why")

    def test_r1_25_why_evidence_is_string(self):
        b = board()
        b.steps[0].why.append(Why("S-1", "done", "pr_state", "gh.prs", "MERGED"))
        self.assert_invalid(b, "证据类型")
        b = board()
        b.why.append(Why("阶段 merged", "否", "pr_state", "gh.prs", "OPEN"))
        self.assert_invalid(b, "证据类型")

    def test_r1_25_step_section_out_of_range(self):
        b = board()
        b.steps[0].step.section = 7
        self.assert_invalid(b, "章节索引")
        b = board()
        b.steps[1].step.section = -1
        self.assert_invalid(b, "章节索引")

    def test_r1_25_step_section_ok_without_modules(self):
        """还没有模块（例如任务表不可得）时不校验章节索引。"""
        b = board()
        b.modules = []
        b.validate()

    def test_render_rejects_broken_board(self):
        """render 入口也要拦：写坏的 Board 不许画出来。"""
        b = board()
        b.modules[0].tier = 9
        with self.assertRaises(ValueError):
            render.dump(b, "simple", 150, 52)

    def test_render_rejects_bad_view(self):
        with self.assertRaises(ValueError):
            render.dump(board(), "tree", 150, 52)


class RecordGuardTest(unittest.TestCase):
    """账本 R1-27：`--record` 目录若落在目标仓库内（按 realpath）→ 拒绝退出，不在被读取的仓库里创建文件。"""

    def _run(self, argv):
        import subprocess
        proc = subprocess.run([sys.executable, "-B", os.path.join(ROOT, "plugin", "scripts", "board.py")] + argv,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        return proc.returncode, proc.stdout + proc.stderr

    def test_record_inside_repo_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, "docs", "traces", "1-x"))
            inside = os.path.join(repo, "docs", "traces", "1-x", "snap")
            code, out = self._run(["--repo-root", repo, "--record", inside])
            self.assertNotEqual(code, 0)
            self.assertIn("--record", out)
            self.assertIn("目标仓库", out)
            self.assertFalse(os.path.exists(inside))
            link = os.path.join(tempfile.gettempdir(), "board-record-link-%d" % os.getpid())
            os.symlink(os.path.join(repo, "docs"), link)
            try:
                code, out = self._run(["--repo-root", repo, "--record", os.path.join(link, "snap")])
                self.assertNotEqual(code, 0, "经符号链接绕进仓库也要拒绝")
                self.assertIn("目标仓库", out)
            finally:
                os.unlink(link)


class GoodValues(unittest.TestCase):
    """合法取值不许被误判为错。"""

    def test_all_status_and_tier_values_pass(self):
        b = board()
        for st in Status:
            b.steps[0].status = st
            b.steps[0].chip_status = st
            b.modules[0].status = st
            b.validate()
        for tier in Tier:
            b.modules[0].tier = tier
            b.validate()
        for grade in Grade:
            b.modules[0].rounds.review = Val(1, grade, "gh.issue")
            b.validate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
