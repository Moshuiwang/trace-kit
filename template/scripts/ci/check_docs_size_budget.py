#!/usr/bin/env python3
"""开工必读集体量预算：必读文档的合计字节数设硬上限，超限即红。

出处：lingxi https://github.com/Moshuiwang/lingxi/blob/caa845d77fbd2d6381de304dc6047498aa84c782/scripts/ci/check_docs_size_budget.py（2026-08-24 维护批 PR #299 建立，PR #520 扩容留痕）；验证：2 次上限调整 + 约 100 个 PR。

`AGENTS.md` 把「实现或修改正式代码前必读」定为 AGENTS.md 本身 + 验证与门禁两份文档。
本检查给这组文档的合计字节数设硬上限：超限即红，逼迫瘦身而不是继续堆积——与代码的
体量棘轮（check_size_ratchet.py）同一思路。历史教训：必读文档曾分别长到 53KB 与 18.5KB，
其中大半是住错地方的实现编年史。

上限调整必须与实际瘦身 / 扩容一起发生在同一次改动里，且留下可审阅的 diff；
不接受"先抬上限再慢慢写"。这里换成你的必读集：改 ``BUDGET_FILES``，上限按实测留约 10% 余量。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

BUDGET_FILES = (
    "AGENTS.md",
    "docs/技术设计/验证与门禁.md",
)

# 合计上限（字节）。骨架初值 32KB：按上游瘦身后实测 29.7KB 留约 10% 余量定的那个数；
# 按本脚本自己的规则，调整必须与瘦身/扩容同批发生并留下理由。
TOTAL_BUDGET_BYTES = 32 * 1024


def main() -> int:
    sizes: list[tuple[str, int]] = []
    missing: list[str] = []
    for relative in BUDGET_FILES:
        path = REPOSITORY_ROOT / relative
        if not path.is_file():
            missing.append(relative)
            continue
        sizes.append((relative, path.stat().st_size))

    if missing:
        print("开工必读集体量预算：以下受预算约束的文件不存在（改名或删除时必须同步更新本检查）：", file=sys.stderr)
        for relative in missing:
            print(f"  - {relative}", file=sys.stderr)
        return 1

    total = sum(size for _, size in sizes)
    detail = "、".join(f"{relative}={size}B" for relative, size in sizes)
    if total > TOTAL_BUDGET_BYTES:
        print(
            f"开工必读集体量预算超限：合计 {total}B > 上限 {TOTAL_BUDGET_BYTES}B（{detail}）。"
            "请瘦身文档（编年史移到 Issue / PR / 模块 docstring），或在同一改动里带理由调整上限。",
            file=sys.stderr,
        )
        return 1

    print(f"开工必读集体量预算：合计 {total}B ≤ {TOTAL_BUDGET_BYTES}B（{detail}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
