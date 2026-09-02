#!/usr/bin/env python3
"""``scripts/ci`` 与 ``scripts/dev`` 下门禁脚本的判定用例。

出处：lingxi https://github.com/Moshuiwang/lingxi/issues/82（分层 CI 的钉住用例）、
https://github.com/Moshuiwang/lingxi/issues/238（棘轮与归属核对的自证用例）、
https://github.com/Moshuiwang/lingxi/issues/236（本机分层与 CI 同一事实源）；
验证：上游 tests/test_ci_layering.py、test_size_ratchet_check.py、
test_matrix_row_size_ratchet_check.py、test_contract_attribution_check.py、
test_dev_check_gate_spec.py、test_dev_check_local_layer.py 随约 250 个 PR 每次运行。

**惯例**：每个门禁至少有一条用例先构造一份会违规的输入，断言它被具体地拒绝——
只跑一遍真实仓库看它绿的检查等于没有检查。判定逻辑尽量用纯函数直接喂字典/字符串；
需要磁盘或 git 的部分建临时夹具仓库，不依赖本仓库当前的内容。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load(relative: str, name: str):
    """按路径加载一个门禁脚本（它们是可执行脚本，不是包，不能 import）。"""
    path = REPOSITORY_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # 先登记进 sys.modules 再执行：模块内的 dataclass 会回查 sys.modules 找自己的模块。
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CLASSIFIER = _load("scripts/ci/classify_story_changes.py", "classifier_under_test")
MATRIX = _load("scripts/ci/check_acceptance_matrix.py", "acceptance_matrix_under_test")
ROW_RATCHET = _load("scripts/ci/check_matrix_row_size_ratchet.py", "matrix_row_ratchet_under_test")
SIZE_RATCHET = _load("scripts/ci/check_size_ratchet.py", "size_ratchet_under_test")
DOCS_BUDGET = _load("scripts/ci/check_docs_size_budget.py", "docs_size_budget_under_test")
ATTRIBUTION = _load("scripts/ci/check_contract_attribution.py", "contract_attribution_under_test")
GATE_SPEC = _load("scripts/dev/gate_spec.py", "gate_spec_under_test")
LOCAL_LAYER = _load("scripts/dev/local_layer.py", "local_layer_under_test")


def _run_git(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repository, check=True, capture_output=True, text=True)


def _init_repository(repository: Path) -> None:
    _run_git(repository, "init", "--quiet", "--initial-branch=main")
    _run_git(repository, "config", "user.email", "ci-scripts-test@example.invalid")
    _run_git(repository, "config", "user.name", "ci-scripts-test")


def _write(repository: Path, relative: str, content: str) -> Path:
    target = repository / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _commit(repository: Path, relative: str, content: str, message: str) -> str:
    _write(repository, relative, content)
    _run_git(repository, "add", "--", relative)
    _run_git(repository, "commit", "--quiet", "-m", message)
    return _run_git(repository, "rev-parse", "HEAD").stdout.strip()


class _TemporaryRepositoryTestCase(unittest.TestCase):
    """带 git 仓库的临时夹具基类。

    ``ignore_cleanup_errors=True``：临时目录里是真的 git 仓库，提交后 git 可能拉起后台
    维护继续往 ``.git/objects`` 写文件，清理时撞上会抛 ``Directory not empty``；那只影响
    测试自身的清理，不改任何被测断言（上游真打红过一次）。
    """

    prefix = "trace-kit-ci-scripts-"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix=self.prefix, ignore_cleanup_errors=True)
        self.repository = Path(self._tmp.name)
        _init_repository(self.repository)

    def tearDown(self) -> None:
        self._tmp.cleanup()


# --------------------------------------------------------------------------------------
# scripts/ci/classify_story_changes.py：三档路由 + 未知路径失败关闭到 full
# --------------------------------------------------------------------------------------


class StoryClassificationTest(unittest.TestCase):
    def test_pure_documents_route_to_docs(self) -> None:
        self.assertEqual(CLASSIFIER.classify(["docs/协作约定.md", "AGENTS.md", "README.md"]), "docs")

    def test_normal_code_routes_to_fast(self) -> None:
        self.assertEqual(CLASSIFIER.classify(["src/app/__main__.py", "tests/test_smoke.py"]), "fast")

    def test_documents_mixed_with_code_still_route_to_fast(self) -> None:
        self.assertEqual(CLASSIFIER.classify(["docs/README.md", "src/app/migrate.py"]), "fast")

    def test_high_risk_paths_route_to_full(self) -> None:
        for path in (
            ".github/workflows/ci.yml",
            "scripts/ci/verify_repository.sh",
            "scripts/ci/check_size_ratchet.py",
            "deploy/compose.yaml",
            "migrations/versions/0001_initial.py",
            "Dockerfile",
            ".dockerignore",
            "pyproject.toml",
        ):
            with self.subTest(path=path):
                self.assertEqual(CLASSIFIER.classify([path]), "full")

    def test_high_risk_path_mixed_with_documents_is_not_downgraded(self) -> None:
        self.assertEqual(CLASSIFIER.classify(["docs/README.md", "Dockerfile"]), "full")

    def test_unknown_path_fails_closed_to_full(self) -> None:
        """分类器的目标不是猜得细，而是让新增目录不会因为没人更新路径表而静默绕过检查。"""
        self.assertEqual(CLASSIFIER.classify(["新目录/whatever.py"]), "full")
        self.assertEqual(CLASSIFIER.classify(["Makefile"]), "full")

    def test_empty_change_set_fails_closed_to_full(self) -> None:
        self.assertEqual(CLASSIFIER.classify([]), "full")

    def test_registered_ci_data_file_does_not_escalate(self) -> None:
        self.assertEqual(CLASSIFIER.classify(["scripts/ci/size_ratchet_baseline.txt"]), "fast")
        self.assertEqual(CLASSIFIER.classify(["scripts/ci/matrix_row_size_baseline.txt"]), "fast")

    def test_unregistered_data_looking_file_under_scripts_ci_still_escalates(self) -> None:
        # 否定用例：清单外的 scripts/ci/ 新文件，哪怕名字看起来也像纯数据，默认仍然提级。
        self.assertEqual(CLASSIFIER.classify(["scripts/ci/some_new_baseline.txt"]), "full")

    def test_documents_changed_flag_is_reported_alongside_the_mode(self) -> None:
        detail = CLASSIFIER.classify_detail(["docs/README.md", "Dockerfile"])
        self.assertEqual(detail.mode, "full")
        self.assertTrue(detail.docs_changed)
        self.assertFalse(CLASSIFIER.classify_detail(["src/app/migrate.py"]).docs_changed)


# --------------------------------------------------------------------------------------
# scripts/dev/local_layer.py：本机分层与 CI 分类器同一结论
# --------------------------------------------------------------------------------------


class LocalLayerMatchesClassifierTest(_TemporaryRepositoryTestCase):
    """在真实临时仓库的一段提交历史上比对两条**不同**的代码路径。

    左边 ``local_layer.classify_local()`` 是本机 ``check.sh`` 的入口，右边
    ``classify_story_changes.changed_paths()`` + ``classify()`` 是 CI 的入口；两边各自
    独立地做「git 取路径」再分类。只有当 local_layer 的取路径逻辑与 CI 语义一致时，
    结论才会对每一段历史都相等——写错参数顺序或漏传一个 ref 都会在这里真的不一致。
    """

    prefix = "trace-kit-local-layer-"

    def _assert_same_conclusion(self, base_sha: str) -> str:
        local_mode = LOCAL_LAYER.classify_local(base_sha, include_worktree=False, repository=self.repository)
        ci_paths = CLASSIFIER.changed_paths(base_sha, "HEAD", repository=self.repository)
        ci_mode = CLASSIFIER.classify(ci_paths)
        self.assertEqual(local_mode, ci_mode, f"{base_sha}..HEAD 上本机与 CI 的分层结论不一致")
        return local_mode

    def test_local_layer_loads_the_repository_classifier_instead_of_rewriting_it(self) -> None:
        self.assertEqual(
            Path(LOCAL_LAYER._CLASSIFIER.__file__).resolve(),
            (REPOSITORY_ROOT / "scripts" / "ci" / "classify_story_changes.py").resolve(),
        )

    def test_matches_on_a_real_commit_history(self) -> None:
        base = _commit(self.repository, "README.md", "# 起点\n", "起点")
        _commit(self.repository, "docs/README.md", "# 文档\n", "纯文档")
        self.assertEqual(self._assert_same_conclusion(base), "docs")

        base = _run_git(self.repository, "rev-parse", "HEAD").stdout.strip()
        _commit(self.repository, "src/app/__init__.py", '__version__ = "0.1.0"\n', "代码")
        self.assertEqual(self._assert_same_conclusion(base), "fast")

        base = _run_git(self.repository, "rev-parse", "HEAD").stdout.strip()
        _commit(self.repository, ".github/workflows/ci.yml", "name: Epic Full\n", "门禁自身")
        self.assertEqual(self._assert_same_conclusion(base), "full")

    def test_uncommitted_new_file_is_visible_to_the_local_layer_only(self) -> None:
        """本机默认把未提交（含从未 git add）的改动算进来，这是与 CI 唯一的行为差异。"""
        base = _commit(self.repository, "README.md", "# 起点\n", "起点")
        _commit(self.repository, "docs/README.md", "# 文档\n", "纯文档")
        _write(self.repository, "scripts/ci/brand_new_gate.py", "# 还没 git add\n")

        self.assertEqual(
            LOCAL_LAYER.classify_local(base, include_worktree=True, repository=self.repository), "full"
        )
        self.assertEqual(
            LOCAL_LAYER.classify_local(base, include_worktree=False, repository=self.repository), "docs"
        )


# --------------------------------------------------------------------------------------
# scripts/ci/check_acceptance_matrix.py：状态列三态、编号唯一、覆盖清单跨查
# --------------------------------------------------------------------------------------

LEGAL_MATRIX = """\
# 验收矩阵

| # | 可验证断言 | 层级 | 状态 |
|---|---|---|---|
| V-示例-01 | 给定 A 当 B 则 C | L2 | 未认领 |
| V-示例-02 | 命令里带一个字面竖线 a \\| b 也要能解析 | L2 | 已验证 |
"""

LEGAL_COVERAGE = """\
## 二、合同条款覆盖清单

| 合同章节 | 对应断言 | 说明 |
|---|---|---|
| 产品是什么 | 无对应断言 | 定位陈述，不含独立的可判定规则 |
| 用户与入口 | V-示例-01、V-示例-02 | — |
"""

LEGAL_CONTRACT = """\
# 产品合同

## 产品是什么

一句话。

## 用户与入口

一句话。
"""


class AcceptanceMatrixParseTest(unittest.TestCase):
    def test_legal_matrix_parses_all_three_states(self) -> None:
        statuses, errors = MATRIX.parse_matrix(LEGAL_MATRIX)
        self.assertEqual(errors, [])
        self.assertEqual(statuses, {"V-示例-01": "未认领", "V-示例-02": "已验证"})

    def test_assertion_row_without_a_status_column_is_rejected(self) -> None:
        broken = "| # | 可验证断言 | 层级 |\n|---|---|---|\n| V-示例-01 | 给定 A | L2 |\n"
        _, errors = MATRIX.parse_matrix(broken)
        self.assertTrue(any("没有「状态」列表头" in error for error in errors), errors)

    def test_state_outside_the_three_words_is_rejected(self) -> None:
        broken = LEGAL_MATRIX.replace("| L2 | 未认领 |", "| L2 | 待实现 |")
        _, errors = MATRIX.parse_matrix(broken)
        self.assertTrue(any("只允许" in error and "待实现" in error for error in errors), errors)

    def test_empty_state_cell_is_rejected(self) -> None:
        broken = LEGAL_MATRIX.replace("| L2 | 未认领 |", "| L2 |  |")
        _, errors = MATRIX.parse_matrix(broken)
        self.assertTrue(errors)

    def test_duplicate_assertion_id_is_rejected_across_the_whole_collection(self) -> None:
        documents = {
            "验收矩阵.md": LEGAL_MATRIX,
            "验收矩阵-另一册.md": LEGAL_MATRIX.replace("V-示例-02", "V-示例-03"),
        }
        _, errors = MATRIX.parse_matrix(documents)
        self.assertTrue(any("断言编号重复" in error for error in errors), errors)

    def test_a_matrix_with_no_assertion_rows_fails_closed(self) -> None:
        _, errors = MATRIX.parse_matrix("# 空矩阵\n\n没有表格。\n")
        self.assertTrue(any("一条断言都没解析到" in error for error in errors), errors)

    def test_volume_not_linked_from_the_hub_is_rejected(self) -> None:
        errors = MATRIX.check_volume_registry(
            {MATRIX.MATRIX_DOCUMENT.name: "# 总册\n没有链接。\n", "验收矩阵-部署.md": "# 分册\n"}
        )
        self.assertTrue(any("没有登记在总册" in error for error in errors), errors)
        self.assertEqual(
            MATRIX.check_volume_registry(
                {MATRIX.MATRIX_DOCUMENT.name: "见[部署](验收矩阵-部署.md)\n", "验收矩阵-部署.md": "# 分册\n"}
            ),
            [],
        )


class AcceptanceCoverageTest(unittest.TestCase):
    def test_legal_coverage_maps_sections_to_assertions(self) -> None:
        coverage, errors = MATRIX.parse_coverage(LEGAL_COVERAGE)
        self.assertEqual(errors, [])
        self.assertEqual(coverage["用户与入口"][0], ["V-示例-01", "V-示例-02"])
        self.assertEqual(coverage["产品是什么"][0], [])

    def test_no_assertion_without_a_reason_is_rejected(self) -> None:
        broken = LEGAL_COVERAGE.replace("| 无对应断言 | 定位陈述，不含独立的可判定规则 |", "| 无对应断言 | — |")
        _, errors = MATRIX.parse_coverage(broken)
        self.assertTrue(any("没有说明理由" in error for error in errors), errors)

    def test_empty_assertion_cell_is_rejected(self) -> None:
        broken = LEGAL_COVERAGE.replace("| V-示例-01、V-示例-02 |", "|  |")
        _, errors = MATRIX.parse_coverage(broken)
        self.assertTrue(any("没有任何对应断言" in error for error in errors), errors)

    def test_assertion_range_is_expanded(self) -> None:
        self.assertEqual(MATRIX.expand_reference("V-示例-01…03")[0], ["V-示例-01", "V-示例-02", "V-示例-03"])
        self.assertTrue(MATRIX.expand_reference("V-示例-03…01")[1])
        self.assertTrue(MATRIX.expand_reference("随便写的")[1])

    def test_missing_coverage_table_fails_closed(self) -> None:
        _, errors = MATRIX.parse_coverage("# 只有正文\n")
        self.assertTrue(any("没找到合同条款覆盖清单" in error for error in errors), errors)

    def test_cross_check_catches_the_three_silent_gaps(self) -> None:
        statuses, _ = MATRIX.parse_matrix(LEGAL_MATRIX)
        coverage, _ = MATRIX.parse_coverage(LEGAL_COVERAGE)
        sections = MATRIX.contract_sections(LEGAL_CONTRACT)

        self.assertEqual(MATRIX.cross_check(statuses, coverage, sections), [])

        # ① 合同新增一节却没登记到覆盖清单
        failures = MATRIX.cross_check(statuses, coverage, [*sections, "不提供"])
        self.assertTrue(any("没有登记到覆盖清单" in failure for failure in failures), failures)
        # ② 覆盖清单登记了合同里不存在的章节（改名后没同步）
        failures = MATRIX.cross_check(statuses, coverage, ["产品是什么"])
        self.assertTrue(any("不存在的章节" in failure for failure in failures), failures)
        # ③ 覆盖清单引用了矩阵里不存在的断言编号
        failures = MATRIX.cross_check({"V-示例-01": "未认领"}, coverage, sections)
        self.assertTrue(any("不存在的断言" in failure for failure in failures), failures)


class AcceptanceMatrixOnTheRealDocumentsTest(unittest.TestCase):
    """本仓库当前提交的矩阵与合同必须自洽——门禁跑的就是这一条。"""

    def test_committed_documents_pass(self) -> None:
        documents = MATRIX.matrix_documents()
        statuses, failures = MATRIX.parse_matrix(documents)
        coverage, coverage_errors = MATRIX.parse_coverage(documents)
        sections = MATRIX.contract_sections(MATRIX.CONTRACT_DOCUMENT.read_text(encoding="utf-8"))
        all_failures = (
            failures
            + coverage_errors
            + MATRIX.check_volume_registry(documents)
            + MATRIX.cross_check(statuses, coverage, sections)
        )
        self.assertEqual(all_failures, [])


# --------------------------------------------------------------------------------------
# scripts/ci/check_matrix_row_size_ratchet.py：单行体量棘轮只减不增
# --------------------------------------------------------------------------------------


def _matrix_row(identifier: str, size_bytes: int) -> str:
    """造一条 UTF-8 字节数**恰好**等于 ``size_bytes`` 的合法断言行。"""
    prefix = f"| {identifier} | "
    suffix = " | L2 | 未认领 |"
    padding = size_bytes - len(prefix.encode("utf-8")) - len(suffix.encode("utf-8"))
    assert padding >= 1, "目标字节数太小，装不下一行合法断言"
    return prefix + "x" * padding + suffix


def _matrix_document(rows: list[str]) -> str:
    header = "# 验收矩阵\n\n| # | 可验证断言 | 层级 | 状态 |\n|---|---|---|---|\n"
    return header + "\n".join(rows) + "\n"


class MatrixRowRatchetEvaluateTest(unittest.TestCase):
    def test_measure_rows_counts_the_whole_markdown_line(self) -> None:
        text = _matrix_document([_matrix_row("V-示例-01", 900)])
        self.assertEqual(ROW_RATCHET.measure_rows(text), {"V-示例-01": 900})

    def test_growth_beyond_the_recorded_ceiling_is_rejected(self) -> None:
        failures = ROW_RATCHET.evaluate({"V-示例-01": 900}, {"V-示例-01": 901})
        self.assertTrue(any("超过棘轮基线记录的上限" in failure for failure in failures), failures)

    def test_shrinking_requires_refreshing_the_baseline_to_the_exact_value(self) -> None:
        """基线必须与实测精确相等——这正是「手工把基线调大」被抓住的手段。"""
        failures = ROW_RATCHET.evaluate({"V-示例-01": 900}, {"V-示例-01": 850})
        self.assertTrue(any("与实测" in failure and "不一致" in failure for failure in failures), failures)

    def test_exact_match_passes(self) -> None:
        self.assertEqual(ROW_RATCHET.evaluate({"V-示例-01": 900}, {"V-示例-01": 900}), [])

    def test_new_row_crossing_the_threshold_unregistered_is_rejected(self) -> None:
        failures = ROW_RATCHET.evaluate({}, {"V-示例-01": ROW_RATCHET.THRESHOLD_BYTES + 1})
        self.assertTrue(any("新超过单行体量棘轮阈值" in failure for failure in failures), failures)

    def test_row_under_the_threshold_needs_no_registration(self) -> None:
        self.assertEqual(ROW_RATCHET.evaluate({}, {"V-示例-01": ROW_RATCHET.THRESHOLD_BYTES}), [])

    def test_retired_assertion_leaving_the_baseline_is_not_a_failure(self) -> None:
        self.assertEqual(ROW_RATCHET.evaluate({"V-示例-01": 900}, {}), [])

    def test_baseline_parsing_fails_closed_on_bad_rows(self) -> None:
        for text in ("九百\tV-示例-01\n", "900 V-示例-01\n", "900\t不是编号\n", "900\tV-示例-01\n800\tV-示例-01\n"):
            with self.subTest(text=text):
                with self.assertRaises(ROW_RATCHET.BaselineError):
                    ROW_RATCHET.parse_baseline(text)

    def test_render_then_parse_round_trips(self) -> None:
        entries = {"V-示例-01": 900, "V-部署-02": 1200}
        self.assertEqual(ROW_RATCHET.parse_baseline(ROW_RATCHET.render_baseline(entries)), entries)

    def test_read_range_collapse_fails_closed_instead_of_passing_on_an_empty_set(self) -> None:
        """量到 0 条断言却 exit 0 是最危险的一种绿：棘轮还在跑，但它什么都没在看。"""
        with self.assertRaises(ROW_RATCHET.BaselineError):
            ROW_RATCHET.verify_read_range({}, {})
        with self.assertRaises(ROW_RATCHET.BaselineError):
            ROW_RATCHET.verify_read_range({"验收矩阵.md": "# 空\n"}, {})


class MatrixRowRatchetRefreshTest(_TemporaryRepositoryTestCase):
    """``--refresh`` 只许调小或移除，绝不写入任何增长、也不代为新增登记。"""

    prefix = "trace-kit-row-ratchet-"

    @contextlib.contextmanager
    def _fixture(self, rows: list[str], baseline: dict[str, int]):
        matrix = self.repository / "docs" / "技术设计" / "验收矩阵.md"
        matrix.parent.mkdir(parents=True, exist_ok=True)
        matrix.write_text(_matrix_document(rows), encoding="utf-8")
        baseline_path = self.repository / "scripts" / "ci" / "matrix_row_size_baseline.txt"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(ROW_RATCHET.render_baseline(baseline), encoding="utf-8")
        with mock.patch.multiple(
            ROW_RATCHET,
            REPOSITORY_ROOT=self.repository,
            MATRIX_DOCUMENT=matrix,
            BASELINE_PATH=baseline_path,
        ):
            yield baseline_path

    @staticmethod
    def _quietly(callable_under_test) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return callable_under_test()

    def test_refresh_refuses_to_raise_a_registered_ceiling(self) -> None:
        with self._fixture([_matrix_row("V-示例-01", 1200)], {"V-示例-01": 900}) as baseline_path:
            before = baseline_path.read_text(encoding="utf-8")
            self.assertEqual(self._quietly(ROW_RATCHET.run_refresh), 1)
            self.assertEqual(baseline_path.read_text(encoding="utf-8"), before)

    def test_refresh_refuses_to_register_a_newly_oversized_row(self) -> None:
        oversized = ROW_RATCHET.THRESHOLD_BYTES + 50
        with self._fixture([_matrix_row("V-示例-01", oversized)], {}) as baseline_path:
            before = baseline_path.read_text(encoding="utf-8")
            self.assertEqual(self._quietly(ROW_RATCHET.run_refresh), 1)
            self.assertEqual(baseline_path.read_text(encoding="utf-8"), before)

    def test_refresh_lowers_a_registered_ceiling_after_the_row_shrank(self) -> None:
        with self._fixture([_matrix_row("V-示例-01", 850)], {"V-示例-01": 1200}) as baseline_path:
            self.assertEqual(self._quietly(ROW_RATCHET.run_refresh), 0)
            self.assertEqual(ROW_RATCHET.parse_baseline(baseline_path.read_text(encoding="utf-8")), {"V-示例-01": 850})

    def test_check_passes_only_when_the_baseline_matches_the_measurement(self) -> None:
        with self._fixture([_matrix_row("V-示例-01", 900)], {"V-示例-01": 900}):
            self.assertEqual(self._quietly(ROW_RATCHET.run_check), 0)
        with self._fixture([_matrix_row("V-示例-01", 901)], {"V-示例-01": 900}):
            self.assertEqual(self._quietly(ROW_RATCHET.run_check), 1)


class MatrixRowRatchetOnTheRealBaselineTest(unittest.TestCase):
    def test_committed_baseline_is_honest(self) -> None:
        baseline = ROW_RATCHET.load_baseline(ROW_RATCHET.BASELINE_PATH)
        current = ROW_RATCHET.measure_documents(ROW_RATCHET.read_matrix_documents())
        self.assertEqual(ROW_RATCHET.evaluate(baseline, current), [])


# --------------------------------------------------------------------------------------
# scripts/ci/check_size_ratchet.py：文件体量棘轮
# --------------------------------------------------------------------------------------


class SizeRatchetEvaluateTest(unittest.TestCase):
    def test_growth_beyond_the_recorded_ceiling_is_rejected(self) -> None:
        failures = SIZE_RATCHET.evaluate({"src/app/big.py": 2048}, {"src/app/big.py": 2049})
        self.assertTrue(any("超过棘轮基线记录的上限" in failure for failure in failures), failures)

    def test_manually_inflating_the_baseline_is_rejected(self) -> None:
        failures = SIZE_RATCHET.evaluate({"src/app/big.py": 9999}, {"src/app/big.py": 2048})
        self.assertTrue(any("与实测" in failure and "不一致" in failure for failure in failures), failures)

    def test_new_file_crossing_the_threshold_unregistered_is_rejected(self) -> None:
        failures = SIZE_RATCHET.evaluate({}, {"src/app/new.py": SIZE_RATCHET.THRESHOLD_LINES + 1})
        self.assertTrue(any("新超过体量棘轮阈值" in failure for failure in failures), failures)

    def test_exact_match_and_small_files_pass(self) -> None:
        self.assertEqual(SIZE_RATCHET.evaluate({"src/app/big.py": 2048}, {"src/app/big.py": 2048, "src/app/s.py": 9}), [])

    def test_baseline_parsing_fails_closed(self) -> None:
        for text in ("x\tsrc/app/a.py\n", "2048 src/app/a.py\n", "10\tsrc/app/a.py\n20\tsrc/app/a.py\n"):
            with self.subTest(text=text):
                with self.assertRaises(SIZE_RATCHET.BaselineError):
                    SIZE_RATCHET.parse_baseline(text)


class SizeRatchetScanFailsClosedTest(_TemporaryRepositoryTestCase):
    prefix = "trace-kit-size-ratchet-"

    def test_missing_source_root_fails_closed(self) -> None:
        with mock.patch.object(SIZE_RATCHET, "SOURCE_ROOT", self.repository / "src" / "app"):
            with self.assertRaises(SIZE_RATCHET.BaselineError):
                SIZE_RATCHET.iter_scope_files()

    def test_source_root_without_any_python_file_fails_closed(self) -> None:
        """空枚举不许冒充"零违规"：基线里每条登记都会被当成"文件已删除"静默放行。"""
        source_root = self.repository / "src" / "app"
        source_root.mkdir(parents=True)
        with mock.patch.object(SIZE_RATCHET, "SOURCE_ROOT", source_root):
            with self.assertRaises(SIZE_RATCHET.BaselineError):
                SIZE_RATCHET.iter_scope_files()

    def test_refresh_refuses_to_raise_a_registered_ceiling(self) -> None:
        source_root = self.repository / "src" / "app"
        source_root.mkdir(parents=True)
        (source_root / "big.py").write_text("x = 1\n" * 40, encoding="utf-8")
        baseline_path = self.repository / "scripts" / "ci" / "size_ratchet_baseline.txt"
        baseline_path.parent.mkdir(parents=True)
        baseline_path.write_text(SIZE_RATCHET.render_baseline({"src/app/big.py": 20}), encoding="utf-8")
        with mock.patch.multiple(
            SIZE_RATCHET,
            REPOSITORY_ROOT=self.repository,
            SOURCE_ROOT=source_root,
            BASELINE_PATH=baseline_path,
        ):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                exit_code = SIZE_RATCHET.run_refresh()
        self.assertEqual(exit_code, 1)
        self.assertEqual(SIZE_RATCHET.parse_baseline(baseline_path.read_text(encoding="utf-8")), {"src/app/big.py": 20})


class SizeRatchetOnTheRealBaselineTest(unittest.TestCase):
    def test_committed_baseline_is_honest(self) -> None:
        baseline = SIZE_RATCHET.load_baseline(SIZE_RATCHET.BASELINE_PATH)
        current = SIZE_RATCHET.measure(SIZE_RATCHET.iter_scope_files())
        self.assertEqual(SIZE_RATCHET.evaluate(baseline, current), [])


# --------------------------------------------------------------------------------------
# scripts/ci/check_docs_size_budget.py：开工必读集体量预算
# --------------------------------------------------------------------------------------


class DocsSizeBudgetTest(unittest.TestCase):
    @staticmethod
    def _quietly() -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return DOCS_BUDGET.main()

    def test_current_reading_set_is_within_budget(self) -> None:
        self.assertEqual(self._quietly(), 0)

    def test_exceeding_the_budget_is_red(self) -> None:
        with mock.patch.object(DOCS_BUDGET, "TOTAL_BUDGET_BYTES", 1):
            self.assertEqual(self._quietly(), 1)

    def test_a_renamed_or_deleted_budget_file_is_red(self) -> None:
        """必读集改名却没同步本检查时，绝不能悄悄按"少算一个文件"通过。"""
        with mock.patch.object(DOCS_BUDGET, "BUDGET_FILES", ("AGENTS.md", "docs/不存在的文件.md")):
            self.assertEqual(self._quietly(), 1)


# --------------------------------------------------------------------------------------
# scripts/ci/check_contract_attribution.py：归属登记必须整行逐字相等，例外每次可见
# --------------------------------------------------------------------------------------

FIXTURE_CONTRACT = """\
# 产品合同

## 外部边界

凭据只从环境注入。

<!--
## 已注释掉的一节

这一节已经不是合同正文。
-->

```
## 围栏里的一节
```
"""

# 夹具里那句被扫描的归属声明；本文件整体在 excluded_paths() 里，不会核对到自己头上。
FIXTURE_LINE = "凭据不进代码、日志与数据库（产品合同明令）。"


class ContractAttributionTest(_TemporaryRepositoryTestCase):
    prefix = "trace-kit-attribution-"

    def setUp(self) -> None:
        super().setUp()
        self.contract = _write(self.repository, "docs/产品合同.md", FIXTURE_CONTRACT)

    def _evaluate(self, *, grounded=(), exceptions=()):
        _run_git(self.repository, "add", "-A")
        with mock.patch.multiple(
            ATTRIBUTION,
            REPOSITORY_ROOT=self.repository,
            CONTRACT_DOCUMENT=self.contract,
            GROUNDED_ATTRIBUTIONS=tuple(grounded),
            REGISTERED_EXCEPTIONS=tuple(exceptions),
        ):
            return ATTRIBUTION.evaluate()

    def test_contract_sections_skip_fences_and_html_comments(self) -> None:
        sections = ATTRIBUTION.contract_sections(FIXTURE_CONTRACT)
        self.assertEqual(sections, {"产品合同", "外部边界"})

    def test_a_contract_without_any_heading_fails_closed(self) -> None:
        self.contract.write_text("只有正文，没有标题。\n", encoding="utf-8")
        with self.assertRaises(ATTRIBUTION.AttributionCheckError):
            self._evaluate()

    def test_unregistered_attribution_is_rejected(self) -> None:
        _write(self.repository, "docs/设计.md", f"- {FIXTURE_LINE}\n")
        failures, _, _ = self._evaluate()
        self.assertTrue(any("未登记" in failure for failure in failures), failures)

    def test_registered_whole_line_passes(self) -> None:
        _write(self.repository, "docs/设计.md", f"- {FIXTURE_LINE}\n")
        grounded = (ATTRIBUTION.GroundedAttribution("docs/设计.md", f"- {FIXTURE_LINE}", "外部边界"),)
        failures, _, summary = self._evaluate(grounded=grounded)
        self.assertEqual(failures, [])
        self.assertIn("扫描到 1 处", summary)

    def test_a_registered_substring_does_not_cover_the_line(self) -> None:
        """两个绕过面由「整行逐字相等」同时关闭：过短摘录不再覆盖任意新增行。"""
        _write(self.repository, "docs/设计.md", f"- {FIXTURE_LINE} 另外还悄悄加了一句新断言。\n")
        grounded = (ATTRIBUTION.GroundedAttribution("docs/设计.md", f"- {FIXTURE_LINE}", "外部边界"),)
        failures, _, _ = self._evaluate(grounded=grounded)
        self.assertTrue(any("未登记" in failure for failure in failures), failures)
        self.assertTrue(any("逐字比对" in failure for failure in failures), failures)

    def test_each_occurrence_needs_its_own_registration(self) -> None:
        _write(self.repository, "docs/设计.md", f"- {FIXTURE_LINE}\n- {FIXTURE_LINE}\n")
        grounded = (ATTRIBUTION.GroundedAttribution("docs/设计.md", f"- {FIXTURE_LINE}", "外部边界"),)
        failures, _, _ = self._evaluate(grounded=grounded)
        self.assertEqual(sum(1 for failure in failures if "未登记" in failure), 1, failures)

    def test_registration_pointing_at_a_missing_contract_section_is_rejected(self) -> None:
        _write(self.repository, "docs/设计.md", f"- {FIXTURE_LINE}\n")
        grounded = (ATTRIBUTION.GroundedAttribution("docs/设计.md", f"- {FIXTURE_LINE}", "已改名的一节"),)
        failures, _, _ = self._evaluate(grounded=grounded)
        self.assertTrue(any("找不到这个标题" in failure for failure in failures), failures)

    def test_a_stale_registration_whose_line_disappeared_is_rejected(self) -> None:
        _write(self.repository, "docs/设计.md", "- 这句已经改写过了。\n")
        grounded = (ATTRIBUTION.GroundedAttribution("docs/设计.md", f"- {FIXTURE_LINE}", "外部边界"),)
        failures, _, _ = self._evaluate(grounded=grounded)
        self.assertTrue(any("逐字比对" in failure for failure in failures), failures)

    def test_registered_exception_is_visible_on_both_the_green_and_the_red_path(self) -> None:
        _write(self.repository, "docs/设计.md", f"- {FIXTURE_LINE}\n")
        exception = ATTRIBUTION.RegisteredException(
            "docs/设计.md", f"- {FIXTURE_LINE}", "Issue #1", "2026-01-01", "产品负责人", "合同正文没有这句话。"
        )
        failures, notes, _ = self._evaluate(exceptions=(exception,))
        self.assertEqual(failures, [])
        self.assertTrue(any("Issue #1" in note for note in notes), notes)

        _write(self.repository, "docs/另一处.md", f"- {FIXTURE_LINE}\n")
        failures, notes, _ = self._evaluate(exceptions=(exception,))
        self.assertTrue(failures)
        self.assertTrue(any("Issue #1" in note for note in notes), notes)

    def test_an_untraceable_exception_is_rejected(self) -> None:
        _write(self.repository, "docs/设计.md", f"- {FIXTURE_LINE}\n")
        for source, decided_on, reason in (
            ("随口说的", "2026-01-01", "理由"),
            ("Issue #1", "昨天", "理由"),
            ("Issue #1", "2026-01-01", "   "),
        ):
            with self.subTest(source=source, decided_on=decided_on):
                exception = ATTRIBUTION.RegisteredException(
                    "docs/设计.md", f"- {FIXTURE_LINE}", source, decided_on, "产品负责人", reason
                )
                failures, _, _ = self._evaluate(exceptions=(exception,))
                self.assertTrue(failures)

    def test_the_mechanism_name_itself_is_not_an_attribution_claim(self) -> None:
        _write(self.repository, "docs/设计.md", "见合同条款覆盖清单一节。\n")
        failures, _, summary = self._evaluate()
        self.assertEqual(failures, [])
        self.assertIn("扫描到 0 处", summary)


# --------------------------------------------------------------------------------------
# scripts/dev/gate_spec.py：环境配方现读自工作流，读不出来必须响亮失败
# --------------------------------------------------------------------------------------

MINIMAL_GATE_WORKFLOW = """\
jobs:
  classify:
    name: Epic / classify
  gate:
    name: Epic Full / gate
    steps:
      - name: 配置 Python 运行时
        with:
          python-version: '3.12'
      - name: 安装测试依赖
        run: python3 -m pip install '.[dev]'
      - name: 运行基础质量门禁
        run: scripts/ci/verify_repository.sh
  image:
    name: Epic Full / image
"""

MINIMAL_FAST_WORKFLOW = """\
jobs:
  classify:
    name: Story / classify
  fast:
    name: Story / code fast
    steps:
      - name: 配置 Python 运行时
        with:
          python-version: '3.12'
      - name: 安装快速门禁依赖
        run: python3 -m pip install '.[dev,extra]'
  full:
    name: Story / high-risk full
"""


class GateSpecParsingTest(unittest.TestCase):
    def test_parses_extras_and_python_version_from_the_gate_job(self) -> None:
        spec = GATE_SPEC.parse_gate_spec(MINIMAL_GATE_WORKFLOW)
        self.assertEqual(spec.extras, ["dev"])
        self.assertEqual(spec.python_version, "3.12")

    def test_parses_multiple_extras_from_the_fast_job(self) -> None:
        spec = GATE_SPEC.parse_fast_spec(MINIMAL_FAST_WORKFLOW)
        self.assertEqual(spec.extras, ["dev", "extra"])
        self.assertEqual(spec.python_version, "3.12")

    def test_unrecognised_shapes_fail_loudly_instead_of_falling_back(self) -> None:
        """退回旧值等于本工具自己制造出一次它要消灭的漂移，所以只能响亮失败。"""
        broken_inputs = {
            "缺 gate job": "jobs:\n  classify:\n    name: x\n",
            "缺安装步骤": MINIMAL_GATE_WORKFLOW.replace("      - name: 安装测试依赖\n", "      - name: 别的步骤\n"),
            "pip install 换了写法": MINIMAL_GATE_WORKFLOW.replace(
                "run: python3 -m pip install '.[dev]'", "run: python3 -m pip install -r requirements.txt"
            ),
            "缺 python-version": MINIMAL_GATE_WORKFLOW.replace("          python-version: '3.12'\n", ""),
        }
        for label, text in broken_inputs.items():
            with self.subTest(label=label):
                with self.assertRaises(GATE_SPEC.GateSpecError):
                    GATE_SPEC.parse_gate_spec(text)


class GateSpecOnTheRealWorkflowsTest(unittest.TestCase):
    """对当前真实的 ci.yml / story.yml 各解析一次，锁住「现在读到的就是这些值」。

    工作流真的改了 extras 或 Python 版本时这两条会红——这正是意图：它是「本机与门禁
    同一事实源」唯一会随门禁一起变红的用例，需要有人有意识地同步期望值。
    shellcheck 的版本不在这里读：它锁在 pyproject.toml 的 dev 组里，CI 与本机通过同一个
    extras 取得同一份，从工作流里再读一遍只会多出一个会漂移的副本。
    """

    def test_real_gate_job(self) -> None:
        spec = GATE_SPEC.load_gate_spec()
        self.assertEqual(spec.extras, ["dev"])
        self.assertEqual(spec.python_version, "3.12")

    def test_real_fast_job(self) -> None:
        spec = GATE_SPEC.load_fast_spec()
        self.assertEqual(spec.extras, ["dev"])
        self.assertEqual(spec.python_version, "3.12")

    def test_shellcheck_version_is_pinned_exactly_once_in_pyproject(self) -> None:
        pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('dev = ["shellcheck-py==0.11.0.1"]', pyproject)
        for workflow in ("ci.yml", "story.yml"):
            with self.subTest(workflow=workflow):
                text = (REPOSITORY_ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
                self.assertNotIn("pip install 'shellcheck-py", text)


if __name__ == "__main__":
    unittest.main()
