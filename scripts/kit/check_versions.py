#!/usr/bin/env python3
"""版本一致性检查：方法版本五处一致、套件版本三处一致。

- 方法：`METHOD.md` 标题「模板 vN」= 版本头「方法 **vN**」= 状态行「现行唯一方法入口，vN」= 第八节版本史最新条目「**vN，」
  = 骨架入口 `template/docs/协作/执行方法.md`「方法版本 vN」。
- 套件：`plugin/.claude-plugin/plugin.json` = `.claude-plugin/marketplace.json` = `CHANGELOG.md` 最上面一条版本标题；
  `METHOD.md` 版本头「随 trace-kit **vX.Y.Z** 发布」必须是 CHANGELOG 里存在的版本（只改工具的发版不动方法版本头）。
出处：CHANGELOG v0.8.0——手工同步已漂移 ≥ 3 次（v21 未同步、骨架入口停在 v22、marketplace.json 在 v0.4.0 漏升）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def first(pattern: str, text: str, what: str, errors: list[str]) -> str | None:
    m = re.search(pattern, text, re.M)
    if m is None:
        errors.append(f"找不到{what}（模式 {pattern!r}）")
        return None
    return m.group(1)


def main() -> int:
    errors: list[str] = []
    method = (ROOT / "METHOD.md").read_text(encoding="utf-8")
    title = first(r"^# 长期执行计划与 Execution Trace 模板 (v\d+)\s*$", method, "METHOD.md 标题版本", errors)
    header = first(r"^> \*\*版本\*\*：方法 \*\*(v\d+)\*\*", method, "METHOD.md 版本头方法版本", errors)
    status = first(r"^> \*\*状态：现行唯一方法入口，(v\d+)", method, "METHOD.md 状态行版本", errors)
    if "\n## 八、版本与来源" not in method:
        errors.append("找不到 METHOD.md 第八节标题「## 八、版本与来源」")
    history = first(r"^- \*\*(v\d+)[，/ ]", method.split("\n## 八、版本与来源", 1)[-1], "第八节最新版本条目", errors)
    entry = first(r"\*\*方法版本 (v\d+)\*\*", (ROOT / "template/docs/协作/执行方法.md").read_text(encoding="utf-8"), "骨架方法入口版本", errors)
    header_kit = first(r"^> \*\*版本\*\*：.*?随 trace-kit \*\*v(\d+\.\d+\.\d+)\*\*", method, "METHOD.md 版本头套件版本", errors)

    plugin = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))["plugins"][0]["version"]
    changelog_text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    changelog = first(r"^## (?:v(\d+\.\d+\.\d+)|\[\d+\.\d+\.\d+\])", changelog_text, "CHANGELOG 最新版本标题", errors)
    released = set(re.findall(r"^## (?:v|\[)(\d+\.\d+\.\d+)", changelog_text, re.M))
    if header_kit is not None and header_kit not in released:
        errors.append(f"METHOD.md 版本头的套件版本 v{header_kit} 在 CHANGELOG 里没有对应条目")

    methods = {"标题": title, "版本头": header, "状态行": status, "第八节最新条目": history, "骨架入口": entry}
    if len(set(methods.values())) != 1:
        errors.append(f"方法版本不一致：{methods}")
    kits = {"plugin.json": plugin, "marketplace.json": market, "CHANGELOG 最新标题": changelog}
    if len(set(kits.values())) != 1:
        errors.append(f"套件版本不一致：{kits}")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print(f"版本一致性：通过（方法 {title}；套件 v{plugin}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
