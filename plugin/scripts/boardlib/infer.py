# -*- coding: utf-8 -*-
"""状态推断（接口约定 §7）。归属：S-2 / F-1。只判断、不取数据；每个判定都留 Why；不可得显示「未知」不回落。

    infer(snapshot: Snapshot, conf) -> Board
        - 步骤九色＋未知（§7.1）、模块聚合与三行文案（§7.2）、轮数与边框档位、时长（§7.3）、
          五级阶段（§7.4）、头六项（§7.5）、来源角标、Why 证据链（§7.6）；末尾 board.validate()

规则要点（账本 F-1 条目）：
- 「有证据」归属：提交信息 / 分支名 / worktree 目录名 / PR 标题正文 / 评论首行含 Step ID（词边界）；PR 归属 指针 > 标题 > 正文。
- 独立制品（`done`）只认：指针指向或归属的 PR MERGED、触及 Trace 目录外文件的提交、任务表指针指向的评论（A-2 / R1-2）；
  只改 `docs/traces/<n>/` 的提交与首行提及 Step ID 的评论只算活动证据（角标推）。
- 候选失效（K-2 / K-3 / R1-7）：`t:review` / `t:gate` 且指针含 SHA 的步骤，无论是否勾选，SHA ≠ 分支 HEAD → `stale`；
  HEAD 以 `gh.prs` 批次 PR 远端 head OID 为准，本地 `git.branches` 备用；都不可得 → `unknown`。
- 依赖（R1-6）：依赖不存在 / 成环 → `unknown`＋告警；依赖满足＝依赖状态 ∈ {完成, 自述未证}（自述未证视为满足＝现场裁定）。
- 轮数（R1-3 r5 / A-6）：评论首行**全文**匹配（首行即标题），关键词前 6 字符内有否定词（不是 / 非 / 未 / 无 / 取消 / 引用 / 不算）不计；「修」只计有结果的修复包评论；
  归属 Step ID（实）→ 活动窗口回落（推，重叠取最晚开始）→ Trace 级。CI run 唯一归属（R1-5）：headSha 提交信息 → PR 分支 → 窗口 → Trace 级。
- 五级阶段（R1-11…15）：合入主干只认唯一识别的批次 PR（无批次分支＝不适用）；已发布须有已证实的合并点，祖先关系优先 `gh.compare`；
  已发布未知 → 预发 / 生产未知；合入 / 收口不可得 → 阶段行「未知」。
- Why 来源列只写证据键（`config.*` 只写键与失败类别，绝不写 stderr，A-1）；Board.why 只放 Trace 级行。
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
SHA_BOUND_TYPES = (StepType.REVIEW, StepType.GATE)
KEY_ETYPE = {
    "git.log": E.COMMIT_TIME, "gh.prs": E.PR_STATE, "gh.issue": E.COMMENT_TITLE, "gh.runs": E.CI_CONCLUSION,
    "git.worktrees": E.WORKTREE, "git.tasktable_history": E.CHECKBOX, "git.branches": E.SHA_EQUAL, "gh.tags": E.TAG_REF,
    "gh.release_runs": E.WORKFLOW_RUN, "gh.compare": E.TAG_REF, "tmux.windows": E.TMUX_WINDOW, "git.contract": E.PR_MERGED_BY,
}
FAIL_CATEGORY_RE = re.compile(r"^(超时|退出码 \d+|解析失败|无输出|命令不可用|无法启动|整轮超时|已取消|夹具未记录|未采集|未配置|仓库 slug 未知)")

# 轮数正则（https://github.com/Moshuiwang/lingxi/issues/578 已定；只看评论首行全文——首行即标题，本就是结构化位置；
# R1-3 r5 裁定：不锚定行首，只排除否定形态：关键词前 6 个字符内出现「不是 / 非 / 未 / 无 / 取消 / 引用 / 不算」不计）
REVIEW_RE = re.compile(r"审核[①②③④⑤]|审[①②③④⑤]|审核\s*[1-5]\s*轮|独立审核.*?结论|定向复核.*?结论|复核[①②③④⑤]")
EXTERNAL_RE = re.compile(r"外审|codex|agy", re.IGNORECASE)
EXTERNAL_RESULT_RE = re.compile(r"结论|账本")
FIXPACK_RE = re.compile(r"修复包")
FIXPACK_RESULT_RE = re.compile(r"合入|完成|已落|结论")
NEGATION_RE = re.compile(r"不是|非|未|无|取消|引用|不算")
NEGATION_SPAN = 6
PAUSE_RE = re.compile(r"暂停")
QUOTE_TIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\D{0,3}(\d{1,2}):(\d)([0-9xX])\s*(UTC|北京)?")
PR_SUFFIX_RE = re.compile(r"\(#(\d+)\)\s*$|Merge pull request #(\d+)")
STAGE_LABEL = {"merged": "合入主干", "published": "已发布", "staging": "预发已升级", "production": "已上生产", "closed": "收口"}
PR_STATE_TEXT = {"MERGED": "✓合入", "OPEN": "打开", "CLOSED": "关闭"}
WINDOW_NOTE = "窗口状态未知，需元守护核"
LABEL = registry.STATUS_LABEL
RULE = registry.STATUS_RULE
FIRST_LINE_SHOW = 200


@dataclass
class Ev:
    """一条证据事件（内部用）。kind：commit / commit_docs / pr_created / pr_merged / comment / comment_mention / run / worktree / checkbox。"""

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


def _fail_category(error: str) -> str:
    """A-1：失败只留类别（超时 / 退出码 N / 解析失败 …），绝不带 stderr 原文。"""
    m = FAIL_CATEGORY_RE.match(error or "")
    return m.group(1) if m else "失败"


def _build_attr_re(ids) -> Optional["re.Pattern[str]"]:
    ids = sorted(set(i for i in ids if i), key=len, reverse=True)
    if not ids:
        return None
    return re.compile(r"(?<![0-9A-Za-z])(%s)(?![0-9A-Za-z]|-[0-9A-Za-z])" % "|".join(re.escape(i) for i in ids))


def _why(subject: str, status: str, etype: E, source: str, value: str, at: Optional[datetime] = None, available: bool = True) -> Why:
    return Why(subject, status, etype, source, value, at, available)


def _sha_eq(a: str, b: str) -> bool:
    return bool(a) and bool(b) and (a.startswith(b) or b.startswith(a))


def _strip_heading(text: str) -> str:
    return (text or "").lstrip("#*> ").strip()


class _Ctx:
    """把快照整理成事件表；所有判定函数只读这里。"""

    def __init__(self, snap: Snapshot, conf):
        self.snap = snap
        self.conf = conf
        self.now = utc(snap.now)
        self.cfg = dict(snap.config or {})
        self.table = snap.tasktable
        self.table_ok = bool(getattr(self.table, "available", True))
        self.steps: list[Step] = list(self.table.steps) if self.table_ok else []
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

    def category(self, key: str) -> str:
        return _fail_category(self.err(key))

    def attr(self, text: str) -> set:
        if not text or self.attr_re is None:
            return set()
        return set(self.attr_re.findall(text))

    def _load(self) -> None:
        now = self.now
        raw_log = self.val("git.log", None)
        if isinstance(raw_log, dict):
            commits_raw = raw_log.get("commits") or []
            self.log_mode = raw_log.get("mode") or "branch"
            self.log_truncated = bool(raw_log.get("truncated"))
        else:
            commits_raw = raw_log if isinstance(raw_log, list) else []
            self.log_mode, self.log_truncated = "branch", False
        self.commit_grade = Grade.MEASURED if self.log_mode == "branch" else Grade.INFERRED
        self.commits: list[dict] = []
        for c in commits_raw:
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
            if at is None or h.get("error"):
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
        # R1-9：回放时刻早于采集时刻且任务表历史不可得 → 复选框真值未知
        fetched = [r.fetched_at for r in self.snap.results.values() if r.fetched_at]
        recorded_at = max(fetched) if fetched else None
        self.checkbox_unknown = bool(recorded_at and recorded_at - now > timedelta(seconds=60) and not self.ok("git.tasktable_history"))
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
        # 批次 PR（R1-11：只认唯一识别；多 PR 冲突 → None ＋ 记录冲突）
        self.batch_prs = [p for p in self.prs if self.snap.branch and p.get("headRefName") == self.snap.branch]
        self.batch_pr = self.batch_prs[0] if len(self.batch_prs) == 1 else None
        self.runs: list[dict] = []
        heads = {p.get("headRefName") for p in self.prs if p.get("headRefName")}
        for r in self.val("gh.runs", []):
            created = parse_ts(r.get("createdAt") or "")
            done_at = parse_ts(r.get("updatedAt") or "") or created  # R1-19：新鲜度用结论时刻
            if created is None or not self.in_window(created):
                continue
            if done_at is None or done_at > now:
                done_at = created
            row = dict(r)
            row["_created"] = created
            row["_at"] = done_at
            steps: set = set()
            pr_steps: set = set()
            for p in self.prs:
                if r.get("headBranch") and r.get("headBranch") == p.get("headRefName"):
                    pr_steps |= p["_steps"]
            c = self._commit_by_prefix(r.get("headSha") or "")
            commit_steps = self.attr(c.get("subject", "")) if c is not None else set()
            steps = commit_steps | pr_steps
            relevant = bool(self.snap.branch) or (r.get("headBranch") in heads) or (c is not None)
            if not relevant:
                continue
            row["_steps"], row["_commit_steps"], row["_pr_steps"] = steps, commit_steps, pr_steps
            row["_module"] = None
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
        compare = self.val("gh.compare", {}) or {}
        self.compare_base = compare.get("base") or ""
        self.compare_results: dict[str, str] = dict(compare.get("results") or {})
        self.branches: list[dict] = list(self.val("git.branches", []))
        self.worktrees: list[dict] = []
        for w in self.val("git.worktrees", []):
            row = dict(w)
            row["_at"] = parse_ts(w.get("last_at") or "")
            self.worktrees.append(row)
        # 候选 HEAD（R1-7）：批次 PR 远端 head OID 优先，本地分支备用
        self.tip, self.tip_source = "", ""
        if self.batch_pr is not None and self.batch_pr.get("head_oid"):
            self.tip, self.tip_source = self.batch_pr["head_oid"], "gh.prs"
        elif self.snap.branch and self.ok("git.branches"):
            for b in self.branches:
                if b.get("name") in (self.snap.branch, "origin/" + self.snap.branch):
                    self.tip, self.tip_source = b.get("sha", ""), "git.branches"
                    if b.get("name") == self.snap.branch:
                        break
        self.branch_tip = self.tip
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
                    docs = bool(c.get("docs_only"))
                    ev.append(Ev(c["_at"], "commit_docs" if docs else "commit", E.COMMIT_TIME, "git.log", "commit %s" % c["sha"][:7], steps,
                                 Grade.INFERRED if docs else self.commit_grade, ref=c))
        for p in self.prs:
            n = p.get("number")
            if p["_created"] and self.in_window(p["_created"]):
                ev.append(Ev(p["_created"], "pr_created", E.PR_STATE, "gh.prs", "PR #%s" % n, set(p["_steps"]), ref=p))
            if p["_merged"] and self.in_window(p["_merged"]):
                ev.append(Ev(p["_merged"], "pr_merged", E.PR_STATE, "gh.prs", "PR #%s 合入" % n, set(p["_steps"]), ref=p))
        for c in self.comments:
            if not self.in_window(c["_at"]):
                continue
            pointed = {s.id for s in self.steps if c.get("id") in s.comments}
            mentioned = self.attr(c.get("first_line", "")) - pointed
            c["_steps"] = pointed | mentioned
            if pointed:
                ev.append(Ev(c["_at"], "comment", E.COMMENT_TITLE, "gh.issue", "评论 %s" % c.get("id"), pointed, ref=c))
            if mentioned:
                ev.append(Ev(c["_at"], "comment_mention", E.COMMENT_TITLE, "gh.issue", "评论 %s 提及" % c.get("id"), mentioned, Grade.INFERRED, ref=c))
            if not pointed and not mentioned:
                ev.append(Ev(c["_at"], "comment_mention", E.COMMENT_TITLE, "gh.issue", "评论 %s" % c.get("id"), set(), Grade.INFERRED, ref=c))
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
                src = "git.tasktable_history"
            else:
                m = QUOTE_TIME_RE.search(q)
                if m:
                    minute = int(m.group(3)) * 10 + (0 if m.group(4).lower() == "x" else int(m.group(4)))
                    start = parse_ts("%sT%02d:%02d:00+00:00" % (m.group(1), int(m.group(2)), minute))
                    if start and m.group(5) == "北京":
                        start = start - timedelta(hours=8)
                    src, grade = "tasktable.quotes", Grade.REPORTED
            if start is None or start > self.now:
                continue
            end = next((e.at for e in self.step_work_events if e.at > start), None)
            self.pauses.append({"start": start, "end": end, "line": q, "source": src, "grade": grade})
        self.pauses.sort(key=lambda p: p["start"])

    # ---------- 评论 / CI run 归属（§7.2：Step ID → 时间窗回落 → Trace 级；R1-5 run 唯一归属） ----------
    def assign(self, windows: dict[int, tuple[Optional[datetime], Optional[datetime]]]) -> None:
        self.module_windows = windows

        def by_window(at: datetime) -> Optional[int]:
            cands = [(start, idx) for idx, (start, end) in windows.items() if start is not None and start <= at <= (end or self.now)]
            return max(cands)[1] if cands else None

        for c in self.comments:
            if not self.in_window(c["_at"]):
                continue
            explicit = {self.step_by_id[s].section for s in (c.get("_steps") or set()) if s in self.step_by_id}
            if explicit:
                c["_modules"], c["_grade"], c["_window"] = explicit, Grade.MEASURED, None
                continue
            idx = by_window(c["_at"])
            if idx is not None:
                c["_modules"], c["_grade"], c["_window"] = {idx}, Grade.INFERRED, windows[idx]
        for r in self.runs:
            mods = {self.step_by_id[s].section for s in r["_commit_steps"] if s in self.step_by_id}
            if not mods:
                mods = {self.step_by_id[s].section for s in r["_pr_steps"] if s in self.step_by_id}
            if mods:
                r["_module"] = max(mods, key=lambda i: (windows.get(i, (None, None))[0] or self.now, i))
                r["_module_grade"] = Grade.MEASURED
                continue
            idx = by_window(r["_at"])
            r["_module"] = idx
            r["_module_grade"] = Grade.INFERRED


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


def _missing_rows(ctx: _Ctx, sid: str, status: Status, keys: list[str]) -> list[Why]:
    """R1-23：每个不可得的实际依赖各一行，EvidenceType 按键。"""
    return [_why(sid, LABEL[status], KEY_ETYPE.get(k, E.CONFIG_COMMAND), k, "%s 不可得：%s" % (k, ctx.category(k)), None, False) for k in keys]


def _sha_bound(step: Step) -> bool:
    return step.type in SHA_BOUND_TYPES and bool(step.shas)


def _stale_state(ctx: _Ctx, step: Step) -> Optional[bool]:
    """候选 SHA 是否已变：True / False；HEAD 不可得 → None。"""
    if not ctx.tip:
        return None
    return not any(_sha_eq(ctx.tip, x) for x in step.shas)


def _step_view(ctx: _Ctx, step: Step, checked_map: dict[str, bool], dep_status: dict[str, Status], dep_problems: dict[str, str]) -> StepView:
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
    etype, source, detail, at, available = E.CHECKBOX, "任务表", "", None, True
    extra: list[Why] = []

    if step.checked and not checked:
        why.append(_why(step.id, LABEL[Status.TODO], E.CHECKBOX, "git.tasktable_history", "勾选提交晚于 --now，按未勾选处理", ctx.first_checked[step.id][0]))

    stale = _stale_state(ctx, step) if _sha_bound(step) else False
    if ctx.checkbox_unknown and (checked or not work):
        status = Status.UNKNOWN
        etype, source, available = E.CHECKBOX, "git.tasktable_history", False
        detail = "回放时刻早于采集时刻且任务表历史不可得，复选框真值未知"
    elif _sha_bound(step) and stale is None:
        status = Status.UNKNOWN
        etype, source, available = E.SHA_EQUAL, "gh.prs", False
        detail = "候选 %s 需比对分支 HEAD，但远端 head（gh.prs）与本地分支（git.branches）都不可得" % step.shas[-1][:7]
        extra = _missing_rows(ctx, step.id, status, [k for k in ("gh.prs", "git.branches") if not ctx.ok(k)])
    elif stale:
        status = Status.STALE
        etype, source = E.SHA_EQUAL, ctx.tip_source
        detail = "候选 %s ≠ 分支 HEAD %s（%s）%s" % (step.shas[-1][:7], ctx.tip[:7], ctx.tip_source, "；已勾选但候选已变，结论失效" if checked else "")
    elif checked:
        if artifacts:
            status = Status.DONE
            a = artifacts[-1]
            etype, source, at = a.etype, a.source, a.at
            detail = "制品 %s" % " / ".join(sorted({x.label for x in artifacts})[:4])
        elif missing_core:
            status = Status.UNKNOWN
            etype, source, available = KEY_ETYPE[missing_core[0]], missing_core[0], False
            detail = "已勾选，但制品证据不可得：%s" % " / ".join(missing_core)
            extra = _missing_rows(ctx, step.id, status, missing_core)
        else:
            status = Status.DONEQ
            docs = [e for e in evs if e.kind in ("commit_docs", "comment_mention")]
            detail = "无独立制品（指针 PR / 触及 Trace 目录外的提交 / 指针评论均未命中%s）" % ("；只有活动证据 " + "、".join(e.label for e in docs[:3]) if docs else "")
    elif step.type == StepType.HUMAN:
        status = Status.HUMAN
        etype, source, detail = E.TASKTABLE_TAG, "任务表", "t:human 待人类"
    elif work:
        age = _mins(now - last_work)
        last = work[-1]
        etype, source, at = last.etype, last.source, last.at
        if age <= RUNNING_MIN:
            status = Status.RUNNING
            detail = "%s 分钟前有证据 %s" % (_n(age), last.label)
        elif missing_live:
            status = Status.UNKNOWN
            etype, source, available = KEY_ETYPE[missing_live[0]], missing_live[0], False
            detail = "最近证据 %s 分钟前，但 %s 不可得，无法排除更新证据" % (_n(age), " / ".join(missing_live))
            extra = _missing_rows(ctx, step.id, status, missing_live)
        elif age <= WATCH_MIN:
            status = Status.WATCH
            detail = "%s 分钟无新证据（最近 %s）" % (_n(age), last.label)
        else:
            status = Status.STALLED
            detail = "%s 分钟无新证据（最近 %s）" % (_n(age), last.label)
    elif missing_live:
        status = Status.UNKNOWN
        etype, source, available = KEY_ETYPE[missing_live[0]], missing_live[0], False
        detail = "无证据，且 %s 不可得" % " / ".join(missing_live)
        extra = _missing_rows(ctx, step.id, status, missing_live)
    elif step.id in dep_problems:
        status = Status.UNKNOWN
        etype, source, available = E.CHECKBOX, "任务表", False
        detail = dep_problems[step.id]
    else:
        deps = list(step.needs)
        unmet = [d for d in deps if dep_status.get(d) not in (Status.DONE, Status.DONEQ)]
        if not unmet:
            status = Status.READY
            detail = "无证据，依赖状态全部 ∈ {完成, 自述未证}（%s）" % (", ".join(deps) if deps else "无依赖")
        else:
            status = Status.TODO
            detail = "无证据，依赖未完成：%s" % ", ".join("%s=%s" % (d, LABEL[dep_status[d]] if d in dep_status else "?") for d in unmet)
    why.insert(0, _why(step.id, LABEL[status], etype, source, "%s｜%s" % (RULE[status], detail), at, available))
    why.extend(extra)

    started = min((e.at for e in work), default=None)
    last_any = max((e.at for e in evs), default=None)
    actual_min = elapsed_min = None
    if started is not None:
        if checked and last_any is not None:
            actual_min = _mins(last_any - started)
        elif not checked and status in (Status.RUNNING, Status.WATCH, Status.STALLED, Status.UNKNOWN, Status.STALE):
            elapsed_min = _mins(now - started)
    if evs:
        why.append(_why(step.id, "证据", evs[-1].etype, evs[-1].source,
                        "%s 条：%s" % (_n(len(evs)), "、".join(e.label for e in evs[:6]) + ("…" if len(evs) > 6 else "")), evs[-1].at))
    if len(evs) >= 2:
        i = max(range(len(evs) - 1), key=lambda k: evs[k + 1].at - evs[k].at)
        gap, (a, b) = evs[i + 1].at - evs[i].at, (evs[i], evs[i + 1])
        if gap >= timedelta(minutes=WAIT_MIN):
            why.append(_why(step.id, "等待", b.etype, b.source,
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
        return "候选 %s → 已变 %s" % (step.shas[-1][:6], ctx.tip[:6]), Status.STALE, True
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
    real_commits = [e for e in evs if e.kind == "commit"]
    docs_commits = [e for e in evs if e.kind == "commit_docs"]
    pointer_comments = [e for e in evs if e.kind == "comment"]
    mentions = [e for e in evs if e.kind == "comment_mention"]
    wts = [e for e in evs if e.kind == "worktree"]
    runs = [e for e in evs if e.kind == "run"]
    if real_commits:
        c = real_commits[-1]
        if checked:
            return "commit %s ✓" % c.ref["sha"][:7], chip_status, rework
        return "commit %s · %dm 前" % (c.ref["sha"][:7], _mins(now - c.at)), chip_status, rework
    if pointer_comments:
        return "评论 ✓ %s" % beijing(pointer_comments[-1].at), chip_status, rework
    if docs_commits:
        c = docs_commits[-1]
        if checked:
            return "无制品 · 勾选提交 %s" % c.ref["sha"][:7], Status.DONEQ, rework
        return "docs %s · %dm 前" % (c.ref["sha"][:7], _mins(now - c.at)), chip_status, rework
    if mentions:
        if checked:
            return "无制品 · 评论提及", Status.DONEQ, rework
        return "评论提及 %s" % beijing(mentions[-1].at), chip_status, rework
    if wts:
        w = wts[-1]
        return "wt %s · %dm 前" % (w.ref.get("name", "")[:8], _mins(now - w.at)), chip_status, rework
    if runs:
        r = runs[-1]
        return "CI %s" % (r.ref.get("conclusion") or r.ref.get("status") or "?"), chip_status, rework
    if checked:
        return "无 commit · 无 PR", Status.DONEQ, rework
    return "待：PR / 评论", chip_status, rework


def _dependency_problems(ctx: _Ctx) -> dict[str, str]:
    """R1-6：依赖不存在 / 成环 → 该步骤「未知」并记头部告警。"""
    problems: dict[str, str] = {}
    ids = set(ctx.step_by_id)
    for s in ctx.steps:
        missing = [d for d in s.needs if d not in ids]
        if missing:
            problems[s.id] = "依赖不存在：%s" % ", ".join(missing)
            ctx.warnings.append("依赖不存在：%s → %s" % (s.id, ", ".join(missing)))
    color: dict[str, int] = {}
    stack: list[str] = []

    def dfs(sid: str) -> None:
        color[sid] = 1
        stack.append(sid)
        for d in ctx.step_by_id[sid].needs:
            if d not in ids:
                continue
            if color.get(d, 0) == 1:
                cycle = stack[stack.index(d):] + [d]
                for member in cycle[:-1]:
                    problems.setdefault(member, "依赖成环：%s" % " → ".join(cycle))
                ctx.warnings.append("依赖成环：%s" % " → ".join(cycle))
            elif color.get(d, 0) == 0:
                dfs(d)
        stack.pop()
        color[sid] = 2

    for s in ctx.steps:
        if color.get(s.id, 0) == 0:
            dfs(s.id)
    return problems


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


def _affirmed(pattern: "re.Pattern[str]", text: str) -> bool:
    """首行全文里有一处关键词命中，且其前 6 个字符内没有否定词（不是 / 非 / 未 / 无 / 取消 / 引用 / 不算）。
    前文先剥掉同类关键词与空白，故「引用 codex 外审结论」里的「外审」同样被「引用」否定。"""
    for m in pattern.finditer(text):
        before = re.sub(r"[\s＋+·/]+", "", pattern.sub("", text[:m.start()]))
        if not NEGATION_RE.search(before[-NEGATION_SPAN:]):
            return True
    return False


def _classify_comment(first_line: str) -> tuple[bool, bool, bool]:
    text = _strip_heading(first_line)
    review = _affirmed(REVIEW_RE, text)
    external = _affirmed(EXTERNAL_RE, text) and bool(EXTERNAL_RESULT_RE.search(text))
    fixpack = _affirmed(FIXPACK_RE, text) and bool(FIXPACK_RESULT_RE.search(text))
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


def _rounds(ctx: _Ctx, section_index: Optional[int], subject: str) -> tuple[Rounds, list[Why], int]:
    """section_index 为 None 时统计 Trace 级（未归属任何模块的评论 / run）。返回 (Rounds, why, 评论条数)。"""
    why: list[Why] = []
    trace_level = section_index is None
    if not ctx.ok("gh.issue"):
        unk = Val.unknown("gh.issue")
        why.append(_why(subject, "轮数", E.COMMENT_TITLE, "gh.issue", "评论不可得：%s" % ctx.category("gh.issue"), None, False))
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
            hits.append("%s %s「%s」" % (mark, beijing(c["_at"]), _strip_heading(c.get("first_line") or "")[:24]))
        rounds = Rounds(Val(counts["审"][0], counts["审"][1], "gh.issue"), Val(counts["外"][0], counts["外"][1], "gh.issue"),
                        Val(counts["修"][0], counts["修"][1], "gh.issue"), Val(0, Grade.INFERRED, "gh.runs"), Val(0, Grade.INFERRED, "gh.runs"))
        why.append(_why(subject, "轮数", E.COMMENT_TITLE, "gh.issue", "审 %s · 外 %s · 修 %s（评论 %s 条%s）" % (
            rounds.review.text(), rounds.external.text(), rounds.fixpack.text(), _n(n_comments), "；" + "；".join(hits[:4]) if hits else ""), None))
    if not ctx.ok("gh.runs"):
        rounds.ci_red = Val.unknown("gh.runs", Grade.INFERRED)
        rounds.ci_green = Val.unknown("gh.runs", Grade.INFERRED)
        why.append(_why(subject, "CI", E.CI_CONCLUSION, "gh.runs", "run 不可得：%s" % ctx.category("gh.runs"), None, False))
    else:
        red = green = 0
        for r in ctx.runs:
            if r.get("_module") != section_index:
                continue
            concl = (r.get("conclusion") or "").lower()
            if concl in GREEN:
                green += 1
            elif concl in RED:
                red += 1
        rounds.ci_red = Val(red, Grade.INFERRED, "gh.runs")
        rounds.ci_green = Val(green, Grade.INFERRED, "gh.runs")
        lo, hi = ctx.module_windows.get(section_index, (None, None)) if not trace_level else (None, None)
        why.append(_why(subject, "CI", E.CI_CONCLUSION, "gh.runs", "红 %s 绿 %s（唯一归属：headSha 提交 → PR 分支 → 活动窗口 %s→%s）" % (
            rounds.ci_red.text(), rounds.ci_green.text(), beijing(lo) if lo else "?", beijing(hi) if hi else "now"), hi))
    return rounds, why, n_comments


def _module_view(ctx: _Ctx, section, views: list[StepView], n_sections: int) -> ModuleView:
    status = _module_status(views)
    checked_n = sum(1 for v in views if ctx.checked_map.get(v.step.id, False))
    done = sum(1 for v in views if v.status == Status.DONE)
    doneq = sum(1 for v in views if v.status == Status.DONEQ)
    unknown = sum(1 for v in views if v.status == Status.UNKNOWN)
    total = len(views)
    unparsed_n = sum(1 for _ln, idx in (getattr(ctx.table, "unparsed_section", {}) or {}).items() if idx == section.index)
    all_evs = [e for v in views for e in ctx.step_events.get(v.step.id, [])]
    last = max((e.at for e in all_evs), default=None)
    started, _win_end = ctx.module_windows.get(section.index, (None, None))
    finished = total > 0 and checked_n == total
    rounds, why, n_comments = _rounds(ctx, section.index, section.title)
    review_n = rounds.review.value if rounds.review.available else 0
    tier = _tier(int(review_n or 0)) if rounds.review.available else Tier.NONE
    ests = [v.step.est_min for v in views if v.step.est_min is not None]
    est = sum(ests) if ests else None
    actual = elapsed = None
    if started is not None:
        if finished and last is not None:
            actual = _mins(last - started)
        elif status in (Status.RUNNING, Status.WATCH, Status.STALLED, Status.UNKNOWN, Status.STALE) or not finished:
            elapsed = _mins(ctx.now - started)
    # A-3：章节无可解析步骤但有未解析行 → 未知；章节完全为空 → `—`
    if total == 0 and unparsed_n:
        status = Status.UNKNOWN
        what = "%s ?/?（未解析 %d 行）" % (section.title, unparsed_n)
    elif total == 0:
        what = "%s —" % section.title
    else:
        what = "%s 勾选 %d/%d" % (section.title, checked_n, total)
        if doneq:
            what += " · 未证 %d" % doneq
        if unknown:
            what += " · 未知 %d" % unknown
        if unparsed_n:
            what += " · 未解析 %d 行" % unparsed_n
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
    why.insert(0, _why(section.title, LABEL[status], E.CHECKBOX, "步骤聚合", "勾选 %d/%d · 完成 %d · 未证 %d · 未知 %d%s；步骤状态 %s" % (
        checked_n, total, done, doneq, unknown, "；未解析 %d 行" % unparsed_n if unparsed_n else "",
        " ".join("%s=%s" % (v.step.id, LABEL[v.status]) for v in views) or "无"), last))
    why.append(_why(section.title, "边框", E.COMMENT_TITLE, "gh.issue",
                    ("审核轮数 %s → 档位 %d" % (rounds.review.text(), int(tier))) if rounds.review.available else "审核轮数不可得 → 档位未知（画细虚线）",
                    None, rounds.review.available))
    if started is not None:
        hi = last if (finished and last) else ctx.now
        paused = timedelta(0)
        for p in ctx.pauses:
            lo2, hi2 = max(started, p["start"]), min(hi, p["end"] or ctx.now)
            if hi2 > lo2:
                paused += hi2 - lo2
        if paused:
            why.append(_why(section.title, "跨暂停", E.TASKTABLE_TAG, "git.tasktable_history", "活动窗口内含暂停 %s 分钟，时长未扣除" % _n(_mins(paused), Grade.REPORTED), None))
    return ModuleView(section=section, status=status, tier=tier, rounds=rounds, done=done, total=total, what=what, rounds_line=rounds_line,
                      evidence_line=evidence_line, actual_min=actual, elapsed_min=elapsed, est_min=est, needs=needs, why=why)


# ---------------------------------------------------------------- 阶段（§7.4）
def _compare_tag(ctx: _Ctx, published: Optional[str], res) -> Val:
    """R1-22：只捕兼容性异常（S-4 未合入 / 签名不同）；其余转不可得＋告警。"""
    try:
        from . import config as cfg
        fn = getattr(cfg, "compare_tag", None)
        if fn is not None:
            out = fn(published, res)
            if isinstance(out, Val):
                return out
    except (ImportError, AttributeError, TypeError, NotImplementedError):
        pass
    except Exception as exc:  # noqa: BLE001 — 内部错误不得变成确定结论
        ctx.warnings.append("阶段比对内部错误：%s" % exc.__class__.__name__)
        return Val.unknown(res.key, res.grade)
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
    # 合入主干（R1-11）：只认唯一识别的批次 PR
    merged_at: Optional[datetime] = None
    merge_sha = ""
    merged_na = False
    if not ctx.ok("gh.prs"):
        merged = Val.unknown("gh.prs")
        why.append(_why("阶段·合入主干", "未知", E.PR_STATE, "gh.prs", "gh.prs 不可得：%s" % ctx.category("gh.prs"), None, False))
    elif not ctx.snap.branch:
        merged, merged_na = Val.unknown("gh.prs"), True
        why.append(_why("阶段·合入主干", "不适用", E.PR_STATE, "gh.prs", "无批次分支，无法识别批次 PR（不适用）", None, False))
    elif len(ctx.batch_prs) > 1:
        merged = Val.unknown("gh.prs")
        why.append(_why("阶段·合入主干", "未知", E.PR_STATE, "gh.prs", "分支 %s 对应多个 PR（%s），身份冲突" % (
            ctx.snap.branch, " ".join("#%d" % p["number"] for p in ctx.batch_prs)), None, False))
    elif ctx.batch_pr is None:
        merged = Val(False, Grade.MEASURED, "gh.prs")
        why.append(_why("阶段·合入主干", "否", E.PR_STATE, "gh.prs", "分支 %s 尚无 PR" % ctx.snap.branch, None))
    else:
        bp = ctx.batch_pr
        merged = Val(bp["_state"] == "MERGED", Grade.MEASURED, "gh.prs", bp["_merged"])
        merged_at = bp["_merged"]
        merge_sha = (bp.get("mergeCommit") or "") if merged_at else ""
        why.append(_why("阶段·合入主干", "是" if merged.value else "否", E.PR_STATE, "gh.prs", "批次 PR #%d %s%s" % (
            bp["number"], bp["_state"], " → 合并提交 %s" % merge_sha[:7] if merge_sha else ""), bp["_merged"]))
    levels.append(StageLevel("merged", STAGE_LABEL["merged"], merged, configured=not merged_na))

    # 已发布（R1-12 / R1-13）：须有已证实的合并点；祖先关系优先 gh.compare，其次本地祖先（推），再次时间（推）
    workflow = ctx.cfg.get("release_workflow") or getattr(ctx.conf, "release_workflow", None) or ""
    notes: list[str] = []

    def descendant(sha: str) -> tuple[Optional[bool], Grade]:
        if not sha:
            return None, Grade.MEASURED
        if merge_sha and _sha_eq(sha, merge_sha):
            return True, Grade.MEASURED
        st = ctx.compare_results.get(sha) if (merge_sha and _sha_eq(ctx.compare_base, merge_sha)) else None
        if st in ("ahead", "identical"):
            return True, Grade.MEASURED
        if st in ("behind", "diverged"):
            return False, Grade.MEASURED
        c = ctx._commit_by_prefix(sha)
        if c is not None and merged_at is not None:
            notes.append("%s 按时间判（gh.compare 不可得）" % sha[:7])
            return c["_at"] >= merged_at, Grade.INFERRED
        return None, Grade.INFERRED

    release_run, run_grade = None, Grade.MEASURED
    if workflow and ctx.ok("gh.release_runs") and merged_at is not None:
        for r in ctx.val("gh.release_runs", []):
            at = parse_ts(r.get("createdAt") or "")
            if at is None or at > now or at < merged_at or (r.get("conclusion") or "").lower() != "success":
                continue
            d, g = descendant(r.get("headSha") or "")
            if d:
                release_run, run_grade = r, g
                break
    matched_tag, tag_grade, undecided = None, Grade.MEASURED, 0
    if ctx.ok("gh.tags") and merged_at is not None:
        for t in ctx.gh_tags:
            d, g = descendant(t.get("sha", ""))
            if d is None and t["_at"] is not None:
                notes.append("tag %s 按时间判" % t["name"])
                d, g = t["_at"] >= merged_at, Grade.INFERRED
            if d is None:
                undecided += 1
                continue
            if d:
                matched_tag, tag_grade = t, g
                break
    local_ref = ", ".join(t["name"] for t in ctx.tags if merged_at is not None and t["_at"] >= merged_at) or "无"
    published_tag = matched_tag["name"] if matched_tag else None
    note_text = ("；" + "；".join(notes[:2])) if notes else ""
    if merged.available and merged.value is False and not merged_na:
        published = Val(False, Grade.MEASURED, "gh.prs")
        why.append(_why("阶段·已发布", "否", E.TAG_REF, "gh.prs", "批次 PR 未合入，尚无合并点", None))
    elif merged_at is None:
        published = Val.unknown("gh.prs")
        why.append(_why("阶段·已发布", "未知", E.TAG_REF, "gh.prs", "无已证实的合并点（合入主干 %s）" % ("不适用" if merged_na else "未知"), None, False))
    elif not ctx.ok("gh.tags"):
        published = Val.unknown("gh.tags")
        why.append(_why("阶段·已发布", "未知", E.TAG_REF, "gh.tags", "gh.tags 不可得：%s（本地 git.tags 参考：%s）" % (
            ctx.category("gh.tags"), local_ref if ctx.ok("git.tags") else "不可得"), None, False))
    elif workflow and not ctx.ok("gh.release_runs"):
        published = Val.unknown("gh.release_runs")
        why.append(_why("阶段·已发布", "未知", E.WORKFLOW_RUN, "gh.release_runs", "gh.release_runs 不可得：%s" % ctx.category("gh.release_runs"), None, False))
    elif workflow:
        ok = release_run is not None and matched_tag is not None
        at = parse_ts(release_run.get("createdAt") or "") if release_run else None
        grade = Grade.INFERRED if (Grade.INFERRED in (run_grade, tag_grade)) else Grade.MEASURED
        published = Val(ok, grade, "gh.release_runs", at)
        why.append(_why("阶段·已发布", "是" if ok else "否", E.WORKFLOW_RUN, "gh.release_runs", "发布 run %s；tag %s（本地参考：%s）%s" % (
            "success %s %s" % ((release_run.get("headSha") or "")[:7], beijing(at)) if release_run else "无合并后且为合并提交后代的成功 run",
            "%s → %s" % (matched_tag["name"], matched_tag.get("sha", "")[:7]) if matched_tag else "无合并后的 tag", local_ref, note_text), at))
    else:
        if matched_tag is None and undecided:
            published = Val.unknown("gh.tags")
            why.append(_why("阶段·已发布", "未知", E.TAG_REF, "gh.tags", "未配置发布工作流；%d 个 tag 既无祖先关系也无时刻，无法判定%s" % (undecided, note_text), None, False))
        else:
            published = Val(matched_tag is not None, tag_grade if matched_tag else Grade.MEASURED, "gh.tags", matched_tag["_at"] if matched_tag else None)
            why.append(_why("阶段·已发布", "是" if matched_tag else "否", E.TAG_REF, "gh.tags", "未配置发布工作流，按合并点之后的 tag 判定：%s（本地参考：%s）%s" % (
                "%s → %s" % (matched_tag["name"], matched_tag.get("sha", "")[:7]) if matched_tag else "无 tag", local_ref, note_text), published.at))
    levels.append(StageLevel("published", STAGE_LABEL["published"], published))

    # 预发 / 生产（R1-14：已发布未知 → 一律未知）
    stage_keys = {s.get("key") for s in (ctx.cfg.get("stages") or [])}
    conf_stages = getattr(ctx.conf, "stages", None) or {}
    for key in ("staging", "production"):
        configured = key in stage_keys or (isinstance(conf_stages, dict) and key in conf_stages)
        if not configured:
            levels.append(StageLevel(key, STAGE_LABEL[key], Val.unknown("config.%s" % key), configured=False))
            why.append(_why("阶段·" + STAGE_LABEL[key], "未配置", E.CONFIG_COMMAND, "config.%s" % key, "证据源配置未声明", None, False))
            continue
        res = _stage_result(ctx, key)
        if not published.available:
            val = Val.unknown(res.key, res.grade)
            why.append(_why("阶段·" + STAGE_LABEL[key], "未知", E.IMAGE_TAG, res.key, "已发布未知 → 本级未知（不沿用旧结论）", res.fetched_at, False))
        else:
            val = _compare_tag(ctx, published_tag, res)
            why.append(_why("阶段·" + STAGE_LABEL[key], ("是" if val.value else "否") if val.available else "未知", E.IMAGE_TAG, res.key,
                            ("取得 %s vs 已发布 %s" % (str(res.value).strip()[:40], published_tag or "无")) if res.ok else "%s：%s" % (res.key, ctx.category(res.key)),
                            res.fetched_at, val.available))
        levels.append(StageLevel(key, STAGE_LABEL[key], val))
    # 收口
    if not ctx.ok("gh.issue"):
        closed = Val.unknown("gh.issue")
        why.append(_why("阶段·收口", "未知", E.ISSUE_STATE, "gh.issue", "gh.issue 不可得：%s" % ctx.category("gh.issue"), None, False))
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

    def is_unknown(key: str) -> bool:
        s = lv.get(key)
        return bool(s and s.configured and not s.value.available)

    short = re.sub(r"^\d+-", "", ctx.snap.trace_dir.split("/")[-1])
    title = "Trace #%s %s" % (ctx.snap.trace_no or "?", short) + (" · %s" % ctx.snap.branch if ctx.snap.branch else "")
    checked_text = "%d/%s 勾选" % (n_checked, _n(total))
    wts = [w for w in ctx.worktrees if not w.get("main")]
    wt_text = ("worktree %s" % _n(len(wts))) if ctx.ok("git.worktrees") else "worktree 未知"
    # 阶段（R1-15：合入 / 收口不可得 → 未知，不显示「执行中」）
    current = next((m for m in modules if m.total == 0 and m.status == Status.UNKNOWN or (m.total and sum(
        1 for v in views if v.step.section == m.section.index and ctx.checked_map.get(v.step.id, False)) < m.total)), None)
    if not ctx.table_ok:
        stage = "未知（任务表不可得：%s）" % getattr(ctx.table, "error", "")
        nxt = "未知（任务表不可得）"
    elif is_true("closed"):
        stage = "已收口（Issue 关闭 %s）· %s" % (beijing(lv["closed"].value.at), checked_text)
        nxt = "无（Trace 已关闭）"
    elif is_unknown("closed"):
        stage = "未知（收口证据 gh.issue 不可得）· %s" % checked_text
        nxt = "未知（收口证据不可得） · " + wt_text
    elif is_true("production"):
        stage = "已上生产 · %s" % checked_text
        nxt = "观察与收口 · " + wt_text
    elif is_true("staging"):
        stage = "预发已升级 · %s" % checked_text
        nxt = _next_step(ctx, views, wt_text)
    elif is_true("published"):
        stage = "已发布 · %s" % checked_text
        nxt = _next_step(ctx, views, wt_text)
    elif is_true("merged"):
        stage = "已合入主干 · %s" % checked_text
        nxt = _next_step(ctx, views, wt_text)
    elif is_unknown("merged"):
        stage = "未知（合入主干证据不可得）· %s" % checked_text
        nxt = _next_step(ctx, views, wt_text)
    else:
        stage = "执行中 · %s（%s）" % (current.section.title if current else "全部勾选", checked_text)
        nxt = _next_step(ctx, views, wt_text)
    # 阻塞：只放当前阻塞（K-4：短句）
    block_parts: list[str] = []
    if not ctx.table_ok:
        block_parts.append("任务表不可得")
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
    # 预算（每项一行 Why，R1-23）
    budget: list[tuple[str, Val, Optional[int]]] = []
    for b in ctx.cfg.get("budgets") or []:
        key = b.get("result_key") or ("config.%s" % b.get("key"))
        res = ctx.snap.get(key)
        label = b.get("label") or b.get("key") or ""
        val = Val(res.value, res.grade, res.key, res.fetched_at) if res.ok else Val.unknown(res.key, res.grade)
        budget.append((label, val, b.get("cap")))
        why.append(_why("预算·" + label, val.text() if res.ok else "未知", E.CONFIG_COMMAND, key,
                        ("取值 %s" % str(res.value)[:40] + ("，上限 %s" % b.get("cap") if b.get("cap") is not None else "")) if res.ok else "%s：%s" % (key, ctx.category(key)),
                        res.fetched_at, res.ok))
    if not budget:
        budget.append(("PR", Val(len(ctx.prs), Grade.MEASURED, "gh.prs") if ctx.ok("gh.prs") else Val.unknown("gh.prs"), None))
        budget.append(("CI 次数", Val(len(ctx.runs), Grade.MEASURED, "gh.runs") if ctx.ok("gh.runs") else Val.unknown("gh.runs"), None))
    # 存疑（K-4：短句、去重）
    doubt_parts: list[str] = []
    if not ctx.table_ok:
        doubt_parts.append("未知（任务表不可得）")
    doneq = [v.step.id for v in views if v.status == Status.DONEQ]
    if doneq:
        doubt_parts.append("自述未证 %s（%s%s）" % (_n(len(doneq)), "/".join(doneq[:3]), "…" if len(doneq) > 3 else ""))
    if ctx.contract_pr is not None:
        p = ctx.contract_pr
        flags = []
        if p["_state"] == "MERGED" and _pr_self_merged(p):
            flags.append("自合")
        if p["_state"] == "MERGED" and not _pr_approved(p):
            flags.append("零批准")
        if flags:
            doubt_parts.append("合同 PR #%d %s" % (p["number"], "/".join(flags)))
        why.append(_why("合同 PR #%d" % p["number"], "存疑" if flags else "正常", E.PR_MERGED_BY, "git.contract",
                        "首次加入 合同.md 的提交 %s；PR %s；mergedBy=%s author=%s；APPROVED review %d（gh.prs）" % (
                            (ctx.contract or {}).get("sha", "")[:7], p["_state"], p.get("mergedBy") or "-", p.get("author") or "-",
                            sum(1 for r in p.get("reviews") or [] if (r.get("state") or "").upper() == "APPROVED")), p["_merged"] or p["_created"]))
    elif ctx.contract and ctx.ok("gh.prs"):
        why.append(_why("合同 PR", "未找到", E.PR_MERGED_BY, "git.contract", "合同.md 首次提交 %s 未对应任何 PR" % ctx.contract.get("sha", "")[:7], parse_ts(ctx.contract.get("at") or "")))
    shared = ["#%d" % p["number"] for p in ctx.prs if len(p["_steps"]) >= 2]
    if shared:
        doubt_parts.append("共用 PR %s" % " ".join(shared[:3]) + ("…" if len(shared) > 3 else ""))
        why.append(_why("共用 PR", "%s 个" % _n(len(shared)), E.PR_STATE, "gh.prs", "；".join(
            "#%d（%s）" % (p["number"], "/".join(sorted(p["_steps"])[:4])) for p in ctx.prs if len(p["_steps"]) >= 2)[:200], None))
    if ctx.ok("gh.prs"):
        merged_prs = [p for p in ctx.prs if p["_state"] == "MERGED"]
        if merged_prs:
            n_self = sum(1 for p in merged_prs if _pr_self_merged(p))
            n_appr = sum(1 for p in merged_prs if _pr_approved(p))
            tally = "PR 自合 %d/%s" % (n_self, _n(len(merged_prs)))
            tally += " 零批准" if n_appr == 0 else " 批准 %s" % _n(n_appr)
            doubt_parts.append(tally)
            why.append(_why("PR 合并方式", tally, E.PR_MERGED_BY, "gh.prs", "自合 %s" % " ".join("#%d" % p["number"] for p in merged_prs if _pr_self_merged(p)), None))
    else:
        doubt_parts.append("PR 存疑未知（gh.prs）")
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
            text = "空档 %s 分 %s→%s" % (_n(_mins(gap), Grade.INFERRED), beijing(a.at), beijing(b.at))
            if paused:
                text += "（暂停 %s）" % _n(_mins(paused), Grade.REPORTED)
            doubt_parts.append(text)
            why.append(_why("空档", "%s 分钟" % _n(_mins(gap), Grade.INFERRED), b.etype, b.source,
                            "%s %s → %s %s%s" % (a.label, beijing(a.at, "%m-%d %H:%M:%S"), b.label, beijing(b.at, "%m-%d %H:%M:%S"),
                                                 "；归因暂停 %s 分钟" % _n(_mins(paused), Grade.REPORTED) if paused else ""), b.at))
    doubt = " · ".join(doubt_parts) if doubt_parts else "无"
    # 最后外部证据（R1-21：附加证据行进这里；不可得按依赖逐项传播）
    missing_live = [k for k in LIVE_KEYS if not ctx.ok(k)]
    external = [e for e in ctx.events if e.kind != "checkbox"]
    if not ctx.table_ok:
        evidence = "未知（任务表不可得）"
    elif external:
        last = external[-1]
        who = "/".join(sorted(last.steps)[:2]) if last.steps else "Trace"
        evidence = "%s 分钟前 · %s（%s）· %s" % (_n(_mins(now - last.at)), last.label, who, beijing(last.at, "%m-%d %H:%M"))
        if missing_live:
            evidence += " · 未知：%s" % "/".join(missing_live)
    elif missing_live:
        evidence = "未知（%s 不可得）" % "/".join(missing_live)
    else:
        evidence = "无"
    for e_cfg in ctx.cfg.get("evidence") or []:
        key = e_cfg.get("result_key") or ("config.%s" % e_cfg.get("key"))
        res = ctx.snap.get(key)
        label = e_cfg.get("label") or e_cfg.get("key") or key
        if res.ok:
            shown = res.value
            if isinstance(shown, list):
                shown = "%d 行" % len(shown)
            evidence += " · %s %s" % (label, Val(str(shown)[:24], res.grade).text())
            why.append(_why("外部证据·" + label, "可得", E.CONFIG_COMMAND, key, "取值 %s" % str(res.value)[:60], res.fetched_at))
        else:
            evidence += " · %s 未知（%s）" % (label, ctx.category(key))
            why.append(_why("外部证据·" + label, "未知", E.CONFIG_COMMAND, key, "%s：%s" % (key, ctx.category(key)), res.fetched_at, False))
    # 附注与告警
    warnings = list(ctx.warnings)
    if window_alive is not True:
        warnings.append(WINDOW_NOTE)
    if ctx.log_mode == "all" and ctx.ok("git.log"):
        warnings.append("证据可能串线（无批次分支，按全部分支取提交，角标推）")
    if ctx.log_truncated:
        warnings.append("git.log 触顶 5000 条，提交证据可能不完整")
    if ctx.table.unparsed:
        warnings.append("任务表未解析 %s 行" % _n(len(ctx.table.unparsed)))
    if ctx.table.overlong:
        warnings.append("任务表超限 %s 行" % _n(len(ctx.table.overlong)))
    for key in ("git.log", "git.tasktable_history", "git.worktrees", "gh.prs", "gh.issue", "gh.runs", "gh.tags"):
        r = ctx.snap.get(key)
        if not r.ok:
            warnings.append("%s 不可得：%s" % (key, ctx.category(key)))
    return Header(title=title, stage=stage, block=block, nxt=nxt, budget=budget, doubt=doubt, evidence=evidence, stages=levels, warnings=warnings)


def _next_step(ctx: _Ctx, views: list[StepView], wt_text: str) -> str:
    first = next((v for v in views if not ctx.checked_map.get(v.step.id, False)), None)
    return ("%s %s（%s）" % (first.step.id, first.step.title[:18], LABEL[first.status]) if first else "无未勾选 Step") + " · " + wt_text


# ---------------------------------------------------------------- 入口
def infer(snapshot: Snapshot, conf) -> Board:
    ctx = _Ctx(snapshot, conf)
    checked_map = {s.id: ctx.effective_checked(s) for s in ctx.steps}
    ctx.checked_map = checked_map
    dep_problems = _dependency_problems(ctx)
    # 两遍：先算不依赖「依赖状态」的步骤（勾选 / 有证据 / 人工 / 失效 / 未知），再算 ready / todo
    empty_dep: dict[str, Status] = {}
    first_pass: dict[str, StepView] = {s.id: _step_view(ctx, s, checked_map, empty_dep, dep_problems) for s in ctx.steps}
    dep_status = {sid: v.status for sid, v in first_pass.items()}
    views: list[StepView] = [first_pass[s.id] if first_pass[s.id].status not in (Status.READY, Status.TODO)
                             else _step_view(ctx, s, checked_map, dep_status, dep_problems) for s in ctx.steps]
    view_by_section: dict[int, list[StepView]] = {}
    for v in views:
        view_by_section.setdefault(v.step.section, []).append(v)
    sections = list(ctx.table.sections) if ctx.table_ok else []
    n_sections = len(sections)
    ctx.assign({sec.index: _module_window(ctx, view_by_section.get(sec.index, [])) for sec in sections})
    modules = [_module_view(ctx, sec, view_by_section.get(sec.index, []), n_sections) for sec in sections]
    levels, stage_why, _tag = _stages(ctx)
    if not ctx.table_ok:
        levels = [StageLevel(s.key, s.label, Val.unknown(s.value.source), configured=s.configured) for s in levels]
        stage_why.append(_why("阶段", "未知", E.CHECKBOX, "任务表", "任务表不可得（%s）：头部全部未知" % getattr(ctx.table, "error", ""), None, False))
        ctx.warnings.append("任务表不可得：%s" % getattr(ctx.table, "error", ""))
    header_why: list[Why] = []
    header = _header(ctx, views, modules, levels, header_why)
    trace_rounds, trace_why, _n_comments = _rounds(ctx, None, "Trace")
    if any(v.available and v.value for v in (trace_rounds.review, trace_rounds.external, trace_rounds.fixpack)):
        header.stage += " · Trace 级 审 %s 外 %s 修 %s" % (trace_rounds.review.text(), trace_rounds.external.text(), trace_rounds.fixpack.text())
    board = Board(header=header, steps=views, modules=modules, generated_at=ctx.now, why=stage_why + header_why + trace_why,
                  unparsed=list(ctx.table.unparsed) if ctx.table_ok else [])
    board.validate()
    return board
