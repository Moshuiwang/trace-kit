# -*- coding: utf-8 -*-
"""状态 → 证据登记表（https://github.com/Moshuiwang/lingxi/issues/579 关卡 1：代码常量与文档同源；新增状态未登记即单测红）。

`board.py --registry` 打印 Markdown；S-6 的 SKILL.md 登记表节由此生成，S-5 单测比对两者一致。
本文件由 S-2 定稿（编排者种子基础上增补证据类型；状态一个不删）：
- 每个状态列出 infer.py 实际用到的证据类型；`unknown` 列出「可能不可得」的键对应的类型；
- 五级阶段与头部各项（阻塞 / 存疑 / 轮数 / 窗口 / 预算）也登记，便于 `--why` 回读。
"""
from __future__ import annotations

from .model import EvidenceType as E, Status

EVIDENCE_REGISTRY: dict[Status, tuple[E, ...]] = {
    Status.DONE: (E.CHECKBOX, E.PR_STATE, E.COMMIT_TIME, E.COMMENT_TITLE),
    Status.DONEQ: (E.CHECKBOX, E.PR_STATE, E.COMMIT_TIME, E.COMMENT_TITLE),
    Status.HUMAN: (E.TASKTABLE_TAG, E.CHECKBOX),
    Status.RUNNING: (E.COMMIT_TIME, E.WORKTREE, E.PR_STATE, E.CI_CONCLUSION, E.COMMENT_TITLE),
    Status.WATCH: (E.COMMIT_TIME, E.WORKTREE, E.PR_STATE, E.CI_CONCLUSION, E.COMMENT_TITLE),
    Status.STALLED: (E.COMMIT_TIME, E.WORKTREE, E.PR_STATE, E.CI_CONCLUSION, E.COMMENT_TITLE),
    Status.READY: (E.CHECKBOX,),
    Status.TODO: (E.CHECKBOX,),
    Status.STALE: (E.SHA_EQUAL, E.TASKTABLE_TAG, E.CHECKBOX),
    Status.UNKNOWN: (E.COMMIT_TIME, E.PR_STATE, E.COMMENT_TITLE, E.CI_CONCLUSION, E.WORKTREE, E.SHA_EQUAL, E.CHECKBOX, E.CONFIG_COMMAND),
}

STAGE_REGISTRY: dict[str, tuple[str, tuple[E, ...]]] = {
    "merged": ("合入主干", (E.PR_STATE,)),  # 只认唯一识别的批次 PR；无批次分支＝不适用
    "published": ("已发布", (E.WORKFLOW_RUN, E.TAG_REF, E.PR_STATE)),  # 须有已证实的合并点；tag 以 gh.tags 为权威，祖先关系优先 gh.compare
    "staging": ("预发已升级", (E.IMAGE_TAG, E.CONFIG_COMMAND)),
    "production": ("已上生产", (E.IMAGE_TAG, E.CONFIG_COMMAND)),
    "closed": ("收口", (E.ISSUE_STATE,)),
}

HEADER_REGISTRY: dict[str, tuple[str, tuple[E, ...]]] = {
    "block": ("阻塞（当前：卡住步骤 / 最近完成的 CI run 红 / 审核结论失效 / 阶段未知 / 编排窗口不在 / 暂停中）",
              (E.COMMIT_TIME, E.PR_STATE, E.COMMENT_TITLE, E.CI_CONCLUSION, E.SHA_EQUAL, E.TMUX_WINDOW, E.TASKTABLE_TAG)),
    "next": ("下一步（首个未勾选 Step ＋ worktree 数）", (E.CHECKBOX, E.WORKTREE)),
    "budget": ("预算（配置计数条；无配置只列 PR 数与 CI 次数）", (E.CONFIG_COMMAND, E.PR_STATE, E.WORKFLOW_RUN)),
    "doubt": ("存疑（自述未证 / 合同 PR 自合零批准 / 共用 PR / PR 自合计数 / 历史最大空档含暂停归因）",
              (E.CHECKBOX, E.PR_MERGED_BY, E.PR_STATE, E.COMMIT_TIME, E.TASKTABLE_TAG)),
    "rounds": ("轮数（审 / 外 / 修＝评论首行匹配，归属 Step ID 实 → 活动窗口 推 → Trace 级；CI 红绿＝活动窗口内 run 结论）", (E.COMMENT_TITLE, E.CI_CONCLUSION)),
    "evidence": ("最后外部证据（含 [[evidence]] 附加证据行）", (E.COMMIT_TIME, E.PR_STATE, E.COMMENT_TITLE, E.CI_CONCLUSION, E.WORKTREE, E.CONFIG_COMMAND)),
}

STATUS_LABEL = {
    Status.TODO: "待做", Status.READY: "下一步", Status.RUNNING: "运行中", Status.WATCH: "观察",
    Status.STALLED: "卡住", Status.HUMAN: "待人类", Status.DONE: "完成", Status.DONEQ: "自述未证",
    Status.STALE: "失效", Status.UNKNOWN: "未知",
}

STATUS_RULE = {
    Status.TODO: "未勾选、无证据、依赖状态未全部 ∈ {完成, 自述未证}",
    Status.READY: "未勾选、无证据、依赖状态全部 ∈ {完成, 自述未证}",
    Status.RUNNING: "未勾选、60 分钟内有归属证据",
    Status.WATCH: "未勾选、最近证据 60–90 分钟前",
    Status.STALLED: "未勾选、最近证据 > 90 分钟前",
    Status.HUMAN: "`t:human` 且未勾选",
    Status.DONE: "已勾选且有独立制品（PR MERGED / 触及 Trace 目录外文件的提交 / 指针指向的评论）",
    Status.DONEQ: "已勾选但无独立制品（只改任务表的提交、评论提及只算活动证据）",
    Status.STALE: "`t:review` / `t:gate` 指针 SHA ≠ 分支 HEAD（远端 head 优先，本地分支备用；已勾选亦失效）",
    Status.UNKNOWN: "判定所需证据键 ok=False，或依赖不存在 / 成环，或候选 HEAD 不可得（不回落）",
}


def check_complete() -> list[str]:
    """返回未登记的状态名列表（应为空）。"""
    missing = [s.value for s in Status if s not in EVIDENCE_REGISTRY or not EVIDENCE_REGISTRY[s]]
    missing += [s.value + "(label)" for s in Status if s not in STATUS_LABEL]
    missing += [s.value + "(rule)" for s in Status if s not in STATUS_RULE]
    return missing


def render_markdown() -> str:
    lines = ["| 状态 | 判定 | 判定用证据类型 |", "| --- | --- | --- |"]
    for s in Status:
        lines.append("| %s `%s` | %s | %s |" % (STATUS_LABEL[s], s.value, STATUS_RULE[s], " / ".join(e.value for e in EVIDENCE_REGISTRY.get(s, ()))))
    lines += ["", "| 阶段 | 证据类型 |", "| --- | --- |"]
    for key, (label, evs) in STAGE_REGISTRY.items():
        lines.append("| %s `%s` | %s |" % (label, key, " / ".join(e.value for e in evs)))
    lines += ["", "| 头部项 | 证据类型 |", "| --- | --- |"]
    for key, (label, evs) in HEADER_REGISTRY.items():
        lines.append("| %s `%s` | %s |" % (label, key, " / ".join(e.value for e in evs)))
    return "\n".join(lines) + "\n"
