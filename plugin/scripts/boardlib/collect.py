# -*- coding: utf-8 -*-
"""证据采集（接口约定 §6）。归属：S-2。只采集、不判断；失败 → ProviderResult.ok=False，不抛异常、不给默认值。

    class LiveSource(repo_root, per_cmd_timeout=25, round_timeout=60, env=None)
        run(key, argv_or_cmd, *, shell=False, timeout=None, grade=Grade.MEASURED, cwd=None, parse=None) -> ProviderResult
        （subprocess，stdin=DEVNULL，capture，超时 / 非零退出 / 命令不存在 / 解析失败都记 ok=False）
        run_all(jobs, deadline) -> dict[key, ProviderResult]   # 线程池并发；到 deadline 未完成的键 ok=False error="整轮超时"
    class RecordedSource(fixture_dir)          # 从 snapshot.json 回放；没有的键 ok=False error="夹具未记录"；.now＝夹具的 now
    collect(repo_root, trace_no, branch, conf, now, source) -> Snapshot
    write_snapshot(snapshot, out_dir)          # --record：写 <out_dir>/snapshot.json 与 任务表.md 副本
    resolve_trace(repo_root, trace_no=None) -> (trace_no, trace_dir, tasktable_path)   # 相对路径
    resolve_branch(prs, trace_no, conf, override=None, branches=()) -> str            # 见约定 §2；未知＝""

铁律：对目标仓库只读（不 fetch / pull / checkout / stash / add / commit；`git status` 加 --no-optional-locks）；
快照与错误文本里不落绝对路径、tmux session 名（替换为 <repo> / ~ / <session>）。
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from . import tasktable
from .model import Grade, ProviderResult, Snapshot, TaskTable, parse_ts, utc

SEP = "\x1f"
BUILTIN_KEYS = (
    "git.log", "git.tasktable_history", "git.worktrees", "git.tags", "git.branches", "git.contract",
    "tasktable.quotes", "gh.prs", "gh.issue", "gh.runs", "gh.release_runs", "gh.tags", "tmux.windows",
)
GH_TAGS_LIMIT = 30      # gh api repos/<slug>/tags 取前 30
GH_TAG_DATES = 5        # 前 5 个 tag 再查 commits/<sha> 取提交时刻（发布 tag 一定在最前）
GIT_LOG_MAX = 5000
PR_FIELDS = ("number,title,state,isDraft,createdAt,mergedAt,closedAt,mergedBy,author,reviews,headRefName,"
             "baseRefName,mergeCommit,url,body,statusCheckRollup")
RUN_FIELDS = "databaseId,name,workflowName,conclusion,status,createdAt,updatedAt,headSha,headBranch,event,url"
TRACE_DIR_RE = re.compile(r"^(\d+)-(.+)$")
TIME_IN_LINE_RE = re.compile(r"\d{1,2}:[0-9][0-9xX]")
PAUSE_LINE_RE = re.compile(r"暂停")
TASKTABLE_NAME = "任务表.md"
CONTRACT_NAME = "合同.md"
BODY_MAX = 3000


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
    return text


HOME_PATH_RE = re.compile("/" + "home" + r"/[^/\s`'\"]+/")  # 拼接写法：本文件自身不能出现该路径形态（禁词扫描）


def _scrub_text(text: str) -> str:
    """快照里的外部文本（PR 正文 / 评论首行 / 提交信息 / 引用块）把家目录路径形态换成 `~/`。"""
    return HOME_PATH_RE.sub("~/", text or "")


def _first_line(body: str) -> str:
    for line in (body or "").splitlines():
        if line.strip():
            return _scrub_text(line.strip()[:200])
    return ""


def _login(obj: Any) -> str:
    if isinstance(obj, dict):
        return str(obj.get("login") or obj.get("name") or "")
    return str(obj or "")


# ---------------------------------------------------------------- 证据源
class LiveSource:
    """真实采集：subprocess（stdin=DEVNULL、显式超时）＋线程池并发；整轮超时后杀掉在跑的子进程，不阻塞退出。"""

    recorded = False
    now: Optional[datetime] = None

    def __init__(self, repo_root: str, per_cmd_timeout: int = 25, round_timeout: int = 60, env: Optional[dict] = None,
                 max_workers: int = 8, session: str = ""):
        self.repo_root = os.path.abspath(repo_root)
        self.per_cmd_timeout = per_cmd_timeout
        self.round_timeout = round_timeout
        self.env = env
        self.max_workers = max_workers
        self.session = session
        self._procs: set = set()
        self._lock = threading.Lock()

    def describe(self, argv_or_cmd, shell: bool) -> str:
        text = argv_or_cmd if shell else " ".join(str(a) for a in argv_or_cmd)
        return _scrub(text, self.repo_root, self.session)

    def run(self, key: str, argv_or_cmd, *, shell: bool = False, timeout: Optional[int] = None,
            grade: Grade = Grade.MEASURED, cwd: Optional[str] = None, parse: Optional[Callable[[str], Any]] = None) -> ProviderResult:
        cmd_text = self.describe(argv_or_cmd, shell)
        argv = ["bash", "-c", argv_or_cmd] if shell else [str(a) for a in argv_or_cmd]
        limit = timeout or self.per_cmd_timeout
        try:
            proc = subprocess.Popen(argv, cwd=cwd or self.repo_root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, env=self.env)
        except (FileNotFoundError, PermissionError, NotADirectoryError) as exc:
            return ProviderResult(key, False, None, "命令不可用：%s（%s）" % (argv[0], exc.__class__.__name__), cmd_text, _now(), grade)
        except OSError as exc:
            return ProviderResult(key, False, None, "启动失败：%s" % _scrub(str(exc), self.repo_root, self.session), cmd_text, _now(), grade)
        with self._lock:
            self._procs.add(proc)
        try:
            try:
                out, err = proc.communicate(timeout=limit)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                return ProviderResult(key, False, None, "超时 %ds" % limit, cmd_text, _now(), grade)
        finally:
            with self._lock:
                self._procs.discard(proc)
        if proc.returncode != 0:
            msg = _scrub((err or out or "").strip().splitlines()[-1] if (err or out or "").strip() else "", self.repo_root, self.session)
            return ProviderResult(key, False, None, "退出码 %d：%s" % (proc.returncode, msg[:200]), cmd_text, _now(), grade)
        if parse is None:
            return ProviderResult(key, True, out, "", cmd_text, _now(), grade)
        try:
            value = parse(out)
        except Exception as exc:  # noqa: BLE001 — 解析失败也只记 ok=False
            return ProviderResult(key, False, None, "解析失败：%s" % _scrub(str(exc)[:200], self.repo_root, self.session), cmd_text, _now(), grade)
        return ProviderResult(key, True, value, "", cmd_text, _now(), grade)

    def kill_all(self) -> None:
        with self._lock:
            procs = list(self._procs)
        for proc in procs:
            try:
                proc.kill()
            except OSError:
                pass

    def run_all(self, jobs: list[tuple[str, Callable[[], ProviderResult]]], deadline: float) -> dict[str, ProviderResult]:
        results: dict[str, ProviderResult] = {}
        if not jobs:
            return results
        executor = cf.ThreadPoolExecutor(max_workers=self.max_workers)
        futures = {executor.submit(fn): key for key, fn in jobs}
        done, not_done = cf.wait(futures, timeout=max(0.0, deadline - time.monotonic()))
        for fut in done:
            key = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                res = ProviderResult(key, False, None, "内部错误：%s" % _scrub(str(exc)[:200], self.repo_root, self.session))
            if not isinstance(res, ProviderResult):
                res = ProviderResult(key, False, None, "内部错误：任务未返回 ProviderResult")
            results[key] = res
        for fut in not_done:
            results[futures[fut]] = ProviderResult(futures[fut], False, None, "整轮超时", "", _now())
        if not_done:
            self.kill_all()
        executor.shutdown(wait=False, cancel_futures=True)
        return results


class RecordedSource:
    """夹具回放：只读 <fixture_dir>/snapshot.json；零网络。"""

    recorded = True

    def __init__(self, fixture_dir: str):
        self.fixture_dir = fixture_dir
        path = os.path.join(fixture_dir, "snapshot.json")
        with open(path, encoding="utf-8") as fh:
            self.raw = json.load(fh)
        self.now = parse_ts(self.raw.get("now") or "") or _now()
        self.results: dict[str, ProviderResult] = {}
        for key, v in (self.raw.get("results") or {}).items():
            self.results[key] = ProviderResult(
                key=v.get("key", key), ok=bool(v.get("ok")), value=v.get("value"), error=v.get("error", ""),
                cmd=v.get("cmd", ""), fetched_at=parse_ts(v.get("fetched_at") or ""), grade=Grade(v.get("grade", "measured")),
            )

    def get(self, key: str) -> ProviderResult:
        return self.results.get(key) or ProviderResult(key, False, None, "夹具未记录")

    def run_all(self, jobs, deadline=None) -> dict[str, ProviderResult]:
        return {key: self.get(key) for key, _fn in jobs}


# ---------------------------------------------------------------- 解析器（命令输出 → 结构化值）
def _parse_git_log(out: str) -> list[dict]:
    rows = []
    for line in out.splitlines():
        parts = line.split(SEP)
        if len(parts) < 5:
            continue
        sha, cd, ad, author, subject = parts[0], parts[1], parts[2], parts[3], parts[4]
        refs = parts[5] if len(parts) > 5 else ""
        rows.append({"sha": sha, "at": cd, "authored": ad, "author": author, "subject": _scrub_text(subject), "refs": refs})
    return rows


def _parse_tags(out: str) -> list[dict]:
    rows = []
    for line in out.splitlines():
        parts = line.split(SEP)
        if len(parts) < 3:
            continue
        rows.append({"name": parts[0], "at": parts[1], "object": parts[2], "commit": parts[3] if len(parts) > 3 and parts[3] else parts[2]})
    return rows


def _parse_branches(out: str) -> list[dict]:
    rows = []
    for line in out.splitlines():
        parts = line.split(SEP)
        if len(parts) < 3:
            continue
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
        "number": int(p.get("number") or 0), "title": _scrub_text(p.get("title") or ""), "state": p.get("state") or "",
        "isDraft": bool(p.get("isDraft")), "createdAt": p.get("createdAt") or "", "mergedAt": p.get("mergedAt") or "",
        "closedAt": p.get("closedAt") or "", "mergedBy": _login(p.get("mergedBy")), "author": _login(p.get("author")),
        "reviews": reviews, "headRefName": p.get("headRefName") or "", "baseRefName": p.get("baseRefName") or "",
        "mergeCommit": (p.get("mergeCommit") or {}).get("oid", "") if isinstance(p.get("mergeCommit"), dict) else "",
        "url": p.get("url") or "", "body": _scrub_text((p.get("body") or "")[:BODY_MAX]), "checks": checks,
    }


def _parse_prs(out: str) -> list[dict]:
    return [_reduce_pr(p) for p in json.loads(out or "[]")]


def _parse_issue(out: str) -> dict:
    d = json.loads(out or "{}")
    comments = []
    for c in d.get("comments") or []:
        url = c.get("url") or ""
        m = re.search(r"issuecomment-(\d+)", url)
        comments.append({
            "id": int(m.group(1)) if m else 0, "createdAt": c.get("createdAt") or "", "author": _login(c.get("author")),
            "first_line": _first_line(c.get("body") or ""), "url": url,
        })
    return {
        "number": int(d.get("number") or 0), "title": d.get("title") or "", "state": d.get("state") or "",
        "createdAt": d.get("createdAt") or "", "closedAt": d.get("closedAt") or "", "url": d.get("url") or "", "comments": comments,
    }


def _parse_runs(out: str) -> list[dict]:
    rows = []
    for r in json.loads(out or "[]"):
        rows.append({
            "id": r.get("databaseId") or 0, "name": r.get("name") or "", "workflowName": r.get("workflowName") or "",
            "conclusion": r.get("conclusion") or "", "status": r.get("status") or "", "createdAt": r.get("createdAt") or "",
            "updatedAt": r.get("updatedAt") or "", "headSha": r.get("headSha") or "", "headBranch": r.get("headBranch") or "",
            "event": r.get("event") or "", "url": r.get("url") or "",
        })
    return rows


def _parse_gh_tags(out: str) -> list[dict]:
    rows = []
    for t in json.loads(out or "[]"):
        commit = t.get("commit") or {}
        rows.append({"name": t.get("name") or "", "sha": commit.get("sha") or "", "at": ""})
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
    res = source.run("repo.slug", ["git", "remote", "get-url", "origin"])
    if not res.ok:
        return ""
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", (res.value or "").strip())
    return m.group(1) if m else ""


# ---------------------------------------------------------------- 内置证据键（每个键一个闭包；内部多条命令串行，任一失败整键 ok=False 或部分记 error）
def _job_git_log(src: LiveSource):
    return src.run("git.log", ["git", "log", "--all", "--date=iso-strict", "--max-count=%d" % GIT_LOG_MAX,
                               "--format=%H" + SEP + "%cd" + SEP + "%ad" + SEP + "%an" + SEP + "%s" + SEP + "%D"], parse=_parse_git_log)


def _job_tasktable_history(src: LiveSource, tasktable_path: str, deadline: float):
    def _inner():
        if not tasktable_path:
            return ProviderResult("git.tasktable_history", False, None, "无任务表路径")
        head = src.run("git.tasktable_history", ["git", "log", "--all", "--reverse", "--date=iso-strict",
                                                  "--format=%H" + SEP + "%cd", "--", tasktable_path])
        if not head.ok:
            return head
        commits = []
        for line in (head.value or "").splitlines():
            parts = line.split(SEP)
            if len(parts) < 2:
                continue
            if time.monotonic() > deadline:
                return ProviderResult("git.tasktable_history", False, None, "整轮超时", head.cmd, _now())
            sha, at = parts[0], parts[1]
            blob = src.run("git.tasktable_history", ["git", "show", "%s:%s" % (sha, tasktable_path)])
            if not blob.ok:
                continue
            row = _parse_tasktable_blob(blob.value or "")
            row.update({"sha": sha, "at": at})
            commits.append(row)
        return ProviderResult("git.tasktable_history", True, {"path": tasktable_path, "commits": commits}, "",
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
            last = src.run("git.worktrees", ["git", "log", "-1", "--date=iso-strict", "--format=%cd" + SEP + "%s"], cwd=path)
            if last.ok and (last.value or "").strip():
                parts = last.value.strip().split(SEP)
                row["last_at"] = parts[0]
                row["last_subject"] = _scrub_text(parts[1]) if len(parts) > 1 else ""
            else:
                row["error"] = last.error
            if branch and wt["branch"] != branch:
                ahead = src.run("git.worktrees", ["git", "rev-list", "--count", "%s..HEAD" % branch], cwd=path)
                if ahead.ok and (ahead.value or "").strip().isdigit():
                    row["ahead"] = int(ahead.value.strip())
            status = src.run("git.worktrees", ["git", "--no-optional-locks", "status", "--porcelain"], cwd=path)
            if status.ok:
                files = [ln[3:].strip() for ln in (status.value or "").splitlines() if len(ln) > 3]
                row["dirty"] = len(files)
                row["files"] = files[:20]
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
                                       "--format=%H" + SEP + "%cd" + SEP + "%s", "--", path])
        if not res.ok:
            return res
        first = None
        for line in (res.value or "").splitlines():
            parts = line.split(SEP)
            if len(parts) >= 3:
                first = {"sha": parts[0], "at": parts[1], "subject": parts[2], "path": path}
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
            if extra.ok:
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


def _job_gh_tags(src: LiveSource, slug: str, deadline: float):
    """已发布 tag 的权威来源：远端 tag 列表（前 30）＋ 前 5 个 tag 的提交时刻（引擎不 fetch，本地 tag 可能滞后）。"""
    def _inner():
        if not slug:
            return ProviderResult("gh.tags", False, None, "仓库 slug 未知")
        res = src.run("gh.tags", ["gh", "api", "repos/%s/tags?per_page=%d" % (slug, GH_TAGS_LIMIT)], parse=_parse_gh_tags)
        if not res.ok:
            return res
        for t in (res.value or [])[:GH_TAG_DATES]:
            if time.monotonic() > deadline or not t["sha"]:
                break
            d = src.run("gh.tags", ["gh", "api", "repos/%s/commits/%s" % (slug, t["sha"]), "-q", ".commit.committer.date"])
            if d.ok and (d.value or "").strip():
                t["at"] = d.value.strip()
        res.cmd = "gh api repos/<repo>/tags?per_page=%d ＋ 前 %d 个 tag 的 repos/<repo>/commits/<sha>" % (GH_TAGS_LIMIT, GH_TAG_DATES)
        return res
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
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(key, False, None, "config provider 异常：%s" % _scrub(str(exc)[:200]))
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


def config_specs(conf) -> list[tuple[str, str, str, Any]]:
    """conf 声明的全部命令 → [(kind, key, result_key, spec)]。优先 S-4 的 `conf.specs()`（result_key＝`config.<key>`）；
    没有 specs() 的最小假 conf 退回按 stages / budgets / evidence 属性拼。"""
    out: list[tuple[str, str, str, Any]] = []
    specs = getattr(conf, "specs", None)
    if callable(specs):
        try:
            for sp in specs() or []:
                key = _spec_key(sp, "")
                out.append((getattr(sp, "kind", "evidence") or "evidence", key, getattr(sp, "result_key", None) or ("config." + key), sp))
            return out
        except Exception:  # noqa: BLE001 — 假 conf 的 specs 不可用时退回属性拼法
            out = []
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


def config_meta(conf) -> dict:
    """把 conf 里推断要用的声明抄进 snapshot.config（不含 session 名 / 命令原文等机器事实），夹具回放时以此为准。"""
    meta = {
        "repo_slug": getattr(conf, "repo_slug", None) or "",
        "trace_branch": getattr(conf, "trace_branch", None) or "",
        "tmux_configured": bool(getattr(conf, "tmux_session", None)),
        "window_pattern": getattr(conf, "window_pattern", None) or "",
        "release_workflow": getattr(conf, "release_workflow", None) or "",
        "stages": [], "budgets": [], "evidence": [],
    }
    for kind, key, result_key, sp in config_specs(conf):
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
               phase: int) -> list[tuple[str, Callable[[], ProviderResult]]]:
    """phase 1：不依赖分支的键；phase 2：依赖分支的键。"""
    jobs: list[tuple[str, Callable[[], ProviderResult]]] = []
    if phase == 1:
        jobs += [
            ("git.log", lambda: _job_git_log(src)),
            ("git.tasktable_history", _job_tasktable_history(src, tasktable_path, deadline)),
            ("git.tags", lambda: _job_tags(src)),
            ("git.branches", lambda: _job_branches(src)),
            ("git.contract", _job_contract(src, trace_dir)),
            ("tasktable.quotes", _job_quotes(src.repo_root, tasktable_path)),
            ("gh.prs", _job_prs(src, slug, trace_no, branch)),
            ("gh.issue", _job_issue(src, slug, trace_no)),
            ("gh.release_runs", _job_release_runs(src, slug, getattr(conf, "release_workflow", None) or "")),
            ("gh.tags", _job_gh_tags(src, slug, deadline)),
            ("tmux.windows", _job_tmux(src, getattr(conf, "tmux_session", None) or "")),
        ]
        for _kind, _key, result_key, spec in config_specs(conf):
            jobs.append((result_key, _job_config(conf, spec, result_key, src.per_cmd_timeout)))
    else:
        jobs += [
            ("git.worktrees", _job_worktrees(src, branch, deadline)),
            ("gh.runs", _job_runs(src, slug, branch)),
        ]
        if branch:
            jobs.append(("gh.prs", _job_prs(src, slug, trace_no, branch)))
    return jobs


# ---------------------------------------------------------------- 主入口
def _empty_table(path: str) -> TaskTable:
    return TaskTable(path=path, sections=[], unparsed=[], overlong=[])


def _read_tasktable(path: str, rel: str, warnings: list[str]) -> TaskTable:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        warnings.append("任务表不可读：%s（%s）" % (rel or TASKTABLE_NAME, exc.__class__.__name__))
        return _empty_table(rel)
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
        return Snapshot(
            now=now, repo=raw.get("repo", ""), trace_no=int(trace_no or raw.get("trace_no") or 0), trace_dir=raw.get("trace_dir", ""),
            branch=branch or raw.get("branch", ""), tasktable=table, results=dict(source.results), config=cfg_meta,
        )

    src: LiveSource = source
    if getattr(conf, "tmux_session", None) and not getattr(src, "session", ""):
        src.session = str(conf.tmux_session)
    round_timeout = getattr(src, "round_timeout", None)
    deadline = time.monotonic() + max(0.0, float(60 if round_timeout is None else round_timeout))
    n, trace_dir, tt_rel = resolve_trace(repo_root, trace_no)
    if not trace_dir:
        warnings.append("找不到 Trace 目录：docs/traces/<%s>-*" % (trace_no if trace_no is not None else "max"))
    table = _read_tasktable(os.path.join(repo_root, tt_rel), tt_rel, warnings) if tt_rel else _empty_table("")
    slug = getattr(conf, "repo_slug", None) or repo_slug_from_git(src)
    branch0 = branch or (getattr(conf, "trace_branch", None) or "")

    results = src.run_all(build_jobs(src, conf, n, trace_dir, tt_rel, slug, branch0, deadline, phase=1), deadline)
    prs = results.get("gh.prs")
    branches = results.get("git.branches")
    resolved = resolve_branch(prs.value if prs and prs.ok else [], n, conf, override=branch, branches=branches.value if branches and branches.ok else ())
    phase2 = build_jobs(src, conf, n, trace_dir, tt_rel, slug, resolved, deadline, phase=2)
    if time.monotonic() >= deadline:
        for key, _fn in phase2:
            results.setdefault(key, ProviderResult(key, False, None, "整轮超时", "", _now()))
    else:
        results.update(src.run_all(phase2, deadline))
    cfg_meta = config_meta(conf)
    if warnings:
        cfg_meta["warnings"] = warnings
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
