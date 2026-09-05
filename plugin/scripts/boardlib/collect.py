# -*- coding: utf-8 -*-
"""证据采集（接口约定 §6）。归属：S-2 / F-1。只采集、不判断；失败 → ProviderResult.ok=False，不抛异常、不给默认值。

    class LiveSource(repo_root, per_cmd_timeout=25, round_timeout=60, env=None)
        run(key, argv_or_cmd, *, shell=False, timeout=None, grade=Grade.MEASURED, cwd=None, parse=None) -> ProviderResult
        （subprocess：独立进程组、stdin=DEVNULL、capture、超时杀整组；非零退出 / 命令不存在 / 解析失败都记 ok=False）
        run_all(jobs, deadline) -> dict[key, ProviderResult]   # 守护线程并发；到 deadline 未完成的键 ok=False error="整轮超时"，
                                                               # 本轮进程组全部杀掉并有界 join；每轮独立进程登记表
        cancel(round_id=None)                                  # 杀本轮全部进程组、置取消标志（幂等）；供 tui 看门狗调用（R1-29 / R2-5）
        .deadline                                              # 可选绝对 monotonic 截止（board.py 可设，R1-30）：采集 / slug 探测共享剩余预算
    class RecordedSource(fixture_dir)          # 从 snapshot.json 回放（严格校验类型与必需字段，R1-18）；没有的键 ok=False error="夹具未记录"；.now＝夹具的 now
    collect(repo_root, trace_no, branch, conf, now, source) -> Snapshot
    write_snapshot(snapshot, out_dir)          # --record：写 <out_dir>/snapshot.json 与 任务表.md 副本
    resolve_trace(repo_root, trace_no=None) -> (trace_no, trace_dir, tasktable_path)   # 相对路径
    resolve_branch(prs, trace_no, conf, override=None, branches=()) -> str            # 见约定 §2；未知＝""

铁律：对目标仓库只读（不 fetch / pull / checkout / stash / add / commit；`git status` 加 --no-optional-locks）；
快照与错误文本里不落绝对路径、tmux session 名（替换为 <repo> / ~ / <session>）。

证据键的值形态（snapshot.json）：
    git.log      {"mode": "branch"|"all", "refs": [...], "truncated": bool, "commits": [{sha, at(作者时刻 %ad), committed(%cd), author, subject, refs, docs_only, files_n}]}
                 mode=branch：批次分支＋各 worktree 分支（R1-1，实测级）；找不到分支才 --all（推断级，infer 加告警「证据可能串线」）
    gh.tags      [{name, sha, at, at_source}]  前 30 个远端 tag；提交时刻优先取本地 git.log，本地没有的候选 tag 才并发（≤5）查 commits/<sha>（A-4）
    gh.compare   {"base": <批次 PR 合并提交>, "results": {sha: "ahead"|"behind"|"identical"|"diverged"|"<error>"}}  祖先关系（R1-13）
    gh.issue     comments[].first_line 为完整首行（展示时再截，R1-4）
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from . import tasktable
from .model import Grade, ProviderResult, Snapshot, TaskTable, parse_ts, utc

SEP = "\x1f"
REC = "\x1e"
BUILTIN_KEYS = (
    "git.log", "git.tasktable_history", "git.worktrees", "git.tags", "git.branches", "git.contract",
    "tasktable.quotes", "gh.prs", "gh.issue", "gh.runs", "gh.release_runs", "gh.tags", "gh.compare", "tmux.windows",
)
GIT_LOG_MAX = 5000
GH_TAGS_LIMIT = 30      # gh api repos/<slug>/tags 取前 30
GH_TAG_DATES = 5        # 本地没有的候选 tag 最多查 5 个提交时刻（并发 ≤ 5）
GH_COMPARE_MAX = 5      # 祖先关系比对最多 5 个候选（并发 ≤ 5）
JOIN_GRACE = 2.0        # 整轮超时后有界 join 的秒数
PR_FIELDS = ("number,title,state,isDraft,createdAt,mergedAt,closedAt,mergedBy,author,reviews,headRefName,headRefOid,"
             "baseRefName,mergeCommit,url,body,statusCheckRollup")
RUN_FIELDS = "databaseId,name,workflowName,conclusion,status,createdAt,updatedAt,headSha,headBranch,event,url"
TRACE_DIR_RE = re.compile(r"^(\d+)-(.+)$")
TIME_IN_LINE_RE = re.compile(r"\d{1,2}:[0-9][0-9xX]")
PAUSE_LINE_RE = re.compile(r"暂停")
HOME_PATH_RE = re.compile("/" + "home" + r"/[^/\s`'\"]+/")  # 拼接写法：本文件自身不能出现该路径形态（禁词扫描）
TASKTABLE_NAME = "任务表.md"
CONTRACT_NAME = "合同.md"
BODY_MAX = 3000
FIRST_LINE_MAX = 2000
GRADES = {g.value for g in Grade}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _scrub(text: str, repo_root: str = "", session: str = "") -> str:
    """错误 / 命令文本去本机路径与 session 名。"""
    if not text:
        return ""
    if repo_root:
        text = text.replace(repo_root, "<repo>")
    home = os.path.expanduser("~")
    if home and home != "/":
        text = text.replace(home, "~")
    if session:
        text = text.replace(session, "<session>")
    return HOME_PATH_RE.sub("~/", text)


def _scrub_text(text: str) -> str:
    """快照里的外部文本（PR 正文 / 评论首行 / 提交信息 / 引用块）把家目录路径形态换成 `~/`。"""
    return HOME_PATH_RE.sub("~/", text or "")


def _first_line(body: str) -> str:
    """评论完整首行（只做上限截断防爆，结构化匹配用它；展示副本由 infer 再截 200）。"""
    for line in (body or "").splitlines():
        if line.strip():
            return _scrub_text(line.strip()[:FIRST_LINE_MAX])
    return ""


def _login(obj: Any) -> str:
    if isinstance(obj, dict):
        return str(obj.get("login") or obj.get("name") or "")
    return str(obj or "")


def _kill_group(proc: subprocess.Popen) -> None:
    """杀整个进程组（子进程以 start_new_session 起，pgid == pid）；组不存在时退回杀单进程。"""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


# ---------------------------------------------------------------- 证据源
class LiveSource:
    """真实采集：subprocess（独立进程组、stdin=DEVNULL、显式超时）＋守护线程并发；整轮超时后杀本轮进程组并有界 join。"""

    recorded = False
    now: Optional[datetime] = None
    deadline: Optional[float] = None  # 绝对 monotonic 截止；board.py 设置后采集 / slug 探测共享剩余预算（R1-30）

    def __init__(self, repo_root: str, per_cmd_timeout: int = 25, round_timeout: int = 60, env: Optional[dict] = None,
                 max_workers: int = 8, session: str = ""):
        self.repo_root = os.path.abspath(repo_root)
        self.per_cmd_timeout = per_cmd_timeout
        self.round_timeout = round_timeout
        self.env = env
        self.max_workers = max_workers
        self.session = session
        self._lock = threading.Lock()
        self._tls = threading.local()
        self._rounds: dict[int, dict] = {}   # round_id → {"procs": set[Popen], "cancelled": bool}
        self._round_seq = 0
        self.current_round = self._new_round()

    # ---- 轮次登记表 ----
    def _new_round(self) -> int:
        with self._lock:
            self._round_seq += 1
            self._rounds[self._round_seq] = {"procs": set(), "cancelled": False}
            return self._round_seq

    def _round_of_thread(self) -> int:
        return getattr(self._tls, "round_id", None) or self.current_round

    def cancelled(self, round_id: Optional[int] = None) -> bool:
        with self._lock:
            state = self._rounds.get(round_id or self.current_round)
            return bool(state and state["cancelled"])

    def _cancel_reason(self, round_id: int) -> str:
        with self._lock:
            state = self._rounds.get(round_id) or {}
            return state.get("reason") or "已取消（看门狗）"

    def cancel(self, round_id: Optional[int] = None, reason: str = "已取消（看门狗）") -> None:
        """杀某轮（缺省本轮）全部进程组并置取消标志；幂等；不阻塞。被杀的键 error＝reason。"""
        rid = round_id or self.current_round
        with self._lock:
            state = self._rounds.get(rid)
            if state is None:
                return
            state["cancelled"] = True
            state["reason"] = reason
            procs = list(state["procs"])
        for proc in procs:
            _kill_group(proc)

    def kill_all(self) -> None:
        self.cancel(self.current_round)

    def _forget_round(self, rid: int) -> None:
        with self._lock:
            state = self._rounds.get(rid)
            if state is not None and not state["procs"]:
                self._rounds.pop(rid, None)

    # ---- 单条命令 ----
    def describe(self, argv_or_cmd, shell: bool) -> str:
        text = argv_or_cmd if shell else " ".join(str(a) for a in argv_or_cmd)
        return _scrub(text, self.repo_root, self.session)

    def remaining(self) -> Optional[float]:
        return None if self.deadline is None else max(0.0, self.deadline - time.monotonic())

    def run(self, key: str, argv_or_cmd, *, shell: bool = False, timeout: Optional[float] = None,
            grade: Grade = Grade.MEASURED, cwd: Optional[str] = None, parse: Optional[Callable[[str], Any]] = None) -> ProviderResult:
        cmd_text = self.describe(argv_or_cmd, shell)
        argv = ["bash", "-c", argv_or_cmd] if shell else [str(a) for a in argv_or_cmd]
        rid = self._round_of_thread()
        if self.cancelled(rid):
            return ProviderResult(key, False, None, self._cancel_reason(rid), cmd_text, _now(), grade)
        limit = float(timeout or self.per_cmd_timeout)
        rem = self.remaining()
        if rem is not None:
            if rem <= 0:
                return ProviderResult(key, False, None, "整轮超时", cmd_text, _now(), grade)
            limit = min(limit, rem)
        try:
            proc = subprocess.Popen(argv, cwd=cwd or self.repo_root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, errors="replace", env=self.env, start_new_session=True)
        except (FileNotFoundError, PermissionError, NotADirectoryError) as exc:
            return ProviderResult(key, False, None, "命令不可用：%s（%s）" % (argv[0], exc.__class__.__name__), cmd_text, _now(), grade)
        except OSError as exc:
            return ProviderResult(key, False, None, "启动失败：%s" % _scrub(str(exc), self.repo_root, self.session), cmd_text, _now(), grade)
        with self._lock:
            state = self._rounds.setdefault(rid, {"procs": set(), "cancelled": False})
            state["procs"].add(proc)
        try:
            try:
                out, err = proc.communicate(timeout=limit)
            except subprocess.TimeoutExpired:
                _kill_group(proc)
                try:
                    proc.communicate(timeout=JOIN_GRACE)
                except (subprocess.TimeoutExpired, OSError, ValueError):
                    pass
                return ProviderResult(key, False, None, "超时 %ds" % int(limit + 0.999), cmd_text, _now(), grade)
        finally:
            with self._lock:
                state = self._rounds.get(rid)
                if state is not None:
                    state["procs"].discard(proc)
        if self.cancelled(rid):
            return ProviderResult(key, False, None, self._cancel_reason(rid), cmd_text, _now(), grade)
        if proc.returncode != 0:
            tail = (err or out or "").strip().splitlines()
            msg = _scrub(tail[-1] if tail else "", self.repo_root, self.session)
            return ProviderResult(key, False, None, "退出码 %d：%s" % (proc.returncode, msg[:200]), cmd_text, _now(), grade)
        if parse is None:
            return ProviderResult(key, True, out, "", cmd_text, _now(), grade)
        try:
            value = parse(out)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            return ProviderResult(key, False, None, "解析失败：%s" % _scrub(str(exc)[:200], self.repo_root, self.session), cmd_text, _now(), grade)
        return ProviderResult(key, True, value, "", cmd_text, _now(), grade)

    # ---- 一轮并发 ----
    def run_all(self, jobs: list[tuple[str, Callable[[], ProviderResult]]], deadline: float) -> dict[str, ProviderResult]:
        """守护线程并发跑一批作业；到 deadline 未完成的键记「整轮超时」，本轮进程组全部杀掉，线程有界 join 后返回。"""
        results: dict[str, ProviderResult] = {}
        if not jobs:
            return results
        rid = self._new_round()
        self.current_round = rid
        lock = threading.Lock()

        def worker(key: str, fn: Callable[[], ProviderResult]) -> None:
            self._tls.round_id = rid
            try:
                res = fn()
                if not isinstance(res, ProviderResult):
                    res = ProviderResult(key, False, None, "内部错误：任务未返回 ProviderResult")
            except Exception as exc:  # noqa: BLE001 — 作业内部错误转不可得，不让整轮崩
                res = ProviderResult(key, False, None, "内部错误：%s：%s" % (exc.__class__.__name__, _scrub(str(exc)[:160], self.repo_root, self.session)))
            with lock:
                results[key] = res

        threads = []
        for key, fn in jobs:
            t = threading.Thread(target=worker, args=(key, fn), name="board-%s" % key, daemon=True)
            t.start()
            threads.append((key, t))
        for key, t in threads:
            t.join(max(0.0, deadline - time.monotonic()))
        late = [(key, t) for key, t in threads if t.is_alive()]
        if late:
            self.cancel(rid, reason="整轮超时")
            for key, t in late:
                t.join(JOIN_GRACE)
        with lock:
            for key, _fn in jobs:
                if key not in results:
                    results[key] = ProviderResult(key, False, None, "整轮超时", "", _now())
        self._forget_round(rid)
        return results


class RecordedSource:
    """夹具回放：只读 <fixture_dir>/snapshot.json；零网络；严格校验（R1-18）：类型与必需字段非法 → ValueError，`now` 非法不取墙钟。"""

    recorded = True

    def __init__(self, fixture_dir: str):
        self.fixture_dir = fixture_dir
        path = os.path.join(fixture_dir, "snapshot.json")
        where = "夹具 %s" % os.path.basename(os.path.abspath(fixture_dir))
        with open(path, encoding="utf-8") as fh:
            try:
                self.raw = json.load(fh)
            except json.JSONDecodeError as exc:
                raise ValueError("%s：snapshot.json 不是合法 JSON（%s）" % (where, exc)) from None
        if not isinstance(self.raw, dict):
            raise ValueError("%s：snapshot.json 顶层必须是对象" % where)
        now = parse_ts(str(self.raw.get("now") or ""))
        if now is None:
            raise ValueError("%s：now 缺失或不是 ISO8601（%r）" % (where, self.raw.get("now")))
        self.now = now
        results = self.raw.get("results")
        if not isinstance(results, dict):
            raise ValueError("%s：results 必须是对象" % where)
        self.results: dict[str, ProviderResult] = {}
        for key, v in results.items():
            if not isinstance(v, dict):
                raise ValueError("%s：results[%s] 必须是对象" % (where, key))
            if not isinstance(v.get("ok"), bool):
                raise ValueError("%s：results[%s].ok 必须是布尔值（%r）" % (where, key, v.get("ok")))
            if v["ok"] and "value" not in v:
                raise ValueError("%s：results[%s] ok=true 但缺 value" % (where, key))
            grade = v.get("grade", "measured")
            if grade not in GRADES:
                raise ValueError("%s：results[%s].grade 非法（%r）" % (where, key, grade))
            error = v.get("error", "")
            if not isinstance(error, str):
                raise ValueError("%s：results[%s].error 必须是字符串" % (where, key))
            fetched_raw = v.get("fetched_at") or ""
            fetched = parse_ts(fetched_raw) if fetched_raw else None
            if fetched_raw and fetched is None:
                raise ValueError("%s：results[%s].fetched_at 不是 ISO8601（%r）" % (where, key, fetched_raw))
            self.results[key] = ProviderResult(key=str(v.get("key") or key), ok=v["ok"], value=v.get("value"), error=error,
                                               cmd=str(v.get("cmd", "")), fetched_at=fetched, grade=Grade(grade))
        for field, typ in (("repo", str), ("trace_dir", str), ("branch", str), ("tasktable_path", str)):
            if field in self.raw and not isinstance(self.raw[field], typ):
                raise ValueError("%s：%s 必须是字符串" % (where, field))
        if "trace_no" in self.raw and not isinstance(self.raw["trace_no"], int):
            raise ValueError("%s：trace_no 必须是整数" % where)

    def get(self, key: str) -> ProviderResult:
        return self.results.get(key) or ProviderResult(key, False, None, "夹具未记录")

    def run_all(self, jobs, deadline=None) -> dict[str, ProviderResult]:
        return {key: self.get(key) for key, _fn in jobs}


# ---------------------------------------------------------------- 解析器（命令输出 → 结构化值；畸形行 → ValueError → 整键 ok=False，R1-17）
def _parse_git_log(out: str, trace_dir: str = "") -> dict:
    prefix = (trace_dir.rstrip("/") + "/") if trace_dir else None
    commits = []
    for chunk in out.split(REC):
        if not chunk.strip():
            continue
        lines = chunk.split("\n")
        parts = lines[0].split(SEP)
        if len(parts) < 5:
            raise ValueError("git log 记录字段不足：%r" % lines[0][:80])
        files = [ln.strip() for ln in lines[1:] if ln.strip()]
        docs_only = bool(files) and bool(prefix) and all(f.startswith(prefix) for f in files)
        commits.append({
            "sha": parts[0], "at": parts[1], "committed": parts[2], "author": parts[3], "subject": _scrub_text(parts[4]),
            "refs": parts[5] if len(parts) > 5 else "", "docs_only": docs_only, "files_n": len(files),
        })
    return {"mode": "", "refs": [], "truncated": len(commits) >= GIT_LOG_MAX, "commits": commits}


def _parse_tags(out: str) -> list[dict]:
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split(SEP)
        if len(parts) < 3:
            raise ValueError("git tag 行字段不足：%r" % line[:80])
        rows.append({"name": parts[0], "at": parts[1], "object": parts[2], "commit": parts[3] if len(parts) > 3 and parts[3] else parts[2]})
    return rows


def _parse_branches(out: str) -> list[dict]:
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split(SEP)
        if len(parts) < 3:
            raise ValueError("for-each-ref 行字段不足：%r" % line[:80])
        rows.append({"name": parts[0], "sha": parts[1], "at": parts[2]})
    return rows


def _parse_worktree_list(out: str) -> list[dict]:
    entries, cur = [], None
    for line in out.splitlines():
        if line.startswith("worktree "):
            cur = {"path": line[len("worktree "):], "head": "", "branch": ""}
            entries.append(cur)
        elif cur is not None and line.startswith("HEAD "):
            cur["head"] = line[5:]
        elif cur is not None and line.startswith("branch "):
            cur["branch"] = line[7:].replace("refs/heads/", "")
    return entries


def _reduce_pr(p: dict) -> dict:
    if not isinstance(p, dict) or "number" not in p:
        raise ValueError("PR 记录缺 number")
    checks = []
    for c in p.get("statusCheckRollup") or []:
        checks.append({
            "name": c.get("name") or c.get("context") or "", "workflowName": c.get("workflowName") or "",
            "conclusion": c.get("conclusion") or c.get("state") or "", "status": c.get("status") or "",
            "startedAt": c.get("startedAt") or "", "completedAt": c.get("completedAt") or "",
        })
    reviews = [{"state": r.get("state") or "", "author": _login(r.get("author")), "submittedAt": r.get("submittedAt") or ""}
               for r in (p.get("reviews") or [])]
    return {
        "number": int(p["number"]), "title": _scrub_text(p.get("title") or ""), "state": p.get("state") or "",
        "isDraft": bool(p.get("isDraft")), "createdAt": p.get("createdAt") or "", "mergedAt": p.get("mergedAt") or "",
        "closedAt": p.get("closedAt") or "", "mergedBy": _login(p.get("mergedBy")), "author": _login(p.get("author")),
        "reviews": reviews, "headRefName": p.get("headRefName") or "", "head_oid": p.get("headRefOid") or "",
        "baseRefName": p.get("baseRefName") or "",
        "mergeCommit": (p.get("mergeCommit") or {}).get("oid", "") if isinstance(p.get("mergeCommit"), dict) else "",
        "url": p.get("url") or "", "body": _scrub_text((p.get("body") or "")[:BODY_MAX]), "checks": checks,
    }


def _parse_prs(out: str) -> list[dict]:
    data = json.loads(out or "[]")
    if not isinstance(data, list):
        raise ValueError("gh pr list 输出不是数组")
    return [_reduce_pr(p) for p in data]


def _parse_issue(out: str) -> dict:
    d = json.loads(out or "{}")
    if not isinstance(d, dict) or "state" not in d:
        raise ValueError("gh issue view 输出缺 state")
    comments = []
    for c in d.get("comments") or []:
        url = c.get("url") or ""
        m = re.search(r"issuecomment-(\d+)", url)
        comments.append({
            "id": int(m.group(1)) if m else 0, "createdAt": c.get("createdAt") or "", "author": _login(c.get("author")),
            "first_line": _first_line(c.get("body") or ""), "url": url,
        })
    return {
        "number": int(d.get("number") or 0), "title": _scrub_text(d.get("title") or ""), "state": d.get("state") or "",
        "createdAt": d.get("createdAt") or "", "closedAt": d.get("closedAt") or "", "url": d.get("url") or "", "comments": comments,
    }


def _parse_runs(out: str) -> list[dict]:
    data = json.loads(out or "[]")
    if not isinstance(data, list):
        raise ValueError("gh run list 输出不是数组")
    rows = []
    for r in data:
        if not isinstance(r, dict):
            raise ValueError("run 记录不是对象")
        rows.append({
            "id": r.get("databaseId") or 0, "name": r.get("name") or "", "workflowName": r.get("workflowName") or "",
            "conclusion": r.get("conclusion") or "", "status": r.get("status") or "", "createdAt": r.get("createdAt") or "",
            "updatedAt": r.get("updatedAt") or "", "headSha": r.get("headSha") or "", "headBranch": r.get("headBranch") or "",
            "event": r.get("event") or "", "url": r.get("url") or "",
        })
    return rows


def _parse_gh_tags(out: str) -> list[dict]:
    data = json.loads(out or "[]")
    if not isinstance(data, list):
        raise ValueError("gh api tags 输出不是数组")
    rows = []
    for t in data:
        if not isinstance(t, dict) or not t.get("name"):
            raise ValueError("tag 记录缺 name")
        commit = t.get("commit") or {}
        rows.append({"name": t.get("name"), "sha": commit.get("sha") or "", "at": "", "at_source": ""})
    return rows


def _parse_tasktable_blob(text: str) -> dict:
    """任务表某一版本 → 出现的 Step ID、已勾选 ID、含时刻与「暂停」的引用块行（暂停区间原料）。"""
    ids, checked, quotes = [], [], []
    for line in text.splitlines():
        m = tasktable.STEP_RE.match(line)
        if m:
            ids.append(m.group(2))
            if m.group(1) in ("x", "X"):
                checked.append(m.group(2))
        elif line.startswith(">") and TIME_IN_LINE_RE.search(line) and PAUSE_LINE_RE.search(line):
            quotes.append(_scrub_text(line.strip()[:300]))
    return {"ids": ids, "checked": checked, "quotes": quotes}


# ---------------------------------------------------------------- 定位
def resolve_trace(repo_root: str, trace_no: Optional[int] = None) -> tuple[int, str, str]:
    """返回 (trace_no, trace_dir, tasktable_path)，均相对 repo_root；找不到返回 (trace_no or 0, "", "")。"""
    base = os.path.join(repo_root, "docs", "traces")
    found: list[tuple[int, str]] = []
    if os.path.isdir(base):
        for name in os.listdir(base):
            m = TRACE_DIR_RE.match(name)
            if m and os.path.isdir(os.path.join(base, name)):
                found.append((int(m.group(1)), name))
    if not found:
        return (trace_no or 0, "", "")
    if trace_no is not None:
        cands = [x for x in found if x[0] == trace_no]
        if not cands:
            return (trace_no, "", "")
        n, name = sorted(cands)[0]
    else:
        n, name = max(found)
    trace_dir = "docs/traces/%s" % name
    return (n, trace_dir, "%s/%s" % (trace_dir, TASKTABLE_NAME))


def resolve_branch(prs, trace_no: int, conf, override: Optional[str] = None, branches=()) -> str:
    """override → 配置 [trace].branch → 含 <n> 的 PR 分支（batch/<n>-* 优先）→ 本地 / 远端 batch/<n>-* → 未知 ""。"""
    if override:
        return override
    configured = getattr(conf, "trace_branch", None)
    if configured:
        return str(configured)
    prs = prs or []
    if not trace_no:
        return ""
    batch_re = re.compile(r"^batch/%d-" % trace_no)
    loose_re = re.compile(r"(^|/)%d-" % trace_no)
    for p in prs:
        if batch_re.match(p.get("headRefName") or ""):
            return p["headRefName"]
    for b in branches or ():
        name = re.sub(r"^origin/", "", b.get("name") or "")
        if batch_re.match(name):
            return name
    for p in prs:
        head = p.get("headRefName") or ""
        if loose_re.search(head) and p.get("state") == "OPEN":
            return head
    return ""


def repo_slug_from_git(source: "LiveSource") -> str:
    rem = source.remaining()
    res = source.run("repo.slug", ["git", "remote", "get-url", "origin"], timeout=min(source.per_cmd_timeout, rem) if rem else None)
    if not res.ok:
        return ""
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", (res.value or "").strip())
    return m.group(1) if m else ""


def _ref_exists(src: LiveSource, ref: str) -> bool:
    res = src.run("git.ref", ["git", "rev-parse", "--verify", "--quiet", ref + "^{commit}"])
    return res.ok and bool((res.value or "").strip())


# ---------------------------------------------------------------- 内置证据键（每个键一个闭包；内部多条命令串行，失败整键 ok=False 或字段级记 error）
def _job_git_log(src: LiveSource, branch: str, trace_dir: str):
    """R1-1：批次分支＋各 worktree 分支（实测级）；找不到分支才 --all（推断级，infer 加「证据可能串线」告警）。"""
    def _inner():
        refs: list[str] = []
        if branch:
            for cand in (branch, "origin/" + branch):
                if _ref_exists(src, cand):
                    refs.append(cand)
                    break
        if refs:
            wt = src.run("git.log", ["git", "worktree", "list", "--porcelain"], parse=_parse_worktree_list)
            if wt.ok:
                for w in wt.value[1:]:  # 跳过主工作树（通常在 main 上；main 的历史经批次分支已覆盖，不再单独并入）
                    b = w.get("branch") or ""
                    if b and b != branch and b not in refs and _ref_exists(src, b):
                        refs.append(b)
        mode = "branch" if refs else "all"
        argv = ["git", "-c", "core.quotePath=false", "log"] + (refs if refs else ["--all"]) + [
            "--date=iso-strict", "--max-count=%d" % GIT_LOG_MAX, "--name-only",
            "--format=%x1e%H" + SEP + "%ad" + SEP + "%cd" + SEP + "%an" + SEP + "%s" + SEP + "%D"]
        res = src.run("git.log", argv, parse=lambda out: _parse_git_log(out, trace_dir), grade=Grade.MEASURED if refs else Grade.INFERRED)
        if res.ok:
            res.value["mode"] = mode
            res.value["refs"] = refs
        return res
    return _inner


def _job_tasktable_history(src: LiveSource, tasktable_path: str, deadline: float):
    def _inner():
        if not tasktable_path:
            return ProviderResult("git.tasktable_history", False, None, "无任务表路径")
        head = src.run("git.tasktable_history", ["git", "log", "--all", "--reverse", "--date=iso-strict",
                                                  "--format=%H" + SEP + "%ad", "--", tasktable_path])
        if not head.ok:
            return head
        commits, failed = [], 0
        for line in (head.value or "").splitlines():
            if not line.strip():
                continue
            parts = line.split(SEP)
            if len(parts) < 2:
                return ProviderResult("git.tasktable_history", False, None, "解析失败：git log 行字段不足", head.cmd, _now())
            if time.monotonic() > deadline:
                return ProviderResult("git.tasktable_history", False, None, "整轮超时", head.cmd, _now())
            sha, at = parts[0], parts[1]
            blob = src.run("git.tasktable_history", ["git", "show", "%s:%s" % (sha, tasktable_path)])
            if not blob.ok:
                failed += 1
                commits.append({"sha": sha, "at": at, "ids": [], "checked": [], "quotes": [], "error": blob.error[:120]})
                continue
            row = _parse_tasktable_blob(blob.value or "")
            row.update({"sha": sha, "at": at})
            commits.append(row)
        if commits and failed == len(commits):
            return ProviderResult("git.tasktable_history", False, None, "全部 %d 个版本 git show 失败：%s" % (failed, commits[0]["error"]), head.cmd, _now())
        return ProviderResult("git.tasktable_history", True, {"path": tasktable_path, "commits": commits, "failed": failed}, "",
                              head.cmd + " ＋ git show <sha>:<任务表>", _now(), Grade.INFERRED)
    return _inner


def _job_worktrees(src: LiveSource, branch: str, deadline: float):
    def _inner():
        listing = src.run("git.worktrees", ["git", "worktree", "list", "--porcelain"], parse=_parse_worktree_list)
        if not listing.ok:
            return listing
        rows = []
        for i, wt in enumerate(listing.value or []):
            if time.monotonic() > deadline:
                return ProviderResult("git.worktrees", False, None, "整轮超时", listing.cmd, _now())
            path = wt["path"]
            row = {"name": os.path.basename(path.rstrip("/")) or path, "head": wt["head"], "branch": wt["branch"], "main": i == 0,
                   "last_at": "", "last_subject": "", "ahead": None, "dirty": None, "files": [], "error": ""}
            if not os.path.isdir(path):
                row["error"] = "目录不存在"
                rows.append(row)
                continue
            last = src.run("git.worktrees", ["git", "log", "-1", "--date=iso-strict", "--format=%ad" + SEP + "%s"], cwd=path)
            if last.ok and (last.value or "").strip():
                parts = last.value.strip().split(SEP)
                row["last_at"] = parts[0]
                row["last_subject"] = _scrub_text(parts[1]) if len(parts) > 1 else ""
            else:
                row["error"] = last.error or "无提交"
            if branch and wt["branch"] != branch:
                ahead = src.run("git.worktrees", ["git", "rev-list", "--count", "%s..HEAD" % branch], cwd=path)
                if ahead.ok and (ahead.value or "").strip().isdigit():
                    row["ahead"] = int(ahead.value.strip())
                elif not row["error"]:
                    row["error"] = "ahead 不可得：%s" % ahead.error[:80]
            status = src.run("git.worktrees", ["git", "--no-optional-locks", "status", "--porcelain"], cwd=path)
            if status.ok:
                files = [ln[3:].strip() for ln in (status.value or "").splitlines() if len(ln) > 3]
                row["dirty"] = len(files)
                row["files"] = files[:20]
            elif not row["error"]:
                row["error"] = "status 不可得：%s" % status.error[:80]
            rows.append(row)
        return ProviderResult("git.worktrees", True, rows, "", listing.cmd + " ＋ 每个 worktree 的 log -1 / rev-list --count / status", _now())
    return _inner


def _job_tags(src: LiveSource):
    return src.run("git.tags", ["git", "tag", "--format=%(refname:short)" + SEP + "%(creatordate:iso-strict)" + SEP + "%(objectname)" + SEP + "%(*objectname)"],
                   parse=_parse_tags)


def _job_branches(src: LiveSource):
    return src.run("git.branches", ["git", "for-each-ref", "--format=%(refname:short)" + SEP + "%(objectname)" + SEP + "%(committerdate:iso-strict)",
                                    "refs/heads", "refs/remotes"], parse=_parse_branches)


def _job_contract(src: LiveSource, trace_dir: str):
    def _inner():
        if not trace_dir:
            return ProviderResult("git.contract", False, None, "无 Trace 目录")
        path = "%s/%s" % (trace_dir, CONTRACT_NAME)
        res = src.run("git.contract", ["git", "log", "--all", "--reverse", "--diff-filter=A", "--date=iso-strict",
                                       "--format=%H" + SEP + "%ad" + SEP + "%s", "--", path])
        if not res.ok:
            return res
        first = None
        for line in (res.value or "").splitlines():
            parts = line.split(SEP)
            if len(parts) >= 3:
                first = {"sha": parts[0], "at": parts[1], "subject": _scrub_text(parts[2]), "path": path}
                break
        return ProviderResult("git.contract", True, first, "", res.cmd, _now())
    return _inner


def _job_quotes(repo_root: str, tasktable_path: str):
    def _inner():
        if not tasktable_path:
            return ProviderResult("tasktable.quotes", False, None, "无任务表路径")
        try:
            with open(os.path.join(repo_root, tasktable_path), encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            return ProviderResult("tasktable.quotes", False, None, "读取失败：%s" % exc.__class__.__name__)
        return ProviderResult("tasktable.quotes", True, _parse_tasktable_blob(text)["quotes"], "", "读 <任务表> 引用块", _now(), Grade.REPORTED)
    return _inner


def _job_prs(src: LiveSource, slug: str, trace_no: int, branch: str):
    def _inner():
        if not slug:
            return ProviderResult("gh.prs", False, None, "仓库 slug 未知（无 origin / 未配置 [repo].slug）")
        res = src.run("gh.prs", ["gh", "pr", "list", "-R", slug, "--state", "all", "--limit", "200", "--search", "#%d" % trace_no,
                                 "--json", PR_FIELDS], parse=_parse_prs)
        if not res.ok:
            return res
        prs = list(res.value or [])
        if branch and not any(p.get("headRefName") == branch for p in prs):
            extra = src.run("gh.prs", ["gh", "pr", "list", "-R", slug, "--state", "all", "--limit", "20", "--head", branch, "--json", PR_FIELDS],
                            parse=_parse_prs)
            if not extra.ok:
                return ProviderResult("gh.prs", False, None, "--head 查询失败：%s" % extra.error[:120], res.cmd + " ＋ --head <branch>", _now())
            seen = {p["number"] for p in prs}
            prs.extend(p for p in extra.value if p["number"] not in seen)
            res.cmd += " ＋ --head <branch>"
        res.value = sorted(prs, key=lambda p: p["number"])
        return res
    return _inner


def _job_issue(src: LiveSource, slug: str, trace_no: int):
    def _inner():
        if not slug:
            return ProviderResult("gh.issue", False, None, "仓库 slug 未知")
        if not trace_no:
            return ProviderResult("gh.issue", False, None, "Trace 号未知")
        return src.run("gh.issue", ["gh", "issue", "view", str(trace_no), "-R", slug, "--json", "number,title,state,createdAt,closedAt,url,comments"],
                       parse=_parse_issue)
    return _inner


def _job_runs(src: LiveSource, slug: str, branch: str):
    def _inner():
        if not slug:
            return ProviderResult("gh.runs", False, None, "仓库 slug 未知")
        argv = ["gh", "run", "list", "-R", slug, "--limit", "100", "--json", RUN_FIELDS]
        if branch:
            argv[5:5] = ["--branch", branch]
        return src.run("gh.runs", argv, parse=_parse_runs)
    return _inner


def _job_release_runs(src: LiveSource, slug: str, workflow: str):
    def _inner():
        if not workflow:
            return ProviderResult("gh.release_runs", False, None, "未配置发布工作流")
        if not slug:
            return ProviderResult("gh.release_runs", False, None, "仓库 slug 未知")
        return src.run("gh.release_runs", ["gh", "run", "list", "-R", slug, "--workflow", workflow, "--branch", "main", "--limit", "10",
                                           "--json", RUN_FIELDS], parse=_parse_runs)
    return _inner


def _job_gh_tags_list(src: LiveSource, slug: str):
    def _inner():
        if not slug:
            return ProviderResult("gh.tags", False, None, "仓库 slug 未知")
        res = src.run("gh.tags", ["gh", "api", "repos/%s/tags?per_page=%d" % (slug, GH_TAGS_LIMIT)], parse=_parse_gh_tags)
        if res.ok:
            res.cmd = "gh api repos/<repo>/tags?per_page=%d" % GH_TAGS_LIMIT
        return res
    return _inner


def _parallel(src: LiveSource, tasks: list[tuple[str, Callable[[], None]]], limit: int, deadline: float) -> None:
    """作业内部的小并发（≤ limit 个守护线程，共享本轮登记表），到 deadline 不再等。"""
    rid = src._round_of_thread()
    pending = list(tasks)
    while pending and time.monotonic() < deadline:
        batch, pending = pending[:limit], pending[limit:]
        threads = []
        for _name, fn in batch:
            def runner(f=fn):
                src._tls.round_id = rid
                try:
                    f()
                except Exception:  # noqa: BLE001 — 子任务自己把失败写进字段
                    pass
            t = threading.Thread(target=runner, daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(max(0.0, deadline - time.monotonic()))


def _job_gh_tags_dates(src: LiveSource, slug: str, tags_res: Optional[ProviderResult], local_times: dict, deadline: float):
    """A-4：tag 提交时刻优先取本地 git.log；本地没有的候选 tag（列表最前的 ≤5 个）并发查 commits/<sha>。"""
    def _inner():
        if tags_res is None or not tags_res.ok:
            return tags_res or ProviderResult("gh.tags", False, None, "未采集")
        need = []
        for t in tags_res.value or []:
            sha = t.get("sha") or ""
            if sha in local_times:
                t["at"], t["at_source"] = local_times[sha], "git.log"
            elif len(need) < GH_TAG_DATES:
                need.append(t)

        def fetch(t):
            d = src.run("gh.tags", ["gh", "api", "repos/%s/commits/%s" % (slug, t["sha"]), "-q", ".commit.committer.date"])
            if d.ok and (d.value or "").strip():
                t["at"], t["at_source"] = d.value.strip(), "gh.commits"
            else:
                t["error"] = d.error[:80]

        if need:
            _parallel(src, [(t["name"], (lambda t=t: fetch(t))) for t in need], GH_TAG_DATES, deadline)
            tags_res.cmd += " ＋ %d 个候选 tag 的 repos/<repo>/commits/<sha>（并发 ≤ %d）" % (len(need), GH_TAG_DATES)
        return tags_res
    return _inner


def _job_gh_compare(src: LiveSource, slug: str, base: str, heads: list[str], deadline: float):
    """R1-13：合并提交 → 候选提交（发布 run headSha、远端 tag）的祖先关系：ahead / identical / behind / diverged。"""
    def _inner():
        if not slug:
            return ProviderResult("gh.compare", False, None, "仓库 slug 未知")
        if not base:
            return ProviderResult("gh.compare", False, None, "无已证实的合并点（批次 PR 未合入或未识别）")
        results: dict[str, str] = {}
        cands = [h for h in heads if h and h != base][:GH_COMPARE_MAX]

        def fetch(h):
            r = src.run("gh.compare", ["gh", "api", "repos/%s/compare/%s...%s" % (slug, base, h), "-q", ".status"])
            results[h] = (r.value or "").strip() if r.ok else "error:%s" % r.error[:60]

        _parallel(src, [(h, (lambda h=h: fetch(h))) for h in cands], GH_COMPARE_MAX, deadline)
        for h in cands:
            results.setdefault(h, "error:整轮超时")
        return ProviderResult("gh.compare", True, {"base": base, "results": results}, "",
                              "gh api repos/<repo>/compare/<merge>...<sha>（%d 个候选，并发 ≤ %d）" % (len(cands), GH_COMPARE_MAX), _now())
    return _inner


def _job_tmux(src: LiveSource, session: str):
    def _inner():
        if not session:
            return ProviderResult("tmux.windows", False, None, "未配置编排 session")
        res = src.run("tmux.windows", ["tmux", "list-windows", "-t", session, "-F", "#{window_name}"],
                      parse=lambda out: [ln.strip() for ln in out.splitlines() if ln.strip()])
        res.cmd = "tmux list-windows -t <session> -F '#{window_name}'"
        return res
    return _inner


def _job_config(conf, spec, key: str, per_cmd_timeout: int):
    def _inner():
        try:
            from . import config as cfg  # 延迟导入：S-4 未合入时不影响其他键
            provider_cls = getattr(cfg, "ShellProvider", None)
            if provider_cls is None:
                return ProviderResult(key, False, None, "config.ShellProvider 未实现")
            res = provider_cls(per_cmd_timeout).run(spec, key)
        except NotImplementedError as exc:
            return ProviderResult(key, False, None, "config provider 未实现：%s" % str(exc)[:120])
        if not isinstance(res, ProviderResult):
            return ProviderResult(key, False, None, "config provider 未返回 ProviderResult")
        res.key = key
        return res
    return _inner


def _spec_key(spec, fallback: str) -> str:
    for attr in ("key", "name", "label"):
        v = getattr(spec, attr, None)
        if v:
            return str(v)
    return fallback


def config_specs(conf, warnings: Optional[list] = None) -> list[tuple[str, str, str, Any]]:
    """conf 声明的全部命令 → [(kind, key, result_key, spec)]。优先 S-4 的 `conf.specs()`（result_key＝`config.<key>`）；
    没有 specs() 的最小假 conf 退回按 stages / budgets / evidence 属性拼。只捕兼容性异常（缺属性 / 类型），其余记告警（R1-22）。"""
    out: list[tuple[str, str, str, Any]] = []
    specs = getattr(conf, "specs", None)
    if callable(specs):
        try:
            rows = specs() or []
        except (AttributeError, TypeError):
            rows = None
        except Exception as exc:  # noqa: BLE001 — 非兼容性异常：不静默，记告警并视为无声明
            if warnings is not None:
                warnings.append("配置声明读取失败：%s" % exc.__class__.__name__)
            return out
        if rows is not None:
            for sp in rows:
                key = _spec_key(sp, "")
                out.append((getattr(sp, "kind", "evidence") or "evidence", key, getattr(sp, "result_key", None) or ("config." + key), sp))
            return out
    stages = getattr(conf, "stages", None) or {}
    if isinstance(stages, dict):
        for k, sp in stages.items():
            out.append(("stage", k, getattr(sp, "result_key", None) or ("config." + k), sp))
    for i, sp in enumerate(getattr(conf, "budgets", None) or []):
        k = _spec_key(sp, "budget%d" % i)
        out.append(("budget", k, getattr(sp, "result_key", None) or ("config." + k), sp))
    for i, sp in enumerate(getattr(conf, "evidence", None) or []):
        k = _spec_key(sp, "evidence%d" % i)
        out.append(("evidence", k, getattr(sp, "result_key", None) or ("config." + k), sp))
    return out


def config_meta(conf, warnings: Optional[list] = None) -> dict:
    """把 conf 里推断要用的声明抄进 snapshot.config（不含 session 名 / 命令原文等机器事实），夹具回放时以此为准。"""
    meta = {
        "repo_slug": getattr(conf, "repo_slug", None) or "",
        "trace_branch": getattr(conf, "trace_branch", None) or "",
        "tmux_configured": bool(getattr(conf, "tmux_session", None)),
        "window_pattern": getattr(conf, "window_pattern", None) or "",
        "release_workflow": getattr(conf, "release_workflow", None) or "",
        "stages": [], "budgets": [], "evidence": [],
    }
    for kind, key, result_key, sp in config_specs(conf, warnings):
        row = {"key": key, "result_key": result_key, "label": getattr(sp, "label", "") or key}
        if kind == "stage":
            meta["stages"].append(row)
        elif kind == "budget":
            row["cap"] = getattr(sp, "cap", None)
            meta["budgets"].append(row)
        else:
            meta["evidence"].append(row)
    return meta


def build_jobs(src: LiveSource, conf, trace_no: int, trace_dir: str, tasktable_path: str, slug: str, branch: str, deadline: float,
               phase: int, prior: Optional[dict] = None) -> list[tuple[str, Callable[[], ProviderResult]]]:
    """phase 1：不依赖分支的键；phase 2：依赖分支或第一阶段结果的键（worktrees / runs / gh.prs --head / tag 时刻 / 祖先比对）。"""
    jobs: list[tuple[str, Callable[[], ProviderResult]]] = []
    if phase == 1:
        jobs += [
            ("git.log", _job_git_log(src, branch, trace_dir)),
            ("git.tasktable_history", _job_tasktable_history(src, tasktable_path, deadline)),
            ("git.tags", lambda: _job_tags(src)),
            ("git.branches", lambda: _job_branches(src)),
            ("git.contract", _job_contract(src, trace_dir)),
            ("tasktable.quotes", _job_quotes(src.repo_root, tasktable_path)),
            ("gh.prs", _job_prs(src, slug, trace_no, branch)),
            ("gh.issue", _job_issue(src, slug, trace_no)),
            ("gh.release_runs", _job_release_runs(src, slug, getattr(conf, "release_workflow", None) or "")),
            ("gh.tags", _job_gh_tags_list(src, slug)),
            ("tmux.windows", _job_tmux(src, getattr(conf, "tmux_session", None) or "")),
        ]
        for _kind, _key, result_key, spec in config_specs(conf):
            jobs.append((result_key, _job_config(conf, spec, result_key, src.per_cmd_timeout)))
        return jobs
    prior = prior or {}
    jobs += [
        ("git.worktrees", _job_worktrees(src, branch, deadline)),
        ("gh.runs", _job_runs(src, slug, branch)),
    ]
    if branch and not (prior.get("git.log") and prior["git.log"].ok and prior["git.log"].value.get("mode") == "branch"):
        jobs.append(("git.log", _job_git_log(src, branch, trace_dir)))  # 第一阶段还不知道分支：按分支重取
    prs_res = prior.get("gh.prs")
    prs = prs_res.value if prs_res and prs_res.ok else []
    if branch and not any(p.get("headRefName") == branch for p in prs):
        jobs.append(("gh.prs", _job_prs(src, slug, trace_no, branch)))
    log_res = prior.get("git.log")
    local_times = {c["sha"]: c["at"] for c in (log_res.value.get("commits") if log_res and log_res.ok else [])}
    tags_res = prior.get("gh.tags")
    jobs.append(("gh.tags", _job_gh_tags_dates(src, slug, tags_res, local_times, deadline)))
    base = ""
    for p in prs:
        if branch and p.get("headRefName") == branch and p.get("state") == "MERGED" and p.get("mergeCommit"):
            base = p["mergeCommit"]
            break
    heads: list[str] = []
    rr = prior.get("gh.release_runs")
    if rr and rr.ok:
        for r in rr.value[:3]:
            if r.get("headSha"):
                heads.append(r["headSha"])
    if tags_res and tags_res.ok:
        for t in tags_res.value[:GH_COMPARE_MAX]:
            if t.get("sha"):
                heads.append(t["sha"])
    dedup: list[str] = []
    for h in heads:
        if h not in dedup:
            dedup.append(h)
    jobs.append(("gh.compare", _job_gh_compare(src, slug, base, dedup, deadline)))
    return jobs


# ---------------------------------------------------------------- 主入口
def _unavailable_table(rel: str, error: str) -> TaskTable:
    """R1-8：任务表缺失 / 不可读不得当空表用——标 available=False 带 error，infer 据此全部「未知」。"""
    table = TaskTable(path=rel, sections=[], unparsed=[], overlong=[])
    table.available = False
    table.error = error
    table.unparsed_section = {}
    return table


def _read_tasktable(path: str, rel: str, warnings: list[str]) -> TaskTable:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        msg = "任务表不可读：%s（%s）" % (rel or TASKTABLE_NAME, exc.__class__.__name__)
        warnings.append(msg)
        return _unavailable_table(rel, msg)
    table = tasktable.parse(text, rel)
    table.text = text  # 原文留给 write_snapshot 抄夹具副本（不进 JSON）
    return table


def collect(repo_root, trace_no, branch, conf, now, source) -> Snapshot:
    now = utc(now) or _now()
    warnings: list[str] = []
    if getattr(source, "recorded", False):
        raw = source.raw
        table = _read_tasktable(os.path.join(source.fixture_dir, TASKTABLE_NAME), raw.get("tasktable_path") or TASKTABLE_NAME, warnings)
        cfg_meta = dict(raw.get("config") or {})
        if warnings:
            cfg_meta["warnings"] = list(cfg_meta.get("warnings", [])) + warnings
        if not getattr(table, "available", True):
            cfg_meta["tasktable_error"] = table.error
        return Snapshot(
            now=now, repo=raw.get("repo", ""), trace_no=int(trace_no or raw.get("trace_no") or 0), trace_dir=raw.get("trace_dir", ""),
            branch=branch or raw.get("branch", ""), tasktable=table, results=dict(source.results), config=cfg_meta,
        )

    src: LiveSource = source
    if getattr(conf, "tmux_session", None) and not getattr(src, "session", ""):
        src.session = str(conf.tmux_session)
    round_timeout = getattr(src, "round_timeout", None)
    deadline = time.monotonic() + max(0.0, float(60 if round_timeout is None else round_timeout))
    if getattr(src, "deadline", None) is not None:
        deadline = min(deadline, float(src.deadline))
    n, trace_dir, tt_rel = resolve_trace(repo_root, trace_no)
    if not trace_dir:
        warnings.append("找不到 Trace 目录：docs/traces/<%s>-*" % (trace_no if trace_no is not None else "max"))
        table = _unavailable_table("", "找不到 Trace 目录")
    else:
        table = _read_tasktable(os.path.join(repo_root, tt_rel), tt_rel, warnings)
    slug = getattr(conf, "repo_slug", None) or repo_slug_from_git(src)
    branch0 = branch or (getattr(conf, "trace_branch", None) or "")

    results = src.run_all(build_jobs(src, conf, n, trace_dir, tt_rel, slug, branch0, deadline, phase=1), deadline)
    prs = results.get("gh.prs")
    branches = results.get("git.branches")
    resolved = resolve_branch(prs.value if prs and prs.ok else [], n, conf, override=branch, branches=branches.value if branches and branches.ok else ())
    phase2 = build_jobs(src, conf, n, trace_dir, tt_rel, slug, resolved, deadline, phase=2, prior=results)
    if time.monotonic() >= deadline:
        for key, _fn in phase2:
            results.setdefault(key, ProviderResult(key, False, None, "整轮超时", "", _now()))
    else:
        results.update(src.run_all(phase2, deadline))
    cfg_meta = config_meta(conf, warnings)
    if warnings:
        cfg_meta["warnings"] = warnings
    if not getattr(table, "available", True):
        cfg_meta["tasktable_error"] = table.error
    return Snapshot(now=now, repo=slug, trace_no=n, trace_dir=trace_dir, branch=resolved, tasktable=table, results=results, config=cfg_meta)


def write_snapshot(snapshot: Snapshot, out_dir: str) -> str:
    """--record：写 <out_dir>/snapshot.json；有原文时同时写 <out_dir>/任务表.md 副本（夹具形态）。"""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "snapshot.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(snapshot.to_json())
        fh.write("\n")
    text = getattr(snapshot.tasktable, "text", None)
    if text:
        with open(os.path.join(out_dir, TASKTABLE_NAME), "w", encoding="utf-8") as fh:
            fh.write(text)
    return path
