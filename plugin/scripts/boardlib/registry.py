# -*- coding: utf-8 -*-
"""状态 → 证据登记表（https://github.com/Moshuiwang/lingxi/issues/579 关卡 1：代码常量与文档同源；新增状态未登记即单测红）。

`board.py --registry` 打印 Markdown；S-6 的 SKILL.md 登记表节由此生成，S-5 单测比对两者一致。
本文件由 S-2 定稿；下面是编排者按接口约定 §7 给的种子，S-2 可增补证据类型但不得删状态。
"""
from __future__ import annotations

from .model import EvidenceType as E, Status

EVIDENCE_REGISTRY: dict[Status, tuple[E, ...]] = {
    Status.DONE: (E.CHECKBOX, E.PR_STATE, E.COMMIT_TIME, E.COMMENT_TITLE),
    Status.DONEQ: (E.CHECKBOX,),
    Status.HUMAN: (E.TASKTABLE_TAG,),
    Status.RUNNING: (E.COMMIT_TIME, E.WORKTREE, E.PR_STATE, E.CI_CONCLUSION, E.COMMENT_TITLE),
    Status.WATCH: (E.COMMIT_TIME, E.WORKTREE, E.PR_STATE, E.CI_CONCLUSION, E.COMMENT_TITLE),
    Status.STALLED: (E.COMMIT_TIME, E.WORKTREE, E.PR_STATE, E.CI_CONCLUSION, E.COMMENT_TITLE),
    Status.READY: (E.CHECKBOX,),
    Status.TODO: (E.CHECKBOX,),
    Status.STALE: (E.SHA_EQUAL,),
    Status.UNKNOWN: (E.CONFIG_COMMAND,),
}

STAGE_REGISTRY: dict[str, tuple[str, tuple[E, ...]]] = {
    "merged": ("合入主干", (E.PR_STATE,)),
    "published": ("已发布", (E.WORKFLOW_RUN, E.TAG_REF)),
    "staging": ("预发已升级", (E.IMAGE_TAG, E.CONFIG_COMMAND)),
    "production": ("已上生产", (E.IMAGE_TAG, E.CONFIG_COMMAND)),
    "closed": ("收口", (E.ISSUE_STATE,)),
}

STATUS_LABEL = {
    Status.TODO: "待做", Status.READY: "下一步", Status.RUNNING: "运行中", Status.WATCH: "观察",
    Status.STALLED: "卡住", Status.HUMAN: "待人类", Status.DONE: "完成", Status.DONEQ: "自述未证",
    Status.STALE: "失效", Status.UNKNOWN: "未知",
}


def check_complete() -> list[str]:
    """返回未登记的状态名列表（应为空）。"""
    return [s.value for s in Status if s not in EVIDENCE_REGISTRY or not EVIDENCE_REGISTRY[s]]


def render_markdown() -> str:
    lines = ["| 状态 | 判定用证据类型 |", "| --- | --- |"]
    for s in Status:
        lines.append("| %s `%s` | %s |" % (STATUS_LABEL[s], s.value, " / ".join(e.value for e in EVIDENCE_REGISTRY.get(s, ()))))
    lines += ["", "| 阶段 | 证据类型 |", "| --- | --- |"]
    for key, (label, evs) in STAGE_REGISTRY.items():
        lines.append("| %s `%s` | %s |" % (label, key, " / ".join(e.value for e in evs)))
    return "\n".join(lines) + "\n"
