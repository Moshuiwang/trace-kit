# -*- coding: utf-8 -*-
"""状态推断（接口约定 §7）。归属：S-2。只判断、不取数据；每个判定都留 Why；不可得显示「未知」不回落。

    infer(snapshot: Snapshot, conf) -> Board
        - 步骤九色＋未知（§7.1）、模块聚合与三行文案（§7.2）、轮数与边框档位、时长（§7.3）、
          五级阶段（§7.4）、头六项（§7.5）、来源角标、Why 证据链（§7.6）；末尾 board.validate()

「有证据」的归属：提交信息 / 分支名 / worktree 目录名 / PR 标题正文 / 评论首行含 Step ID（词边界：前后不接字母数字，
后面不接 `-字母数字`，故 `S-2` 不命中 `S-2a` / `S-2-1`，但命中 `17-S-2`）。PR 归属优先级：任务表指针 > 标题 > 正文
（正文常罗列多个 Step，只在指针与标题都为空时用）。证据只取 Trace 窗口内的（Issue 创建 / 任务表首次提交 → Issue 关闭 / now），
避免同仓前后 Trace 的同名 Step 串线。评论轮数归属（§7.2）：首行含 Step ID → 该模块（实）；否则按评论时刻落在哪个模块的
活动窗口 [首证据, 末证据或 now]（推，重叠取最晚开始的）；都不命中记 Trace 级。
Why 的来源列只写证据键 / 结构名，不写命令原文（§7.6）；Board.why 只放 Trace 级行（阶段 / 头部 / 合同 PR），Step / 模块行在各自 view 里。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from . import registry
from .model import (
    Board, EvidenceType as E, Grade, Header, ModuleView, Rounds, Snapshot, StageLevel, Status, Step, StepType, StepView,
    Tier, Val, Why, beijing, parse_ts, utc,
)

RUNNING_MIN = 60
WATCH_MIN = 90
GAP_MIN = 60  # 存疑行登记「历史最大空档」的下限（分钟）
WAIT_MIN = 5  # 步骤内「等待」Why 行的下限（分钟）
CORE_KEYS = ("git.log", "gh.prs", "gh.issue")
LIVE_KEYS = ("git.log", "gh.prs", "gh.issue", "gh.runs", "git.worktrees")
ARTIFACT_KINDS = ("pr_merged", "commit", "comment")
RED = {"failure", "timed_out", "startup_failure", "action_required"}
GREEN = {"success"}
CHECK_RED = {"FAILURE", "TIMED_OUT", "CANCELLED", "ERROR", "ACTION_REQUIRED", "STARTUP_FAILURE"}
CHECK_RUNNING = {"IN_PROGRESS", "QUEUED", "PENDING", "WAITING", "REQUESTED"}

# 轮数正则（https://github.com/Moshuiwang/lingxi/issues/578 已定；只看评论首行）
REVIEW_RE = re.compile(r"审核[①②③④⑤]|审[①②③④⑤]|审核\s*[1-5]\s*轮|独立审核.*结论|定向复核.*结论|复核[①②③④⑤]")
EXTERNAL_RE = re.compile(r"外审|codex|agy", re.IGNORECASE)
EXTERNAL_RESULT_RE = re.compile(r"结论|账本")
FIXPACK_RE = re.compile(r"修复包")
PAUSE_RE = re.compile(r"暂停")
QUOTE_TIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\D{0,3}(\d{1,2}):(\d)([0-9xX])\s*(UTC|北京)?")
PR_SUFFIX_RE = re.compile(r"\(#(\d+)\)\s*$|Merge pull request #(\d+)")
STAGE_LABEL = {"merged": "合入主干", "published": "已发布", "staging": "预发已升级", "production": "已上生产", "closed": "收口"}
PR_STATE_TEXT = {"MERGED": "✓合入", "OPEN": "打开", "CLOSED": "关闭"}
WINDOW_NOTE = "窗口状态未知，需元守护核"
LABEL = registry.STATUS_LABEL


@dataclass
class Ev:
    """一条证据事件（内部用）。"""

    at: datetime
    kind: str
    etype: E
    source: str
    label: str
    steps: set
    grade: Grade = Grade.MEASURED
    ref: dict = field(default_factory=dict)


def _mins(delta: timedelta) -> int:
    return int(delta.total_seconds() / 60 + 0.5)


def _hms(delta: timedelta) -> str:
    s = int(delta.total_seconds())
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return ("%dh%02dm%02ds" % (h, m, sec)) if h else ("%dm%02ds" % (m, sec))


def _n(value: int, grade: Grade = Grade.MEASURED) -> str:
    """数字＋角标（实 / 报 / 推）。"""
    return Val(value, grade).text()


def _build_attr_re(ids) -> Optional["re.Pattern[str]"]:
    ids = sorted(set(i for i in ids if i), key=len, reverse=True)
    if not ids:
        return None
    return re.compile(r"(?<![0-9A-Za-z])(%s)(?![0-9A-Za-z]|-[0-9A-Za-z])" % "|".join(re.escape(i) for i in ids))


def _why(subject: str, status: str, etype: E, source: str, value: str, at: Optional[datetime] = None, available: bool = True) -> Why:
    return Why(subject, status, etype, source, value, at, available)


def _sha_eq(a: str, b: str) -> bool:
    return bool(a) and bool(b) and (a.startswith(b) or b.startswith(a))


class _Ctx:
    """把快照整理成事件表；所有判定函数只读这里。"""

    def __init__(self, snap: Snapshot, conf):
        self.snap = snap
        self.conf = conf
        self.now = utc(snap.now)
        self.cfg = dict(snap.config or {})
        self.table = snap.tasktable
        self.steps: list[Step] = list(self.table.steps)
        self.step_by_id = {s.id: s for s in self.steps}
        self.attr_re = _build_attr_re(s.id for s in self.steps)
        self.trace_re = re.compile(r"(?<![0-9A-Za-z#])#%d(?![0-9])" % snap.trace_no) if snap.trace_no else None
        self.warnings: list[str] = list(self.cfg.get("warnings") or [])
        self.checked_map: dict[str, bool] = {}
        self.module_windows: dict[int, tuple[Optional[datetime], Optional[datetime]]] = {}
        self._load()
        self._build_events()

    # ---------- 取数 ----------
    def ok(self, key: str) -> bool:
        return self.snap.get(key).ok

    def val(self, key: str, default: Any) -> Any:
        r = self.snap.get(key)
        return r.value if r.ok and r.value is not None else default

    def err(self, key: str) -> str:
        return self.snap.get(key).error

    def attr(self, text: str) -> set:
        if not text or self.attr_re is None:
            return set()
        return set(self.attr_re.findall(text))

    def _load(self) -> None:
        now = self.now
        self.commits: list[dict] = []
        for c in self.val("git.log", []):
            at = parse_ts(c.get("at") or "")
            if at is None:
                continue
            row = dict(c)
            row["_at"] = at
            self.commits.append(row)
        self.commit_by_sha = {c["sha"]: c for c in self.commits}
        issue = self.val("gh.issue", {}) or {}
        self.issue = issue
        self.issue_created = parse_ts(issue.get("createdAt") or "")
        closed_at = parse_ts(issue.get("closedAt") or "")
        self.issue_closed_at = closed_at if (closed_at and closed_at <= now and (issue.get("state") == "CLOSED")) else None
        self.comments: list[dict] = []
        for c in issue.get("comments") or []:
            at = parse_ts(c.get("createdAt") or "")
            if at is None or at > now:
                continue
            row = dict(c)
            row["_at"] = at
            row["_modules"] = set()
            row["_grade"] = Grade.MEASURED
            row["_window"] = None
            self.comments.append(row)
        hist = self.val("git.tasktable_history", {}) or {}
        self.history: list[dict] = []
        for h in hist.get("commits") or []:
            at = parse_ts(h.get("at") or "")
            if at is None:
                continue
            row = dict(h)
            row["_at"] = at
            self.history.append(row)
        self.history.sort(key=lambda h: h["_at"])
        self.first_checked: dict[str, tuple[datetime, str]] = {}
        self.quote_first: dict[str, tuple[datetime, str]] = {}
        for h in self.history:
            for sid in h.get("checked") or []:
                self.first_checked.setdefault(sid, (h["_at"], h.get("sha", "")))
            for q in h.get("quotes") or []:
                self.quote_first.setdefault(q, (h["_at"], h.get("sha", "")))
        starts = [t for t in (self.issue_created, self.history[0]["_at"] if self.history else None) if t]
        self.window_start = min(starts) if starts else None
        self.window_end = min(now, self.issue_closed_at) if self.issue_closed_at else now
        self.prs_all: list[dict] = []
        for p in self.val("gh.prs", []):
            row = dict(p)
            row["_created"] = parse_ts(p.get("createdAt") or "")
            merged = parse_ts(p.get("mergedAt") or "")
            closed = parse_ts(p.get("closedAt") or "")
            row["_merged"] = merged if (merged and merged <= now) else None
            if row["_merged"]:
                row["_state"] = "MERGED"
            elif closed and closed <= now and p.get("state") != "OPEN":
                row["_state"] = "CLOSED"
            else:
                row["_state"] = "OPEN"
            pointed = {s.id for s in self.steps if row.get("number") in s.prs}
            titled = self.attr(p.get("title", ""))
            row["_steps"] = (pointed | titled) or self.attr(p.get("body", ""))
            self.prs_all.append(row)
        self.prs = [p for p in self.prs_all if self._is_trace_pr(p)]
        self.pr_by_number = {p["number"]: p for p in self.prs}
        self.runs: list[dict] = []
        heads = {p.get("headRefName") for p in self.prs if p.get("headRefName")}
        for r in self.val("gh.runs", []):
            at = parse_ts(r.get("createdAt") or "")
            if at is None or not self.in_window(at):
                continue
            row = dict(r)
            row["_at"] = at
            steps: set = set()
            for p in self.prs:
                if r.get("headBranch") and r.get("headBranch") == p.get("headRefName"):
                    steps |= p["_steps"]
            c = self._commit_by_prefix(r.get("headSha") or "")
            if c is not None:
                steps |= self.attr(c.get("subject", ""))
            relevant = bool(self.snap.branch) or (r.get("headBranch") in heads) or (c is not None)
            if not relevant:
                continue
            row["_steps"] = steps
            self.runs.append(row)
        self.runs.sort(key=lambda r: r["_at"])
        self.tags: list[dict] = []
        for t in self.val("git.tags", []):
            at = parse_ts(t.get("at") or "")
            if at is None or at > now:
                continue
            row = dict(t)
            row["_at"] = at
            self.tags.append(row)
        self.gh_tags: list[dict] = []
        for t in self.val("gh.tags", []):
            row = dict(t)
            row["_at"] = parse_ts(t.get("at") or "")
            if row["_at"] is None:
                c = self._commit_by_prefix(t.get("sha") or "")
                row["_at"] = c["_at"] if c is not None else None
            if row["_at"] is not None and row["_at"] > now:
                continue
            self.gh_tags.append(row)
        self.branches: list[dict] = list(self.val("git.branches", []))
        self.worktrees: list[dict] = []
        for w in self.val("git.worktrees", []):
            row = dict(w)
            row["_at"] = parse_ts(w.get("last_at") or "")
            self.worktrees.append(row)
        self.branch_tip = ""
        if self.snap.branch:
            for b in self.branches:
                if b.get("name") in (self.snap.branch, "origin/" + self.snap.branch):
                    self.branch_tip = b.get("sha", "")
                    if b.get("name") == self.snap.branch:
                        break
        self.contract = self.val("git.contract", None)
        self.contract_pr: Optional[dict] = None
        if self.contract:
            sha = self.contract.get("sha", "")
            for p in self.prs_all:
                if sha and p.get("mergeCommit") and _sha_eq(sha, p["mergeCommit"]):
                    self.contract_pr = p
                    break
            if self.contract_pr is None:
                m = PR_SUFFIX_RE.search(self.contract.get("subject", ""))
                if m:
                    n = int(m.group(1) or m.group(2))
                    self.contract_pr = next((p for p in self.prs_all if p.get("number") == n), None)

    def _is_trace_pr(self, p: dict) -> bool:
        if any(p.get("number") in s.prs for s in self.steps):
            return True
        if self.snap.branch and p.get("headRefName") == self.snap.branch:
            return True
        created = p.get("_created")
        if created is None or not self.in_window(created):
            return False
        if p["_steps"]:
            return True
        if self.trace_re and (self.trace_re.search(p.get("title", "")) or self.trace_re.search(p.get("body", ""))):
            return True
        return False

    def _commit_by_prefix(self, sha: str) -> Optional[dict]:
        if not sha:
            return None
        c = self.commit_by_sha.get(sha)
        if c is not None:
            return c
        for full, row in self.commit_by_sha.items():
            if _sha_eq(full, sha):
                return row
        return None

    def in_window(self, at: Optional[datetime]) -> bool:
        if at is None:
            return False
        if self.window_start and at < self.window_start:
            return False
        return at <= self.window_end

    def effective_checked(self, step: Step) -> bool:
        """`--now` 早于首次勾选提交时按未勾选处理（只在有任务表历史时）。"""
        if not step.checked:
            return False
        if self.ok("git.tasktable_history") and step.id in self.first_checked and self.first_checked[step.id][0] > self.now:
            return False
        return True

    # ---------- 事件 ----------
    def _build_events(self) -> None:
        ev: list[Ev] = []
        if self.ok("git.log"):
            for c in self.commits:
                if not self.in_window(c["_at"]):
                    continue
                steps = self.attr(c.get("subject", "")) | self.attr(c.get("refs", ""))
                steps |= {s.id for s in self.steps if any(c["sha"].startswith(x) for x in s.shas)}
                if steps:
                    ev.append(Ev(c["_at"], "commit", E.COMMIT_TIME, "git.log", "commit %s" % c["sha"][:7], steps, ref=c))
        for p in self.prs:
            n = p.get("number")
            if p["_created"] and self.in_window(p["_created"]):
                ev.append(Ev(p["_created"], "pr_created", E.PR_STATE, "gh.prs", "PR #%s" % n, set(p["_steps"]), ref=p))
            if p["_merged"] and self.in_window(p["_merged"]):
                ev.append(Ev(p["_merged"], "pr_merged", E.PR_STATE, "gh.prs", "PR #%s 合入" % n, set(p["_steps"]), ref=p))
        for c in self.comments:
            if not self.in_window(c["_at"]):
                continue
            steps = self.attr(c.get("first_line", "")) | {s.id for s in self.steps if c.get("id") in s.comments}
            c["_steps"] = steps
            ev.append(Ev(c["_at"], "comment", E.COMMENT_TITLE, "gh.issue", "评论 %s" % c.get("id"), steps, ref=c))
        for r in self.runs:
            ev.append(Ev(r["_at"], "run", E.CI_CONCLUSION, "gh.runs", "CI %s %s" % (r.get("workflowName") or r.get("name"), r.get("conclusion") or r.get("status")),
                         set(r["_steps"]), Grade.INFERRED, ref=r))
        for w in self.worktrees:
            if w.get("main") or w["_at"] is None or not self.in_window(w["_at"]):
                continue
            steps = self.attr(w.get("name", "")) | self.attr(w.get("branch", ""))
            if steps:
                ev.append(Ev(w["_at"], "worktree", E.WORKTREE, "git.worktrees", "wt %s" % w.get("name"), steps, ref=w))
        for sid, (at, sha) in self.first_checked.items():
            if sid in self.step_by_id and self.in_window(at):
                ev.append(Ev(at, "checkbox", E.CHECKBOX, "git.tasktable_history", "勾选 %s" % sha[:7], {sid}, Grade.INFERRED, ref={"sha": sha}))
        ev.sort(key=lambda e: e.at)
        self.events = ev
        self.step_events: dict[str, list[Ev]] = {s.id: [] for s in self.steps}
        for e in ev:
            for sid in e.steps:
                if sid in self.step_events:
                    self.step_events[sid].append(e)
        self.step_work_events = [e for e in ev if e.steps and e.kind != "checkbox"]
        # 暂停区间（任务表引用块含时刻与「暂停」；自报级）
        self.pauses: list[dict] = []
        quotes = list(self.quote_first.keys())
        for q in self.val("tasktable.quotes", []) or []:
            if q not in quotes:
                quotes.append(q)
        for q in quotes:
            if not PAUSE_RE.search(q):
                continue
            start, src, grade = None, "", Grade.INFERRED
            if q in self.quote_first:
                start, sha = self.quote_first[q]
                src = "git.tasktable_history %s" % sha[:7]
            else:
                m = QUOTE_TIME_RE.search(q)
                if m:
                    minute = int(m.group(3)) * 10 + (0 if m.group(4).lower() == "x" else int(m.group(4)))
                    start = parse_ts("%sT%02d:%02d:00+00:00" % (m.group(1), int(m.group(2)), minute))
                    if start and m.group(5) == "北京":
                        start = start - timedelta(hours=8)
                    src, grade = "tasktable.quotes（行内时刻）", Grade.REPORTED
            if start is None or start > self.now:
                continue
            end = next((e.at for e in self.step_work_events if e.at > start), None)
            self.pauses.append({"start": start, "end": end, "line": q, "source": src, "grade": grade})
        self.pauses.sort(key=lambda p: p["start"])

    # ---------- 评论归属（§7.2：Step ID → 时间窗回落 → Trace 级） ----------
    def assign_comments(self, windows: dict[int, tuple[Optional[datetime], Optional[datetime]]]) -> None:
        self.module_windows = windows
        for c in self.comments:
            if not self.in_window(c["_at"]):
                continue
            explicit = {self.step_by_id[s].section for s in (c.get("_steps") or set()) if s in self.step_by_id}
            if explicit:
                c["_modules"], c["_grade"], c["_window"] = explicit, Grade.MEASURED, None
                continue
            cands = [(start, idx) for idx, (start, end) in windows.items() if start is not None and start <= c["_at"] <= (end or self.now)]
            if cands:
                start, idx = max(cands)
                c["_modules"], c["_grade"], c["_window"] = {idx}, Grade.INFERRED, windows[idx]


# ---------------------------------------------------------------- 步骤
def _pr_self_merged(p: dict) -> bool:
    return bool(p.get("mergedBy")) and p.get("mergedBy") == p.get("author")


def _pr_approved(p: dict) -> bool:
    return any((r.get("state") or "").upper() == "APPROVED" for r in p.get("reviews") or [])


def _ci_hint(p: dict) -> str:
    checks = p.get("checks") or []
    if not checks:
        return ""
    concl = {(c.get("conclusion") or "").upper() for c in checks}
    status = {(c.get("status") or "").upper() for c in checks}
    if concl & CHECK_RED:
        return " · CI ✗"
    if status & CHECK_RUNNING or "" in concl:
        return " · CI 跑"
    return " · CI ✓"


def _step_view(ctx: _Ctx, step: Step, checked_map: dict[str, bool]) -> StepView:
    now = ctx.now
    evs = ctx.step_events.get(step.id, [])
    checked = checked_map[step.id]
    why: list[Why] = []
    artifacts = [e for e in evs if e.kind in ARTIFACT_KINDS]
    work = [e for e in evs if e.kind != "checkbox"]
    missing_core = [k for k in CORE_KEYS if not ctx.ok(k)]
    missing_live = [k for k in LIVE_KEYS if not ctx.ok(k)]
    last_work = max((e.at for e in work), default=None)
    status = Status.TODO
    etype, source, value, at, available = E.CHECKBOX, "任务表", "", None, True

    if step.checked and not checked:
        why.append(_why(step.id, LABEL[Status.TODO], E.CHECKBOX, "git.tasktable_history", "勾选提交晚于 --now，按未勾选处理", ctx.first_checked[step.id][0]))

    if checked:
        if artifacts:
            status = Status.DONE
            a = artifacts[-1]
            etype, source, value, at = a.etype, a.source, "已勾选 ＋ 独立制品 %s" % " / ".join(sorted({x.label for x in artifacts})[:4]), a.at
        elif missing_core:
            status = Status.UNKNOWN
            etype, source, value, available = E.CONFIG_COMMAND, " / ".join(missing_core), "已勾选，但制品证据不可得：" + "；".join("%s：%s" % (k, ctx.err(k)) for k in missing_core), False
        else:
            status = Status.DONEQ
            value = "已勾选，无独立制品（指针 PR / 提交 / 评论均未命中）"
    elif step.type == StepType.HUMAN:
        status = Status.HUMAN
        etype, source, value = E.TASKTABLE_TAG, "任务表 t:human", "待人类"
    else:
        stale = False
        if step.type == StepType.REVIEW and step.shas and ctx.branch_tip:
            if not any(_sha_eq(ctx.branch_tip, x) for x in step.shas):
                stale = True
        if stale:
            status = Status.STALE
            etype, source, value = E.SHA_EQUAL, "git.branches", "候选 %s ≠ 分支 HEAD %s" % (step.shas[-1][:7], ctx.branch_tip[:7])
        elif work:
            age = _mins(now - last_work)
            last = work[-1]
            etype, source, at = last.etype, last.source, last.at
            if age <= RUNNING_MIN:
                status = Status.RUNNING
                value = "%s 分钟前有证据 %s" % (_n(age), last.label)
            elif missing_live:
                status = Status.UNKNOWN
                etype, source, available = E.CONFIG_COMMAND, " / ".join(missing_live), False
                value = "最近证据 %s 分钟前，但 %s 不可得，无法排除更新证据" % (_n(age), " / ".join(missing_live))
            elif age <= WATCH_MIN:
                status = Status.WATCH
                value = "%s 分钟无新证据（最近 %s）" % (_n(age), last.label)
            else:
                status = Status.STALLED
                value = "%s 分钟无新证据（最近 %s）" % (_n(age), last.label)
        elif missing_live:
            status = Status.UNKNOWN
            etype, source, available = E.CONFIG_COMMAND, " / ".join(missing_live), False
            value = "无证据，且 %s 不可得" % " / ".join("%s（%s）" % (k, ctx.err(k)) for k in missing_live)
        else:
            deps = [d for d in step.needs if d in checked_map]
            if all(checked_map[d] for d in deps):
                status = Status.READY
                value = "无证据，依赖全部勾选（%s）" % (", ".join(deps) if deps else "无依赖")
            else:
                status = Status.TODO
                value = "无证据，依赖未完成：%s" % ", ".join(d for d in deps if not checked_map[d])
    why.insert(0, _why(step.id, LABEL[status], etype, source, value, at, available))

    started = min((e.at for e in work), default=None)
    last_any = max((e.at for e in evs), default=None)
    actual_min = elapsed_min = None
    if started is not None:
        if checked and last_any is not None:
            actual_min = _mins(last_any - started)
        elif not checked and status in (Status.RUNNING, Status.WATCH, Status.STALLED, Status.UNKNOWN, Status.STALE):
            elapsed_min = _mins(now - started)
    if evs:
        why.append(_why(step.id, "证据", evs[-1].etype, " / ".join(sorted({e.source for e in evs})),
                        "%s 条：%s" % (_n(len(evs)), "、".join(e.label for e in evs[:6]) + ("…" if len(evs) > 6 else "")), evs[-1].at))
    if len(evs) >= 2:
        i = max(range(len(evs) - 1), key=lambda k: evs[k + 1].at - evs[k].at)
        gap, (a, b) = evs[i + 1].at - evs[i].at, (evs[i], evs[i + 1])
        if gap >= timedelta(minutes=WAIT_MIN):
            why.append(_why(step.id, "等待", b.etype, "%s → %s" % (a.source, b.source),
                            "%s（%s %s → %s %s）" % (_hms(gap), a.label, beijing(a.at, "%m-%d %H:%M:%S"), b.label, beijing(b.at, "%m-%d %H:%M:%S")), b.at))
    chip, chip_status, rework = _chip(ctx, step, evs, status, checked, artifacts)
    return StepView(step=step, status=status, started=started, last_evidence=last_any, actual_min=actual_min, elapsed_min=elapsed_min,
                    est_min=step.est_min, chip=chip, chip_status=chip_status, rework=rework, why=why)


def _chip(ctx: _Ctx, step: Step, evs: list[Ev], status: Status, checked: bool, artifacts: list[Ev]) -> tuple[str, Status, bool]:
    now = ctx.now
    prs = {}
    for e in evs:
        if e.kind in ("pr_created", "pr_merged"):
            prs[e.ref["number"]] = e.ref
    pick = None
    pointer_prs = [prs[n] for n in step.prs if n in prs]
    if pointer_prs:
        pick = pointer_prs[-1]
    elif prs:
        pick = max(prs.values(), key=lambda p: p["_created"] or now)
    chip_status = status
    rework = False
    if status == Status.UNKNOWN:
        return "证据未知", Status.UNKNOWN, False
    if status == Status.STALE:
        return "候选 %s → 已变 %s" % (step.shas[-1][:6], ctx.branch_tip[:6]), Status.STALE, True
    if pick is not None:
        n = pick["number"]
        is_contract = ctx.contract_pr is not None and ctx.contract_pr.get("number") == n
        if pick["_state"] == "MERGED":
            text = "PR #%d ✓合入" % n
            if _pr_self_merged(pick):
                text += " · 自合"
            elif _pr_approved(pick):
                text += " · 批准"
            if is_contract and not _pr_approved(pick):
                text += " · 零批准"
                chip_status = Status.DONEQ
        elif pick["_state"] == "OPEN":
            text = "PR #%d %s%s" % (n, "草稿" if pick.get("isDraft") else "打开", _ci_hint(pick))
        else:
            text = "PR #%d 关闭" % n
        if checked and not artifacts:
            chip_status = Status.DONEQ
        return text, chip_status, rework
    commits = [e for e in evs if e.kind == "commit"]
    comments = [e for e in evs if e.kind == "comment"]
    wts = [e for e in evs if e.kind == "worktree"]
    runs = [e for e in evs if e.kind == "run"]
    if commits:
        c = commits[-1]
        if checked:
            return "commit %s ✓" % c.ref["sha"][:7], chip_status, rework
        return "commit %s · %dm 前" % (c.ref["sha"][:7], _mins(now - c.at)), chip_status, rework
    if comments:
        return "评论 ✓ %s" % beijing(comments[-1].at), chip_status, rework
    if wts:
        w = wts[-1]
        return "wt %s · %dm 前" % (w.ref.get("name", "")[:8], _mins(now - w.at)), chip_status, rework
    if runs:
        r = runs[-1]
        return "CI %s" % (r.ref.get("conclusion") or r.ref.get("status") or "?"), chip_status, rework
    if checked:
        return "无 commit · 无 PR", Status.DONEQ, rework
    return "待：PR / 评论", chip_status, rework


# ---------------------------------------------------------------- 模块
MODULE_PRIORITY = (Status.STALLED, Status.WATCH, Status.RUNNING, Status.STALE, Status.HUMAN, Status.UNKNOWN, Status.READY, Status.DONEQ, Status.TODO)


def _module_status(views: list[StepView]) -> Status:
    if not views:
        return Status.TODO
    statuses = [v.status for v in views]
    if all(s == Status.DONE for s in statuses):
        return Status.DONE
    if all(s in (Status.DONE, Status.DONEQ) for s in statuses):
        return Status.DONEQ
    for s in MODULE_PRIORITY:
        if s in statuses:
            return s
    return Status.TODO


def _tier(n: int) -> Tier:
    if n <= 0:
        return Tier.NONE
    if n == 1:
        return Tier.ONE
    if n == 2:
        return Tier.TWO
    if n == 3:
        return Tier.THREE
    return Tier.MORE


def _classify_comment(first_line: str) -> tuple[bool, bool, bool]:
    text = first_line.lstrip("#*> ").strip()
    review = bool(REVIEW_RE.search(text))
    external = bool(EXTERNAL_RE.search(text) and EXTERNAL_RESULT_RE.search(text))
    fixpack = bool(FIXPACK_RE.search(text))
    return review, external, fixpack


def _module_window(ctx: _Ctx, views: list[StepView]) -> tuple[Optional[datetime], Optional[datetime]]:
    """模块活动窗口 [首个证据, 末个证据（未全勾选则 now）]。"""
    work = [e for v in views for e in ctx.step_events.get(v.step.id, []) if e.kind != "checkbox"]
    allev = [e for v in views for e in ctx.step_events.get(v.step.id, [])]
    started = min((e.at for e in work), default=None)
    if started is None:
        return None, None
    finished = all(ctx.checked_map.get(v.step.id, False) for v in views)
    end = max((e.at for e in allev), default=None) if finished else ctx.now
    return started, end


def _rounds(ctx: _Ctx, section_index: Optional[int], window: tuple[Optional[datetime], Optional[datetime]], subject: str) -> tuple[Rounds, list[Why], int]:
    """section_index 为 None 时统计 Trace 级（未归属任何模块的评论）。返回 (Rounds, why, 评论条数)。"""
    why: list[Why] = []
    trace_level = section_index is None
    if not ctx.ok("gh.issue"):
        unk = Val.unknown("gh.issue")
        why.append(_why(subject, "轮数", E.COMMENT_TITLE, "gh.issue", "评论不可得：%s" % ctx.err("gh.issue"), None, False))
        n_comments = 0
        rounds = Rounds(unk, unk, unk, Val.unknown("gh.runs", Grade.INFERRED), Val.unknown("gh.runs", Grade.INFERRED))
    else:
        counts = {"审": [0, Grade.MEASURED], "外": [0, Grade.MEASURED], "修": [0, Grade.MEASURED]}
        n_comments = 0
        hits: list[str] = []
        for c in ctx.comments:
            if not ctx.in_window(c["_at"]):
                continue
            mods = c.get("_modules") or set()
            if trace_level:
                if mods:
                    continue
            elif section_index not in mods:
                continue
            n_comments += 1
            flags = dict(zip(("审", "外", "修"), _classify_comment(c.get("first_line", ""))))
            if not any(flags.values()):
                continue
            for k, hit in flags.items():
                if hit:
                    counts[k][0] += 1
                    if c["_grade"] == Grade.INFERRED:
                        counts[k][1] = Grade.INFERRED
            mark = "".join(k for k, hit in flags.items() if hit)
            if c["_grade"] == Grade.INFERRED and c.get("_window"):
                lo, hi = c["_window"]
                mark += "推（落在窗口 %s→%s）" % (beijing(lo), beijing(hi) if hi else "now")
            else:
                mark += "实"
            hits.append("%s %s「%s」" % (mark, beijing(c["_at"]), (c.get("first_line") or "").lstrip("#*> ")[:24]))
        rounds = Rounds(Val(counts["审"][0], counts["审"][1], "gh.issue"), Val(counts["外"][0], counts["外"][1], "gh.issue"),
                        Val(counts["修"][0], counts["修"][1], "gh.issue"), Val(0, Grade.INFERRED, "gh.runs"), Val(0, Grade.INFERRED, "gh.runs"))
        why.append(_why(subject, "轮数", E.COMMENT_TITLE, "gh.issue", "审 %s · 外 %s · 修 %s（评论 %s 条%s）" % (
            rounds.review.text(), rounds.external.text(), rounds.fixpack.text(), _n(n_comments), "；" + "；".join(hits[:4]) if hits else ""), None))
    if not ctx.ok("gh.runs"):
        rounds.ci_red = Val.unknown("gh.runs", Grade.INFERRED)
        rounds.ci_green = Val.unknown("gh.runs", Grade.INFERRED)
        why.append(_why(subject, "CI", E.CI_CONCLUSION, "gh.runs", "run 不可得：%s" % ctx.err("gh.runs"), None, False))
    else:
        red = green = 0
        lo, hi = window
        for r in ctx.runs:
            inside = True if trace_level else (lo is not None and lo <= r["_at"] <= (hi or ctx.now))
            if not inside:
                continue
            concl = (r.get("conclusion") or "").lower()
            if concl in GREEN:
                green += 1
            elif concl in RED:
                red += 1
        rounds.ci_red = Val(red, Grade.INFERRED, "gh.runs")
        rounds.ci_green = Val(green, Grade.INFERRED, "gh.runs")
        why.append(_why(subject, "CI", E.CI_CONCLUSION, "gh.runs", "红 %s 绿 %s（活动窗口 %s→%s）" % (
            rounds.ci_red.text(), rounds.ci_green.text(), beijing(lo) if lo else "?", beijing(hi) if hi else "now"), hi))
    return rounds, why, n_comments


def _module_view(ctx: _Ctx, section, views: list[StepView], n_sections: int) -> ModuleView:
    status = _module_status(views)
    done = sum(1 for v in views if ctx.checked_map.get(v.step.id, False))
    total = len(views)
    all_evs = [e for v in views for e in ctx.step_events.get(v.step.id, [])]
    last = max((e.at for e in all_evs), default=None)
    started, win_end = ctx.module_windows.get(section.index, (None, None))
    finished = total > 0 and done == total
    rounds, why, n_comments = _rounds(ctx, section.index, (started, last if finished else None), section.title)
    review_n = rounds.review.value if rounds.review.available else 0
    tier = _tier(int(review_n or 0))
    ests = [v.step.est_min for v in views if v.step.est_min is not None]
    est = sum(ests) if ests else None
    actual = elapsed = None
    if started is not None:
        if finished and last is not None:
            actual = _mins(last - started)
        elif status in (Status.RUNNING, Status.WATCH, Status.STALLED, Status.UNKNOWN, Status.STALE) or not finished:
            elapsed = _mins(ctx.now - started)
    what = "%s %d/%d" % (section.title, done, total)
    rounds_line = "审 %s · 外 %s · 修 %s · CI 红%s 绿%s" % (rounds.review.text(), rounds.external.text(), rounds.fixpack.text(),
                                                          rounds.ci_red.text(), rounds.ci_green.text())
    prs = {}
    for e in all_evs:
        if e.kind in ("pr_created", "pr_merged"):
            prs[e.ref["number"]] = e.ref
    if not ctx.ok("gh.prs"):
        pr_text = "PR 未知"
    elif not prs:
        pr_text = "无 PR"
    elif len(prs) == 1:
        p = next(iter(prs.values()))
        pr_text = "PR #%d %s" % (p["number"], "草稿" if (p["_state"] == "OPEN" and p.get("isDraft")) else PR_STATE_TEXT[p["_state"]])
    else:
        merged = sum(1 for p in prs.values() if p["_state"] == "MERGED")
        pr_text = "PR ×%s ✓%s" % (_n(len(prs)), _n(merged))
    comment_text = ("评论 %s" % _n(n_comments)) if ctx.ok("gh.issue") else "评论 未知"
    evidence_line = "%s · %s · 最新 %s" % (pr_text, comment_text, beijing(last) if last else "?")
    needs: list[int] = []
    for v in views:
        for d in v.step.needs:
            dep = ctx.step_by_id.get(d)
            if dep is not None and dep.section != section.index and dep.section not in needs and 0 <= dep.section < n_sections:
                needs.append(dep.section)
    if not needs and section.index > 0:
        needs = [section.index - 1]
    why.insert(0, _why(section.title, LABEL[status], E.CHECKBOX, "步骤聚合", "%d/%d 勾选；步骤状态 %s" % (
        done, total, " ".join("%s=%s" % (v.step.id, LABEL[v.status]) for v in views)), last))
    why.append(_why(section.title, "边框", E.COMMENT_TITLE, "gh.issue", "审核轮数 %s → 档位 %d" % (rounds.review.text(), int(tier)), None, rounds.review.available))
    if started is not None:
        hi = last if (finished and last) else ctx.now
        paused = timedelta(0)
        for p in ctx.pauses:
            lo2, hi2 = max(started, p["start"]), min(hi, p["end"] or ctx.now)
            if hi2 > lo2:
                paused += hi2 - lo2
        if paused:
            why.append(_why(section.title, "跨暂停", E.TASKTABLE_TAG, "任务表引用块", "活动窗口内含暂停 %s 分钟，时长未扣除" % _n(_mins(paused), Grade.REPORTED), None))
    return ModuleView(section=section, status=status, tier=tier, rounds=rounds, done=done, total=total, what=what, rounds_line=rounds_line,
                      evidence_line=evidence_line, actual_min=actual, elapsed_min=elapsed, est_min=est, needs=needs, why=why)


# ---------------------------------------------------------------- 阶段（§7.4）
def _compare_tag(ctx: _Ctx, published: Optional[str], res) -> Val:
    try:
        from . import config as cfg
        fn = getattr(cfg, "compare_tag", None)
        if fn is not None:
            out = fn(published, res)
            if isinstance(out, Val):
                return out
    except NotImplementedError:
        pass
    except Exception:  # noqa: BLE001 — S-4 未合入或异常时用本地比对
        pass
    if not res.ok:
        return Val.unknown(res.key, res.grade)
    got = str(res.value).strip() if res.value is not None else ""
    return Val(bool(published) and got == published, res.grade, res.key, res.fetched_at)


def _stage_result(ctx: _Ctx, key: str):
    """配置阶段的结果键：snapshot.config 记录的 result_key（S-4：`config.<key>`），兼容旧键名。"""
    for row in ctx.cfg.get("stages") or []:
        if row.get("key") == key and row.get("result_key"):
            r = ctx.snap.get(row["result_key"])
            if r.ok or r.error != "未采集":
                return r
    for cand in ("config.%s" % key, "config.stages.%s" % key):
        r = ctx.snap.get(cand)
        if r.ok or r.error != "未采集":
            return r
    return ctx.snap.get("config.%s" % key)


def _stages(ctx: _Ctx) -> tuple[list[StageLevel], list[Why], Optional[str]]:
    why: list[Why] = []
    levels: list[StageLevel] = []
    now = ctx.now
    # 合入主干
    batch_pr = next((p for p in ctx.prs if ctx.snap.branch and p.get("headRefName") == ctx.snap.branch), None)
    merged_at: Optional[datetime] = None
    merge_sha = ""
    if not ctx.ok("gh.prs"):
        merged = Val.unknown("gh.prs")
        why.append(_why("阶段·合入主干", "未知", E.PR_STATE, "gh.prs", ctx.err("gh.prs"), None, False))
    elif batch_pr is not None:
        merged = Val(batch_pr["_state"] == "MERGED", Grade.MEASURED, "gh.prs PR #%d" % batch_pr["number"], batch_pr["_merged"])
        merged_at = batch_pr["_merged"]
        merge_sha = batch_pr.get("mergeCommit") or "" if merged_at else ""
        why.append(_why("阶段·合入主干", "是" if merged.value else "否", E.PR_STATE, "gh.prs", "批次 PR #%d %s%s" % (
            batch_pr["number"], batch_pr["_state"], " → %s" % merge_sha[:7] if merge_sha else ""), batch_pr["_merged"]))
    elif ctx.snap.branch:
        merged = Val(False, Grade.INFERRED, "gh.prs 无批次 PR")
        why.append(_why("阶段·合入主干", "否", E.PR_STATE, "gh.prs", "分支 %s 尚无 PR" % ctx.snap.branch, None))
    elif ctx.prs:
        all_merged = all(p["_state"] == "MERGED" for p in ctx.prs)
        merged_at = max((p["_merged"] for p in ctx.prs if p["_merged"]), default=None)
        last_pr = max((p for p in ctx.prs if p["_merged"]), key=lambda p: p["_merged"], default=None)
        merge_sha = (last_pr.get("mergeCommit") or "") if (all_merged and last_pr) else ""
        merged = Val(all_merged, Grade.INFERRED, "gh.prs 全部 PR", merged_at)
        why.append(_why("阶段·合入主干", "是" if all_merged else "否", E.PR_STATE, "gh.prs", "无批次分支，按 Trace 全部 PR 合入判定：%d/%d MERGED" % (
            sum(1 for p in ctx.prs if p["_state"] == "MERGED"), len(ctx.prs)), merged_at))
    else:
        merged = Val(False, Grade.INFERRED, "gh.prs 无 PR")
        why.append(_why("阶段·合入主干", "否", E.PR_STATE, "gh.prs", "Trace 尚无 PR", None))
    levels.append(StageLevel("merged", STAGE_LABEL["merged"], merged))

    # 已发布：gh.tags 为权威（本地 git.tags 只作参考）；配置了发布工作流时还要 run success 且 headSha 为合并提交或其后代
    workflow = ctx.cfg.get("release_workflow") or getattr(ctx.conf, "release_workflow", None) or ""

    def after_merge(at: Optional[datetime]) -> bool:
        if at is None:
            return False
        if merged_at is not None:
            return at >= merged_at
        return ctx.in_window(at)

    def descendant(sha: str) -> bool:
        if not sha:
            return False
        if merge_sha and _sha_eq(sha, merge_sha):
            return True
        c = ctx._commit_by_prefix(sha)
        return c is not None and after_merge(c["_at"])

    release_run = None
    if workflow and ctx.ok("gh.release_runs"):
        for r in ctx.val("gh.release_runs", []):
            at = parse_ts(r.get("createdAt") or "")
            if at is None or at > now or not after_merge(at):
                continue
            if (r.get("conclusion") or "").lower() == "success" and descendant(r.get("headSha") or ""):
                release_run = r
                break
    matched_tag = None
    if ctx.ok("gh.tags"):
        for t in ctx.gh_tags:
            if descendant(t.get("sha", "")) or (release_run and _sha_eq(t.get("sha", ""), release_run.get("headSha") or "")) or after_merge(t["_at"]):
                matched_tag = t
                break
    local_ref = ", ".join(t["name"] for t in ctx.tags if after_merge(t["_at"])) or "无"
    published_tag = matched_tag["name"] if matched_tag else None
    if not ctx.ok("gh.tags"):
        published = Val.unknown("gh.tags")
        why.append(_why("阶段·已发布", "未知", E.TAG_REF, "gh.tags", "%s（本地 git.tags 参考：%s）" % (ctx.err("gh.tags"), local_ref if ctx.ok("git.tags") else "不可得"), None, False))
    elif workflow:
        if not ctx.ok("gh.release_runs"):
            published = Val.unknown("gh.release_runs")
            why.append(_why("阶段·已发布", "未知", E.WORKFLOW_RUN, "gh.release_runs", ctx.err("gh.release_runs"), None, False))
        else:
            ok = release_run is not None and matched_tag is not None
            at = parse_ts(release_run.get("createdAt") or "") if release_run else None
            published = Val(ok, Grade.MEASURED, "gh.release_runs ＋ gh.tags", at)
            why.append(_why("阶段·已发布", "是" if ok else "否", E.WORKFLOW_RUN, "gh.release_runs ＋ gh.tags", "发布 run %s；tag %s（本地参考：%s）" % (
                "success %s %s" % ((release_run.get("headSha") or "")[:7], beijing(at)) if release_run else "无合并后的成功 run",
                "%s → %s" % (matched_tag["name"], matched_tag.get("sha", "")[:7]) if matched_tag else "无合并后的 tag", local_ref), at))
    else:
        published = Val(matched_tag is not None, Grade.INFERRED, "gh.tags", matched_tag["_at"] if matched_tag else None)
        why.append(_why("阶段·已发布", "是" if matched_tag else "否", E.TAG_REF, "gh.tags", "未配置发布工作流，按合并后 tag 判定：%s（本地参考：%s）" % (
            "%s → %s" % (matched_tag["name"], matched_tag.get("sha", "")[:7]) if matched_tag else "无 tag", local_ref), published.at))
    levels.append(StageLevel("published", STAGE_LABEL["published"], published))

    # 预发 / 生产
    stage_keys = {s.get("key") for s in (ctx.cfg.get("stages") or [])}
    conf_stages = getattr(ctx.conf, "stages", None) or {}
    for key in ("staging", "production"):
        configured = key in stage_keys or (isinstance(conf_stages, dict) and key in conf_stages)
        if not configured:
            levels.append(StageLevel(key, STAGE_LABEL[key], Val.unknown("config.%s" % key), configured=False))
            why.append(_why("阶段·" + STAGE_LABEL[key], "未配置", E.CONFIG_COMMAND, "config.%s" % key, "证据源配置未声明", None, False))
            continue
        res = _stage_result(ctx, key)
        val = _compare_tag(ctx, published_tag, res)
        levels.append(StageLevel(key, STAGE_LABEL[key], val))
        why.append(_why("阶段·" + STAGE_LABEL[key], ("是" if val.value else "否") if val.available else "未知", E.IMAGE_TAG, res.key,
                        ("取得 %s vs 已发布 %s" % (str(res.value).strip()[:40], published_tag or "无")) if res.ok else res.error, res.fetched_at, val.available))
    # 收口
    if not ctx.ok("gh.issue"):
        closed = Val.unknown("gh.issue")
        why.append(_why("阶段·收口", "未知", E.ISSUE_STATE, "gh.issue", ctx.err("gh.issue"), None, False))
    else:
        closed = Val(ctx.issue_closed_at is not None, Grade.MEASURED, "gh.issue", ctx.issue_closed_at)
        why.append(_why("阶段·收口", "是" if closed.value else "否", E.ISSUE_STATE, "gh.issue", "Issue #%s %s" % (ctx.snap.trace_no, "CLOSED" if closed.value else "OPEN"), ctx.issue_closed_at))
    levels.append(StageLevel("closed", STAGE_LABEL["closed"], closed))
    return levels, why, published_tag


# ---------------------------------------------------------------- 头六项（§7.5）
def _header(ctx: _Ctx, views: list[StepView], modules: list[ModuleView], levels: list[StageLevel], why: list[Why]) -> Header:
    now = ctx.now
    n_checked = sum(1 for v in views if ctx.checked_map.get(v.step.id, False))
    total = len(views)
    lv = {s.key: s for s in levels}

    def is_true(key: str) -> bool:
        s = lv.get(key)
        return bool(s and s.value.available and s.value.value)

    short = re.sub(r"^\d+-", "", ctx.snap.trace_dir.split("/")[-1])
    title = "Trace #%s %s" % (ctx.snap.trace_no or "?", short) + (" · %s" % ctx.snap.branch if ctx.snap.branch else "")
    checked_text = "%d/%s 勾选" % (n_checked, _n(total))
    # 阶段
    current = next((m for m in modules if m.done < m.total), None)
    if is_true("closed"):
        stage = "已收口（Issue 关闭 %s）· %s" % (beijing(lv["closed"].value.at), checked_text)
    elif is_true("production"):
        stage = "已上生产 · %s" % checked_text
    elif is_true("staging"):
        stage = "预发已升级 · %s" % checked_text
    elif is_true("published"):
        stage = "已发布 · %s" % checked_text
    elif is_true("merged"):
        stage = "已合入主干 · %s" % checked_text
    else:
        stage = "执行中 · %s（%s）" % (current.section.title if current else "全部勾选", checked_text)
    # 下一步 = 第一个未勾选 Step（编号＋标题＋状态）＋ worktree 数
    wts = [w for w in ctx.worktrees if not w.get("main")]
    wt_text = ("worktree %s" % _n(len(wts))) if ctx.ok("git.worktrees") else "worktree 未知"
    if is_true("closed"):
        nxt = "无（Trace 已关闭）"
    elif is_true("production"):
        nxt = "观察与收口 · " + wt_text
    else:
        first = next((v for v in views if not ctx.checked_map.get(v.step.id, False)), None)
        nxt = ("%s %s（%s）" % (first.step.id, first.step.title[:18], LABEL[first.status]) if first else "无未勾选 Step") + " · " + wt_text
    # 阻塞：只放当前阻塞
    block_parts: list[str] = []
    for v in views:
        if v.status == Status.STALLED:
            block_parts.append("%s %s 分钟无证据" % (v.step.id, _n(_mins(now - v.last_evidence) if v.last_evidence else 0)))
    completed = [r for r in ctx.runs if (r.get("status") or "").lower() == "completed" or r.get("conclusion")]
    if completed:
        latest = completed[-1]
        if (latest.get("conclusion") or "").lower() in RED:
            block_parts.append("CI 红：%s %s" % (latest.get("workflowName") or latest.get("name") or "run", beijing(latest["_at"])))
            why.append(_why("CI", "红", E.CI_CONCLUSION, "gh.runs", "最近完成的 run %s %s（%s）" % (
                latest.get("workflowName") or latest.get("name"), latest.get("conclusion"), (latest.get("headSha") or "")[:7]), latest["_at"]))
    stale_ids = [v.step.id for v in views if v.status == Status.STALE]
    if stale_ids:
        block_parts.append("审核结论失效 %s" % "/".join(stale_ids[:3]))
    unknown_stages = [s.label for s in levels if s.configured and not s.value.available]
    if unknown_stages:
        block_parts.append("阶段未知：%s" % " / ".join(unknown_stages))
    pattern = ctx.cfg.get("window_pattern") or getattr(ctx.conf, "window_pattern", None) or ""
    window_alive: Optional[bool] = None
    alive: list[str] = []
    if ctx.cfg.get("tmux_configured") and pattern and ctx.ok("tmux.windows"):
        try:
            alive = [w for w in ctx.val("tmux.windows", []) if re.search(pattern, w)]
        except re.error:
            alive = []
        window_alive = bool(alive)
        why.append(_why("编排窗口", "存活" if alive else "不在", E.TMUX_WINDOW, "tmux.windows", "%s（模式 %s）" % ("、".join(alive[:3]) if alive else "无匹配窗口", pattern), None))
        if not alive:
            block_parts.append("编排窗口不在")
    for p in ctx.pauses:
        if p["end"] is None:
            block_parts.append("暂停中 自 %s（报）" % beijing(p["start"], "%m-%d %H:%M"))
            why.append(_why("暂停", "进行中", E.TASKTABLE_TAG, p["source"], "%s → 无恢复证据；%s" % (beijing(p["start"], "%m-%d %H:%M"), p["line"][:60]), p["start"]))
        else:
            why.append(_why("暂停", "%s 分钟" % _n(_mins(p["end"] - p["start"]), Grade.REPORTED), E.TASKTABLE_TAG, p["source"],
                            "%s → %s（恢复＝其后首个证据）；%s" % (beijing(p["start"], "%m-%d %H:%M:%S"), beijing(p["end"], "%m-%d %H:%M:%S"), p["line"][:60]), p["end"]))
    block = " · ".join(block_parts) if block_parts else "无"
    # 预算
    budget: list[tuple[str, Val, Optional[int]]] = []
    for b in ctx.cfg.get("budgets") or []:
        res = ctx.snap.get(b.get("result_key") or ("config.%s" % b.get("key")))
        val = Val(res.value, res.grade, res.key, res.fetched_at) if res.ok else Val.unknown(res.key, res.grade)
        budget.append((b.get("label") or b.get("key") or "", val, b.get("cap")))
    if not budget:
        budget.append(("PR", Val(len(ctx.prs), Grade.MEASURED, "gh.prs") if ctx.ok("gh.prs") else Val.unknown("gh.prs"), None))
        budget.append(("CI 次数", Val(len(ctx.runs), Grade.MEASURED, "gh.runs") if ctx.ok("gh.runs") else Val.unknown("gh.runs"), None))
    # 存疑：自述未证 / 合同 PR / 共用 PR / PR 自合计数 / 历史最大空档
    doubt_parts: list[str] = []
    doneq = [v.step.id for v in views if v.status == Status.DONEQ]
    if doneq:
        doubt_parts.append("自述未证 %s（%s）" % (_n(len(doneq)), "/".join(doneq[:4]) + ("…" if len(doneq) > 4 else "")))
    if ctx.contract_pr is not None:
        p = ctx.contract_pr
        flags = []
        if p["_state"] == "MERGED" and _pr_self_merged(p):
            flags.append("自合")
        if p["_state"] == "MERGED" and not _pr_approved(p):
            flags.append("零批准")
        if flags:
            doubt_parts.append("合同 PR #%d %s" % (p["number"], " / ".join(flags)))
        why.append(_why("合同 PR #%d" % p["number"], "存疑" if flags else "正常", E.PR_MERGED_BY, "git.contract ＋ gh.prs",
                        "首次加入 合同.md 的提交 %s；%s；mergedBy=%s author=%s；APPROVED review %d" % (
                            (ctx.contract or {}).get("sha", "")[:7], p["_state"], p.get("mergedBy") or "-", p.get("author") or "-",
                            sum(1 for r in p.get("reviews") or [] if (r.get("state") or "").upper() == "APPROVED")), p["_merged"] or p["_created"]))
    elif ctx.contract and ctx.ok("gh.prs"):
        why.append(_why("合同 PR", "未找到", E.PR_MERGED_BY, "git.contract", "合同.md 首次提交 %s 未对应任何 PR" % ctx.contract.get("sha", "")[:7], parse_ts(ctx.contract.get("at") or "")))
    shared = []
    for p in ctx.prs:
        owners = sorted(p["_steps"])
        if len(owners) >= 2:
            shared.append("#%d（%s）" % (p["number"], "/".join(owners[:3])))
    if shared:
        doubt_parts.append("共用 PR %s" % " ".join(shared[:2]) + ("…" if len(shared) > 2 else ""))
    if ctx.ok("gh.prs"):
        merged_prs = [p for p in ctx.prs if p["_state"] == "MERGED"]
        if merged_prs:
            n_self = sum(1 for p in merged_prs if _pr_self_merged(p))
            n_appr = sum(1 for p in merged_prs if _pr_approved(p))
            tally = "PR 自合 %d/%s" % (n_self, _n(len(merged_prs)))
            tally += " · 零批准" if n_appr == 0 else " · 批准 %s" % _n(n_appr)
            doubt_parts.append(tally)
            why.append(_why("PR 合并方式", tally, E.PR_MERGED_BY, "gh.prs", "自合 %s" % " ".join("#%d" % p["number"] for p in merged_prs if _pr_self_merged(p)), None))
    else:
        doubt_parts.append("PR 存疑未知（gh）")
    evs = ctx.step_work_events
    if len(evs) >= 2:
        i = max(range(len(evs) - 1), key=lambda k: evs[k + 1].at - evs[k].at)
        gap, (a, b) = evs[i + 1].at - evs[i].at, (evs[i], evs[i + 1])
        if gap >= timedelta(minutes=GAP_MIN):
            paused = timedelta(0)
            for p in ctx.pauses:
                lo, hi = max(a.at, p["start"]), min(b.at, p["end"] or now)
                if hi > lo:
                    paused += hi - lo
            text = "最大空档 %s 分钟 %s→%s" % (_n(_mins(gap), Grade.INFERRED), beijing(a.at), beijing(b.at))
            if paused:
                text += "（其中暂停 %s 分钟）" % _n(_mins(paused), Grade.REPORTED)
            doubt_parts.append(text)
            why.append(_why("空档", "%s 分钟" % _n(_mins(gap), Grade.INFERRED), b.etype, "%s → %s" % (a.source, b.source),
                            "%s %s → %s %s%s" % (a.label, beijing(a.at, "%m-%d %H:%M:%S"), b.label, beijing(b.at, "%m-%d %H:%M:%S"),
                                                 "；归因暂停 %s 分钟" % _n(_mins(paused), Grade.REPORTED) if paused else ""), b.at))
    doubt = " · ".join(doubt_parts) if doubt_parts else "无"
    # 最后外部证据
    external = [e for e in ctx.events if e.kind != "checkbox"]
    if external:
        last = external[-1]
        who = "/".join(sorted(last.steps)[:2]) if last.steps else "Trace"
        evidence = "%s 分钟前 · %s（%s）· %s" % (_n(_mins(now - last.at)), last.label, who, beijing(last.at, "%m-%d %H:%M"))
    elif not all(ctx.ok(k) for k in CORE_KEYS):
        evidence = "未知（证据不可得）"
    else:
        evidence = "无"
    # 附注与告警
    warnings = list(ctx.warnings)
    if window_alive is not True:
        warnings.append(WINDOW_NOTE)
    if ctx.table.unparsed:
        warnings.append("任务表未解析 %s 行" % _n(len(ctx.table.unparsed)))
    if ctx.table.overlong:
        warnings.append("任务表超限 %s 行" % _n(len(ctx.table.overlong)))
    for key in ("git.log", "git.tasktable_history", "git.worktrees", "gh.prs", "gh.issue", "gh.runs", "gh.tags"):
        r = ctx.snap.get(key)
        if not r.ok:
            warnings.append("%s 不可得：%s" % (key, r.error[:60]))
    return Header(title=title, stage=stage, block=block, nxt=nxt, budget=budget, doubt=doubt, evidence=evidence, stages=levels, warnings=warnings)


# ---------------------------------------------------------------- 入口
def infer(snapshot: Snapshot, conf) -> Board:
    ctx = _Ctx(snapshot, conf)
    checked_map = {s.id: ctx.effective_checked(s) for s in ctx.steps}
    ctx.checked_map = checked_map
    views: list[StepView] = [_step_view(ctx, s, checked_map) for s in ctx.steps]
    view_by_section: dict[int, list[StepView]] = {}
    for v in views:
        view_by_section.setdefault(v.step.section, []).append(v)
    n_sections = len(ctx.table.sections)
    ctx.assign_comments({sec.index: _module_window(ctx, view_by_section.get(sec.index, [])) for sec in ctx.table.sections})
    modules = [_module_view(ctx, sec, view_by_section.get(sec.index, []), n_sections) for sec in ctx.table.sections]
    levels, stage_why, _tag = _stages(ctx)
    header_why: list[Why] = []
    header = _header(ctx, views, modules, levels, header_why)
    trace_rounds, trace_why, _n_comments = _rounds(ctx, None, (None, None), "Trace")
    if any(v.available and v.value for v in (trace_rounds.review, trace_rounds.external, trace_rounds.fixpack)):
        header.stage += " · Trace 级 审 %s 外 %s 修 %s" % (trace_rounds.review.text(), trace_rounds.external.text(), trace_rounds.fixpack.text())
    board = Board(header=header, steps=views, modules=modules, generated_at=ctx.now, why=stage_why + header_why + trace_why,
                  unparsed=list(ctx.table.unparsed))
    board.validate()
    return board
