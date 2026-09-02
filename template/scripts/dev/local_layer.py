#!/usr/bin/env python3
"""本机分层判定：直接加载 CI 用来路由 PR 的同一份 `classify_story_changes.py`。

出处：lingxi https://github.com/Moshuiwang/lingxi/issues/236；验证：5 个批次收口前「本机 full 绿」。

「本机分层验证的分层结果与 CI 的分层判定一致」最可靠的办法不是照抄一份判定规则（两份规则
迟早漂移），而是**不重新实现**——本文件按路径加载 `scripts/ci/classify_story_changes.py`
并直接调用它的 `classify()`，本机与 CI 因此是同一段代码在做判断。

与 CI 不同的一点：CI 的分类器只比较两个已提交的 SHA；本机日常回路默认还要把工作树里
**未提交**的改动算进去（否则「先跑分层验证再决定要不要提交」这个顺序就用不了），
可用 `--committed-only` 关掉，退回成与 CI 完全相同的「只看已提交的两个引用之间」。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER_PATH = REPO_ROOT / "scripts" / "ci" / "classify_story_changes.py"


def _load_classifier():
    spec = importlib.util.spec_from_file_location("classify_story_changes_shared", CLASSIFIER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # 动态加载前先登记模块，和测试加载器同一纪律（模块内若用到 dataclass 会回查 sys.modules）。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# 模块加载一次、进程内复用；`__file__` 指回 scripts/ci/classify_story_changes.py，
# 用例据此断言本文件确实没有另起一份判定规则。
_CLASSIFIER = _load_classifier()


def changed_paths_against(
    base: str,
    *,
    include_worktree: bool = True,
    repository: Path | None = None,
) -> list[str]:
    """相对 `base` 的改动路径。

    `include_worktree=True`（默认）时把未提交（含已 add 未 commit）的改动一并算入，
    对应本机日常「改完还没提交、想知道会跑哪一层」；`include_worktree=False` 时只看
    `base` 到 `HEAD` 之间已提交的差异，与 CI 分类器实际比较两个 SHA 的口径一致。
    """

    args = ["git", "-c", "core.quotePath=false", "diff", "--name-only", "-z", "--no-renames", base]
    if not include_worktree:
        args.append("HEAD")
    result = subprocess.run(args, check=True, capture_output=True, cwd=repository)
    paths = [
        raw.decode("utf-8", errors="surrogateescape")
        for raw in result.stdout.split(b"\0")
        if raw
    ]

    if include_worktree:
        # `git diff` 默认不认「尚未 add 过的新文件」——它们连 index 都没进，diff 找不到
        # 比较对象。日常回路里「新建了一个文件、还没 git add」是常态，漏掉这类文件会让
        # 本机分层判定看不见真正要新增的高风险路径（例如新脚本落在 scripts/ci/ 下）。
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            check=True,
            capture_output=True,
            cwd=repository,
        )
        untracked_paths = [
            raw.decode("utf-8", errors="surrogateescape")
            for raw in untracked.stdout.split(b"\0")
            if raw
        ]
        paths.extend(path for path in untracked_paths if path not in paths)

    return paths


def classify_local(
    base: str,
    *,
    include_worktree: bool = True,
    repository: Path | None = None,
) -> str:
    """本机分层结论：与 `scripts/ci/classify_story_changes.classify` 同一函数、同一结论。"""

    paths = changed_paths_against(base, include_worktree=include_worktree, repository=repository)
    return _CLASSIFIER.classify(paths)


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="main", help="对比基线（默认 main）")
    parser.add_argument(
        "--committed-only",
        action="store_true",
        help="只看 base..HEAD 已提交的差异，不含工作树未提交内容（与 CI 口径一致）",
    )
    args = parser.parse_args()

    try:
        print(classify_local(args.base, include_worktree=not args.committed_only))
    except subprocess.CalledProcessError as error:
        print(f"local_layer：git diff 失败（{error}）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
