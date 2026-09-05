# -*- coding: utf-8 -*-
"""看板数据模型（接口约定 §4 的代码形态；出处：trace-kit #12 v3、https://github.com/Moshuiwang/lingxi/issues/577 子清单 #578 / #579 / #581 / #589）。

所有模块只通过这里的类型交换数据。改字段先改本文件与 docs/traces/<trace>/接口约定.md，再改调用方。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class Status(str, Enum):
    """九色 + 未知（#12 v2 第 3 条；https://github.com/Moshuiwang/lingxi/issues/579「未知」不回落）。"""

    TODO = "todo"
    READY = "ready"
    RUNNING = "running"
    WATCH = "watch"
    STALLED = "stalled"
    HUMAN = "human"
    DONE = "done"
    DONEQ = "doneq"
    STALE = "stale"
    UNKNOWN = "unknown"


class Grade(str, Enum):
    """数字来源等级（https://github.com/Moshuiwang/lingxi/issues/581）：实测 / 自报 / 推断。"""

    MEASURED = "measured"
    REPORTED = "reported"
    INFERRED = "inferred"


GRADE_MARK = {Grade.MEASURED: "实", Grade.REPORTED: "报", Grade.INFERRED: "推"}


class Tier(int, Enum):
    """边框档位 = 审核轮数（决策清单 D-1）。"""

    NONE = 0
    ONE = 1
    TWO = 2
    THREE = 3
    MORE = 4


class StepType(str, Enum):
    IMPL = "impl"
    REVIEW = "review"
    GATE = "gate"
    HUMAN = "human"
    DEPLOY = "deploy"
    RESEARCH = "research"
    CONTRACT = "contract"


class EvidenceType(str, Enum):
    """登记表用的结构化证据类型（https://github.com/Moshuiwang/lingxi/issues/579 关卡 1）。"""

    CHECKBOX = "checkbox"
    TASKTABLE_TAG = "tasktable_tag"
    PR_STATE = "pr_state"
    PR_MERGED_BY = "pr_merged_by"
    CI_CONCLUSION = "ci_conclusion"
    WORKFLOW_RUN = "workflow_run"
    COMMIT_TIME = "commit_time"
    COMMENT_TITLE = "comment_title"
    ISSUE_STATE = "issue_state"
    WORKTREE = "worktree"
    SHA_EQUAL = "sha_equal"
    TAG_REF = "tag_ref"
    TMUX_WINDOW = "tmux_window"
    IMAGE_TAG = "image_tag"
    CONFIG_COMMAND = "config_command"
    FILE_EXISTS = "file_exists"


def utc(dt: Optional[datetime]) -> Optional[datetime]:
    """统一为带时区的 UTC；朴素时间视为 UTC。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_ts(text: str) -> Optional[datetime]:
    """解析 ISO8601（含 `Z`）；解析失败返回 None，不抛异常。"""
    if not text:
        return None
    try:
        return utc(datetime.fromisoformat(text.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


def beijing(dt: Optional[datetime], fmt: str = "%H:%M") -> str:
    """显式换算 UTC+8（https://github.com/Moshuiwang/lingxi/issues/577 已修项）；None → `?`。"""
    from datetime import timedelta

    if dt is None:
        return "?"
    return (utc(dt) + timedelta(hours=8)).strftime(fmt)


@dataclass
class Val:
    """带来源角标的取值；`available=False` 渲染为「未知」。"""

    value: Any
    grade: Grade = Grade.MEASURED
    source: str = ""
    at: Optional[datetime] = None
    available: bool = True

    def text(self) -> str:
        if not self.available:
            return "未知"
        return "%s%s" % (self.value, GRADE_MARK[self.grade])

    @staticmethod
    def unknown(source: str = "", grade: Grade = Grade.MEASURED) -> "Val":
        return Val(None, grade, source, None, False)


@dataclass
class Why:
    """`--why` 证据链一行：对象 | 状态 | 证据类型 | 来源 | 取值 | 时间 | 可得。"""

    subject: str
    status: str
    evidence: EvidenceType
    source: str
    value: str
    at: Optional[datetime] = None
    available: bool = True


@dataclass
class Step:
    id: str
    title: str
    checked: bool
    section: int
    line_no: int
    type: StepType = StepType.IMPL
    needs: list[str] = field(default_factory=list)
    owner: str = ""
    est_min: Optional[int] = None
    prs: list[int] = field(default_factory=list)
    shas: list[str] = field(default_factory=list)
    comments: list[int] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    raw: str = ""


@dataclass
class Section:
    index: int
    title: str
    steps: list[Step] = field(default_factory=list)


@dataclass
class TaskTable:
    path: str
    sections: list[Section]
    unparsed: list[tuple[int, str]] = field(default_factory=list)
    overlong: list[tuple[int, str]] = field(default_factory=list)

    @property
    def steps(self) -> list[Step]:
        return [s for sec in self.sections for s in sec.steps]


@dataclass
class ProviderResult:
    key: str
    ok: bool
    value: Any = None
    error: str = ""
    cmd: str = ""
    fetched_at: Optional[datetime] = None
    grade: Grade = Grade.MEASURED


@dataclass
class Snapshot:
    """一次采集的全部原始证据；可 JSON 往返（夹具回放）。"""

    now: datetime
    repo: str
    trace_no: int
    trace_dir: str
    branch: str
    tasktable: TaskTable
    results: dict[str, ProviderResult] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str) -> ProviderResult:
        return self.results.get(key) or ProviderResult(key, False, None, "未采集")

    def to_json(self) -> str:
        def enc(o: Any) -> Any:
            if isinstance(o, datetime):
                return utc(o).isoformat()
            if isinstance(o, Enum):
                return o.value
            raise TypeError(type(o).__name__)

        payload = {
            "now": utc(self.now).isoformat(),
            "repo": self.repo,
            "trace_no": self.trace_no,
            "trace_dir": self.trace_dir,
            "branch": self.branch,
            "tasktable_path": self.tasktable.path,
            "results": {k: asdict(v) for k, v in self.results.items()},
            "config": self.config,
        }
        return json.dumps(payload, ensure_ascii=False, indent=1, default=enc)

    @staticmethod
    def from_json(text: str, tasktable: TaskTable) -> "Snapshot":
        d = json.loads(text)
        results = {}
        for k, v in d.get("results", {}).items():
            results[k] = ProviderResult(
                key=v["key"], ok=bool(v["ok"]), value=v.get("value"), error=v.get("error", ""),
                cmd=v.get("cmd", ""), fetched_at=parse_ts(v.get("fetched_at") or ""),
                grade=Grade(v.get("grade", "measured")),
            )
        return Snapshot(
            now=parse_ts(d["now"]) or datetime.now(timezone.utc), repo=d.get("repo", ""),
            trace_no=int(d.get("trace_no", 0)), trace_dir=d.get("trace_dir", ""),
            branch=d.get("branch", ""), tasktable=tasktable, results=results, config=d.get("config", {}),
        )


@dataclass
class StepView:
    step: Step
    status: Status
    started: Optional[datetime] = None
    last_evidence: Optional[datetime] = None
    actual_min: Optional[int] = None
    elapsed_min: Optional[int] = None
    est_min: Optional[int] = None
    chip: str = ""
    chip_status: Status = Status.TODO
    rework: bool = False
    why: list[Why] = field(default_factory=list)


@dataclass
class Rounds:
    review: Val
    external: Val
    fixpack: Val
    ci_red: Val
    ci_green: Val


@dataclass
class ModuleView:
    section: Section
    status: Status
    tier: Tier
    rounds: Rounds
    done: int
    total: int
    what: str
    rounds_line: str
    evidence_line: str
    actual_min: Optional[int] = None
    elapsed_min: Optional[int] = None
    est_min: Optional[int] = None
    needs: list[int] = field(default_factory=list)
    why: list[Why] = field(default_factory=list)


@dataclass
class StageLevel:
    """五级阶段之一（https://github.com/Moshuiwang/lingxi/issues/589）；`value.value` ∈ True / False，`available=False` 为未知，`configured=False` 为未配置。"""

    key: str
    label: str
    value: Val
    configured: bool = True


@dataclass
class Header:
    title: str
    stage: str
    block: str
    nxt: str
    budget: list[tuple[str, Val, Optional[int]]]
    doubt: str
    evidence: str
    stages: list[StageLevel] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Board:
    header: Header
    steps: list[StepView]
    modules: list[ModuleView]
    generated_at: datetime
    why: list[Why] = field(default_factory=list)
    unparsed: list[tuple[int, str]] = field(default_factory=list)  # 任务表无法解析的行（行号, 原文）：复杂版画成灰色自由文本卡片（#12 v2 关卡 3）

    def validate(self) -> None:
        """结构断言（https://github.com/Moshuiwang/lingxi/issues/582）：状态串 / 档位 / 角标 / 索引写错即报错，不静默。"""
        n = len(self.modules)
        for sv in self.steps:
            if not isinstance(sv.status, Status) or not isinstance(sv.chip_status, Status):
                raise ValueError("StepView %s 状态不是 Status：%r" % (sv.step.id, sv.status))
        for mv in self.modules:
            if not isinstance(mv.status, Status):
                raise ValueError("ModuleView %s 状态不是 Status：%r" % (mv.section.title, mv.status))
            if not isinstance(mv.tier, Tier):
                raise ValueError("ModuleView %s 档位不是 Tier：%r" % (mv.section.title, mv.tier))
            for v in (mv.rounds.review, mv.rounds.external, mv.rounds.fixpack, mv.rounds.ci_red, mv.rounds.ci_green):
                if not isinstance(v, Val) or not isinstance(v.grade, Grade):
                    raise ValueError("ModuleView %s 轮数不是 Val/Grade：%r" % (mv.section.title, v))
            for k in mv.needs:
                if not (0 <= k < n):
                    raise ValueError("ModuleView %s 依赖索引越界：%d" % (mv.section.title, k))
        for label, val, cap in self.header.budget:
            if not isinstance(val, Val) or not isinstance(val.grade, Grade):
                raise ValueError("预算条 %s 不是 Val/Grade" % label)
        for st in self.header.stages:
            if not isinstance(st.value, Val):
                raise ValueError("阶段 %s 不是 Val" % st.key)
