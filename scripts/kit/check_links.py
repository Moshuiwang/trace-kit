#!/usr/bin/env python3
"""对套件仓库本身跑 template 里的 Markdown 链接检查（把仓库根从 template/ 换成套件根）。

不复制一份检查逻辑：直接加载 template/scripts/ci/check_markdown_links.py，改它的仓库根再调用。
出处：lingxi scripts/ci/check_markdown_links.py（分级清单 C4，G1）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = KIT_ROOT / "template" / "scripts" / "ci" / "check_markdown_links.py"


def main() -> int:
    spec = importlib.util.spec_from_file_location("check_markdown_links", CHECKER)
    if spec is None or spec.loader is None:
        print(f"找不到链接检查脚本：{CHECKER}", file=sys.stderr)
        return 1
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.REPOSITORY_ROOT = KIT_ROOT
    return int(module.main() or 0)


if __name__ == "__main__":
    sys.exit(main())
