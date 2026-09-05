# -*- coding: utf-8 -*-
"""证据源配置（接口约定 §9）。归属：S-4。项目专属证据全部经此声明；引擎不含任何项目名词。

必须实现：
    load(path: str | None) -> Config           # tomllib；未知键 → ConfigError（带行 / 键路径）；None → 空配置
    class Config: trace_number, trace_branch, repo_slug, tmux_session, window_pattern, release_workflow,
                  stages: dict[key -> CommandSpec], budgets: list[BudgetSpec], evidence: list[EvidenceSpec], raw: dict
    class CommandSpec: command, parse, timeout, grade, label, cap（预算用）
    class ShellProvider(per_cmd_timeout): run(spec, key) -> ProviderResult
        （bash -c，stdin=DEVNULL，超时；parse 规则 int / regex:<pat> / lines / json:<路径>；失败 ok=False）
    compare_tag(published: str | None, got: ProviderResult) -> Val   # 阶段比对：== → True，!= → False，不可得 → 未知
"""
from __future__ import annotations


class ConfigError(ValueError):
    pass


def load(path):
    raise NotImplementedError("S-4：证据源配置待实现")
