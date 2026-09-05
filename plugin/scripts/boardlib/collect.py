# -*- coding: utf-8 -*-
"""证据采集（接口约定 §6）。归属：S-2。只采集、不判断；失败 → ProviderResult.ok=False，不抛异常、不给默认值。

必须实现：
    class LiveSource(repo_root, per_cmd_timeout=25, round_timeout=60)
        run(key, argv_or_cmd, *, shell=False, timeout=None, grade=Grade.MEASURED) -> ProviderResult
        （subprocess，stdin=DEVNULL，capture，超时 / 非零退出 / 解析失败都记 ok=False）
    class RecordedSource(fixture_dir)          # 从 snapshot.json 回放；没有的键 ok=False error="夹具未记录"
    collect(repo_root, trace_no, branch, conf, now, source) -> Snapshot
        - 解析 docs/traces/<n>-*/任务表.md（fixture 模式读 fixture_dir/任务表.md）
        - 并发跑内置证据键 git.* / gh.* / tmux.windows，再跑 conf 声明的 config.<key>（由 config.ShellProvider 执行）
        - 整轮受 round_timeout；超时的键 ok=False error="整轮超时"
    write_snapshot(snapshot, out_dir)          # --record
    resolve_trace(repo_root, trace_no=None) -> (trace_no, trace_dir, tasktable_path)
    resolve_branch(snapshot_or_prs, trace_no, conf, override=None) -> str  # 见约定 §2
"""
from __future__ import annotations


def collect(repo_root, trace_no, branch, conf, now, source):
    raise NotImplementedError("S-2：证据采集待实现")
