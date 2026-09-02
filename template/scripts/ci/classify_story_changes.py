#!/usr/bin/env python3
"""把 PR 改动路由到文档快检、普通快检或完整门禁。

出处：lingxi https://github.com/Moshuiwang/lingxi/issues/82（分层 CI；后续分级门禁沿用「未知路径一律升级」）；验证：2026-08-07 起约 250 个 PR 每次路由。

未知路径一律升级到完整门禁。分类器的目标不是猜得尽可能细，而是让新增目录不会因为
没人更新路径表而静默绕过检查。这里换成你的路径表：只改下面五个常量，不改判定顺序。
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


DOCUMENT_PREFIXES = ("docs/",)
DOCUMENT_FILES = {"AGENTS.md", "CLAUDE.md", "README.md", "CHANGELOG.md"}
FULL_PREFIXES = (".github/workflows/", "deploy/", "scripts/ci/", "migrations/")
FULL_FILES = {"Dockerfile", ".dockerignore", "pyproject.toml"}
FAST_PREFIXES = ("src/", "tests/", "scripts/dev/", "scripts/ops/")

# scripts/ci/ 整目录默认提级到完整门禁，但其中已知的纯数据文件（两份棘轮基线）不含可执行
# 逻辑、不改变门禁脚本本身的判定行为，因此显式登记后单独按 fast 处理。新增候选必须显式
# 写进这里——不在清单内的 scripts/ci/ 文件（哪怕文件名看起来也像数据）默认仍然提级，
# 防止「新增一个脚本文件、忘了登记」被静默当成数据放行。
FULL_PREFIX_DATA_FILES = frozenset(
    {
        "scripts/ci/size_ratchet_baseline.txt",
        "scripts/ci/matrix_row_size_baseline.txt",
    }
)


class Classification:
    """路由结论：``mode`` 是 docs/fast/full 三档之一，``docs_changed`` 记录本批是否碰了文档。"""

    __slots__ = ("mode", "docs_changed")

    def __init__(self, mode: str, docs_changed: bool) -> None:
        self.mode = mode
        self.docs_changed = docs_changed


def normalize_path(raw: str) -> str:
    """只剥掉 Git 可能带出的一个 ``./``，绝不 strip 文件名空白。"""

    return raw[2:] if raw.startswith("./") else raw


def normalized_paths(paths: list[str]) -> list[str]:
    return [normalize_path(path) for path in paths if path]


def is_document(path: str) -> bool:
    return path in DOCUMENT_FILES or path.startswith(DOCUMENT_PREFIXES)


def is_full(path: str) -> bool:
    if path in FULL_PREFIX_DATA_FILES:
        return False
    return path in FULL_FILES or path.startswith(FULL_PREFIXES)


def is_fast(path: str) -> bool:
    return path.startswith(FAST_PREFIXES) or path in FULL_PREFIX_DATA_FILES


def classify_detail(paths: list[str]) -> Classification:
    """返回路由结论；未知路径始终走完整门禁，空改动集同样失败关闭到 full。"""

    normalized = normalized_paths(paths)
    if not normalized:
        return Classification("full", False)

    docs_changed = any(is_document(path) for path in normalized)

    # 高风险路径与任何其他改动混合时都不能降级：先判 full，再判纯文档，再判快检。
    if any(is_full(path) for path in normalized):
        return Classification("full", docs_changed)

    if all(is_document(path) for path in normalized):
        return Classification("docs", docs_changed)

    if all(is_document(path) or is_fast(path) for path in normalized):
        return Classification("fast", docs_changed)

    return Classification("full", docs_changed)


def classify(paths: list[str]) -> str:
    """只要三档结论的调用方（本机分层 scripts/dev/local_layer.py 也走这里）。"""

    return classify_detail(paths).mode


def changed_paths(base: str, head: str, *, repository: Path | None = None) -> list[str]:
    result = subprocess.run(
        # 不过滤 D/T 等状态；并关闭 rename 折叠，让高风险旧路径和新路径都进入分类。
        # -z 让 Git 输出原始文件名并用 NUL 分隔；否则中文等非 ASCII 路径会被
        # core.quotePath 转义，docs/** 会被误判成未知高风险路径。bytes + surrogateescape
        # 还保留了不合法 UTF-8 文件名，使其无法被错误地折叠到安全路径。
        ["git", "-c", "core.quotePath=false", "diff", "--name-only", "-z", "--no-renames", base, head],
        check=True,
        capture_output=True,
        cwd=repository,
    )
    return [
        raw.decode("utf-8", errors="surrogateescape")
        for raw in result.stdout.split(b"\0")
        if raw
    ]


def write_output(destination: Path, classification: Classification) -> None:
    with destination.open("a", encoding="utf-8") as output:
        output.write(f"mode={classification.mode}\n")
        output.write(f"docs_changed={'true' if classification.docs_changed else 'false'}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()

    paths = changed_paths(args.base, args.head)
    classification = classify_detail(paths)
    write_output(args.github_output, classification)
    print(f"Story 路由：{classification.mode}（{len(paths)} 个变更路径）")
    for path in paths:
        print(f"  - {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
