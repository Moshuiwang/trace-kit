#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合成夹具生成器（S-5；接口约定 §10）。程序化产出每个案例的 `任务表.md` ＋ `snapshot.json` ＋ `README.md`。

    python3 -B tests/board/make_fixtures.py              # 只重写合成案例的任务表 / 快照 / README
    python3 -B tests/board/make_fixtures.py --expected   # 再调 board.py 重生成三份 expected-*.txt（含 trace1-replay）

所有假数据确定性：时间戳写死、sha / PR 号 / 评论号写死，不读环境、不联网、不取当前时刻。
`trace1-replay` 是本仓 Trace #1 的真实录制（`board.py --record`），不由本文件生成，只在 --expected 时一并重画。
案例清单与「人工核对断言」见 CASES / CHECKS；run_fixtures.py 直接用 CHECKS 做逐项子串断言，
所以 expected 即使被盲目重生成，断言也不会跟着一起变绿。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FIXTURES = os.path.join(HERE, "fixtures")
BOARD = os.path.join(ROOT, "plugin", "scripts", "board.py")
REPO = "example/demo"
DAY = "2026-09-03"
WIDTH, HEIGHT = 150, 52


def T(hhmm: str) -> str:
    """`03:28` / `03:28:40` → 当天 UTC 的 ISO8601。"""
    return "%sT%s+00:00" % (DAY, hhmm if len(hhmm) == 8 else hhmm + ":00")


def sha(seed: str) -> str:
    """确定性假 sha：种子重复到 40 位十六进制。"""
    body = (seed * 40)[:40]
    return "".join(c if c in "0123456789abcdef" else "%x" % (ord(c) % 16) for c in body)





CAND = sha("c3")     # K-1 冻结的候选 SHA（任务表指针与分支 HEAD 都用它）
TIP = sha("d4")      # F3：审核出结论后分支又往前走的新 HEAD


# ---------------------------------------------------------------- 结果构造
def commit(s, at, subject, author="agent-a", refs="", docs_only=False):
    return {"sha": s, "at": at, "committed": at, "author": author, "subject": subject, "refs": refs, "docs_only": docs_only, "files_n": 1}


def gitlog(commits, branch):
    """git.log 值形态（F-1 R1-1）：批次分支模式，不触顶。"""
    return {"mode": "branch", "refs": [branch], "truncated": False, "commits": list(commits)}


def pr(number, title, created, merged="", author="agent-a", merged_by="", head="", merge_commit="",
       body="", reviews=(), checks=(), state="OPEN", draft=False, closed="", head_oid=""):
    return {
        "number": number, "title": title, "state": "MERGED" if merged else state, "isDraft": draft,
        "createdAt": created, "mergedAt": merged, "closedAt": closed or merged, "mergedBy": merged_by,
        "author": author, "reviews": [{"state": st, "author": who, "submittedAt": when} for st, who, when in reviews],
        "headRefName": head, "head_oid": head_oid, "baseRefName": "main", "mergeCommit": merge_commit,
        "url": "https://github.com/%s/pull/%d" % (REPO, number), "body": body,
        "checks": [{"name": n, "workflowName": n, "conclusion": c, "status": "COMPLETED", "startedAt": "", "completedAt": ""} for n, c in checks],
    }


def issue(number, created, state="OPEN", closed="", comments=()):
    rows = []
    for cid, at, first in comments:
        rows.append({"id": cid, "createdAt": at, "author": "agent-a", "first_line": first,
                     "url": "https://github.com/%s/issues/%d#issuecomment-%d" % (REPO, number, cid)})
    return {"number": number, "title": "[tracking] 示例 Trace", "state": state, "createdAt": created,
            "closedAt": closed, "url": "https://github.com/%s/issues/%d" % (REPO, number), "comments": rows}


def run(rid, at, conclusion, head_sha, branch, name="selfcheck"):
    return {"id": rid, "name": name, "workflowName": name, "conclusion": conclusion, "status": "completed",
            "createdAt": at, "updatedAt": at, "headSha": head_sha, "headBranch": branch, "event": "push",
            "url": "https://github.com/%s/actions/runs/%d" % (REPO, rid)}


def worktree(name, branch, at, subject, head="", main=False):
    return {"name": name, "head": head or sha(name[0] if name else "w"), "branch": branch, "main": main,
            "last_at": at, "last_subject": subject, "ahead": 0, "dirty": 0, "files": [], "error": ""}


def history(rows, path, ids):
    """rows: [(at, sha, [该版本已勾选的 ID])]；ids ＝ 任务表全部编号。"""
    return {"path": path, "commits": [{"ids": list(ids), "checked": list(ck), "quotes": [], "sha": s, "at": at}
                                      for at, s, ck in rows]}


DEFAULT_CONFIG = {"repo_slug": REPO, "trace_branch": "", "tmux_configured": False, "window_pattern": "",
                  "release_workflow": "", "stages": [], "budgets": [], "evidence": []}


def snapshot(trace_no, dirname, branch, now, results, config=None):
    trace_dir = "docs/traces/%s" % dirname
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(config or {})
    return {"now": now, "repo": REPO, "trace_no": trace_no, "trace_dir": trace_dir, "branch": branch,
            "tasktable_path": trace_dir + "/任务表.md", "results": results, "config": cfg}


# ---------------------------------------------------------------- 任务表
HEAD = "# 任务表（示例项目；合成夹具，全部数据为假）\n\n"


def table(sections) -> str:
    out = [HEAD]
    for title, rows in sections:
        out.append("## %s\n\n" % title)
        for row in rows:
            out.append(row + "\n")
        out.append("\n")
    return "".join(out).rstrip("\n") + "\n"


def simple_table(s0_ptr: bool, s1_done: bool, s2_done: bool) -> str:
    s0 = "- [x] S-0 合同与授权终点%s [t:contract est:15m]" % ("——PR #10 合入" if s0_ptr else "")
    s1 = "- [%s] S-1 实现取数与解析%s [t:impl est:30m]" % ("x" if s1_done else " ", "——PR #11 合入" if s1_done else "")
    s2 = "- [%s] S-2 补边界与快照测试 [t:impl est:45m]" % ("x" if s2_done else " ")
    s3 = "- [ ] S-3 独立审核 [t:review est:20m]"
    return table([("块 A 合同", [s0]), ("Wave 1 实施", [s1]), ("Wave 2 实施", [s2]), ("Wave 3 审核", [s3])])


def complex_table(*, contract_section: bool, contract_ptr: bool, a1: bool, a2: bool, k1: bool, r1: bool) -> str:
    def box(flag):
        return "x" if flag else " "

    wave1 = ["- [%s] S-A1 打包引擎目录%s [t:impl est:90m own:impl_a]" % (box(a1), "——PR #21 合入" if a1 else ""),
             "- [%s] S-A2 打包模板分层 CI%s [t:impl est:30m own:impl_b]" % (box(a2), "——PR #22 合入" if a2 else "")]
    wave2 = ["- [%s] K-1 候选冻结（`%s`） [t:gate est:10m needs:S-A1,S-A2]" % (box(k1), CAND[:12]),
             "- [%s] R-1 独立审核结论（`%s`） [t:review est:60m needs:K-1]" % (box(r1), CAND[:12]),
             "- [ ] F-1 统一修复包 [t:impl est:30m needs:R-1]",
             "- [ ] R-2 定向复核 [t:review est:15m needs:F-1]"]
    wave3 = ["- [ ] G-1 完整门禁 [t:gate est:8m needs:R-2]",
             "- [ ] H-1 产品负责人批准 [t:human needs:G-1]",
             "- [ ] D-1 发布 tag [t:deploy est:10m needs:H-1]"]
    sections = [("Wave 1 实施", wave1), ("Wave 2 审核链", wave2), ("Wave 3 门禁与发布", wave3)]
    if contract_section:
        s0 = "- [x] S-0 合同与授权终点%s [t:contract est:15m]" % ("——PR #20 合入" if contract_ptr else "")
        sections.insert(0, ("块 A 合同", [s0]))
    return table(sections)


# ---------------------------------------------------------------- 结果表
def ok_(key, value, grade="measured", cmd=""):
    return {"key": key, "ok": True, "value": value, "error": "", "cmd": cmd, "fetched_at": "", "grade": grade}


def bad_(key, error, grade="measured"):
    return {"key": key, "ok": False, "value": None, "error": error, "cmd": "", "fetched_at": "", "grade": grade}


NO_WORKFLOW = "未配置发布工作流"
NO_SESSION = "未配置编排 session"
NO_MERGE_POINT = "无已证实的合并点（批次 PR 未合入或未识别）"
GH_GONE = "命令不可用：gh（FileNotFoundError）"


def finish(rows, now):
    out = {}
    for row in rows:
        row = dict(row)
        row["fetched_at"] = now
        out[row["key"]] = row
    return out


def base_rows(*, log, hist, prs, iss, runs, tags=(), gh_tags=(), branches=(), worktrees=(), contract=None,
              release_runs=None, quotes=(), branch="", compare=None):
    rows = [
        ok_("git.log", gitlog(log, branch)),
        ok_("git.tasktable_history", hist, "inferred"),
        ok_("git.worktrees", list(worktrees)),
        ok_("git.tags", list(tags)),
        ok_("git.branches", list(branches)),
        ok_("git.contract", contract),
        ok_("tasktable.quotes", list(quotes), "reported"),
        ok_("gh.prs", list(prs)),
        ok_("gh.issue", iss),
        ok_("gh.runs", list(runs)),
        ok_("gh.tags", list(gh_tags)),
        release_runs if release_runs is not None else bad_("gh.release_runs", NO_WORKFLOW),
        compare if compare is not None else bad_("gh.compare", NO_MERGE_POINT),
        bad_("tmux.windows", NO_SESSION),
    ]
    return rows


# ---------------------------------------------------------------- simple-t0 / t1 / t2
SIMPLE_IDS = ["S-0", "S-1", "S-2", "S-3"]
S_DIR, S_BRANCH, S_NO = "7-simple-demo", "batch/7-demo", 7
S_PATH = "docs/traces/%s/任务表.md" % S_DIR
C_SHA, A1_SHA, A2_SHA = sha("c0"), sha("a1"), sha("a2")

S_CONTRACT_PR = pr(10, "docs(#7): 三件套入库", T("02:40"), merged=T("02:50"), author="agent-a", merged_by="agent-a",
                   head="wt/7-contract", merge_commit=C_SHA, body="合同与授权终点；Trace #7。")
S_PR11 = pr(11, "feat(#7): S-1 实现取数与解析", T("03:05"), merged=T("03:28"), author="agent-a", merged_by="owner-x",
            head="wt/7-S-1", merge_commit=A2_SHA, body="Trace #7 的第一步。",
            reviews=[("APPROVED", "owner-x", T("03:26"))], checks=[("selfcheck", "SUCCESS")])
S_CONTRACT = {"sha": C_SHA, "at": T("02:50"), "subject": "docs(#7): 三件套入库 (#10)", "path": "docs/traces/%s/合同.md" % S_DIR}
S_BRANCHES = [{"name": S_BRANCH, "sha": A2_SHA, "at": T("03:28")}]
S_COMMITS = [commit(C_SHA, T("02:50"), "docs(#7): 三件套入库 (#10)"),
             commit(A1_SHA, T("03:00"), "feat(#7): S-1 实现取数与解析"),
             commit(A2_SHA, T("03:28"), "feat(#7): S-1 实现取数与解析 (#11)")]
S_HIST = [(T("02:30"), sha("e0"), []), (T("02:55"), sha("e1"), ["S-0"]),
          (T("03:20"), sha("e2"), ["S-0", "S-1"]), (T("05:15"), sha("e3"), ["S-0", "S-1", "S-2"])]
S_WT = worktree("S-2", "wt/7-S-2", T("04:55"), "wip(#7): S-2 起草边界用例")


def build_simple(moment):
    now = T("02:58") if moment == 0 else T("06:00")
    hist_rows = {0: S_HIST[:2], 1: S_HIST[:3], 2: S_HIST[:4]}[moment]
    comments = [(5001, T("02:45"), "开工合同已批准，进入 Wave 1。")]
    if moment == 0:
        rows = base_rows(log=S_COMMITS[:1], hist=history(hist_rows, S_PATH, SIMPLE_IDS), prs=[S_CONTRACT_PR],
                         iss=issue(S_NO, T("02:00"), comments=comments), runs=[], branches=S_BRANCHES, contract=S_CONTRACT, branch=S_BRANCH)
        text = simple_table(False, False, False)
    else:
        runs = [run(901, T("03:26"), "success", A1_SHA, "wt/7-S-1")]
        rows = base_rows(log=S_COMMITS, hist=history(hist_rows, S_PATH, SIMPLE_IDS), prs=[S_CONTRACT_PR, S_PR11],
                         iss=issue(S_NO, T("02:00"), comments=comments), runs=runs, branches=S_BRANCHES,
                         worktrees=[S_WT], contract=S_CONTRACT, branch=S_BRANCH)
        text = simple_table(True, True, moment == 2)
    return text, snapshot(S_NO, S_DIR, S_BRANCH, now, finish(rows, now))


# ---------------------------------------------------------------- complex-f1..f4
X_DIR, X_BRANCH, X_NO = "8-complex-demo", "batch/8-demo", 8
X_PATH = "docs/traces/%s/任务表.md" % X_DIR
X_IDS = ["S-0", "S-A1", "S-A2", "K-1", "R-1", "F-1", "R-2", "G-1", "H-1", "D-1"]
XC_SHA, XA1, XA2, XB1, XB2 = sha("c0"), sha("a1"), sha("a2"), sha("b1"), sha("b2")
X_CONTRACT = {"sha": XC_SHA, "at": T("01:30"), "subject": "docs(#8): 三件套入库 (#20)", "path": "docs/traces/%s/合同.md" % X_DIR}
X_BATCH_PR = pr(29, "feat(#8): 批次分支", T("02:00"), head=X_BRANCH, body="Trace #8 批次 PR。", head_oid=CAND)


def x_contract_pr(self_merged):
    if self_merged:
        return pr(20, "docs(#8): 三件套入库", T("01:20"), merged=T("01:30"), author="agent-a", merged_by="agent-a",
                  head="wt/8-contract", merge_commit=XC_SHA, body="合同与授权终点；Trace #8。")
    return pr(20, "docs(#8): 三件套入库", T("01:20"), merged=T("01:30"), author="agent-a", merged_by="owner-x",
              head="wt/8-contract", merge_commit=XC_SHA, body="合同与授权终点；Trace #8。",
              reviews=[("APPROVED", "owner-x", T("01:29"))])


X_PR21 = pr(21, "feat(#8): S-A1 打包引擎目录", T("02:20"), merged=T("02:40"), author="agent-a", merged_by="owner-x",
            head="wt/8-S-A1", merge_commit=XA2, body="Trace #8。", reviews=[("APPROVED", "owner-x", T("02:39"))],
            checks=[("selfcheck", "SUCCESS")])
X_PR22 = pr(22, "feat(#8): S-A2 打包模板分层 CI", T("02:50"), merged=T("03:10"), author="agent-b", merged_by="owner-x",
            head="wt/8-S-A2", merge_commit=XB2, body="Trace #8。", reviews=[("APPROVED", "owner-x", T("03:09"))],
            checks=[("selfcheck", "SUCCESS")])


def build_complex(fault):
    now = T("06:00")
    contract_section = fault == 4
    self_merged = fault == 4
    prs = [x_contract_pr(self_merged), X_BATCH_PR]
    log = [commit(XC_SHA, T("01:30"), "docs(#8): 三件套入库 (#20)")]
    branch_tip = CAND
    hist = [(T("01:40"), sha("e0"), [])]
    runs = [run(801, T("02:30"), "failure", XA1, X_BRANCH), run(802, T("02:35"), "success", XA1, X_BRANCH),
            run(803, T("05:00"), "success", XB2, X_BRANCH)]
    # 候选冻结的 SHA 就是分支 HEAD；只有 F3 让分支往前走，K-1 / R-1 才判失效
    comments, worktrees, branches = [], [], [{"name": X_BRANCH, "sha": CAND, "at": T("03:15")}]
    a1 = a2 = k1 = r1 = False

    if fault == 1:                                        # F1 代理沉默 95 分钟
        log.append(commit(XA1, T("04:25"), "feat(#8): S-A1 打包引擎目录（阶段性）"))
        log.append(commit(XB1, T("05:50"), "feat(#8): S-A2 打包模板分层 CI（阶段性）"))
        hist.append((T("01:45"), sha("e1"), []))
        runs = [run(801, T("02:30"), "failure", XC_SHA, X_BRANCH), run(802, T("02:35"), "success", XC_SHA, X_BRANCH),
                run(803, T("05:00"), "success", XC_SHA, X_BRANCH)]
    elif fault == 2:                                      # F2 声称完成无 commit
        a1 = a2 = True
        prs.append(X_PR21)
        log += [commit(XA1, T("02:10"), "feat(#8): S-A1 打包引擎目录"), commit(XA2, T("02:40"), "feat(#8): S-A1 打包引擎目录 (#21)")]
        worktrees.append(worktree("S-A2", "wt/8-S-A2", T("03:10"), "chore(#8): S-A2 起草"))
        hist += [(T("02:45"), sha("e1"), ["S-A1"]), (T("03:20"), sha("e2"), ["S-A1", "S-A2"])]
    else:                                                 # F3 候选 SHA 变；F4 合同 PR 自合
        a1 = a2 = True
        prs += [X_PR21, X_PR22]
        log += [commit(XA1, T("02:10"), "feat(#8): S-A1 打包引擎目录"), commit(XA2, T("02:40"), "feat(#8): S-A1 打包引擎目录 (#21)"),
                commit(XB1, T("02:55"), "feat(#8): S-A2 打包模板分层 CI"), commit(XB2, T("03:10"), "feat(#8): S-A2 打包模板分层 CI (#22)")]
        hist += [(T("02:45"), sha("e1"), ["S-A1"]), (T("03:20"), sha("e2"), ["S-A1", "S-A2"])]
        if fault == 3:
            branches = [{"name": X_BRANCH, "sha": TIP, "at": T("05:30")}]   # 审核后分支又往前走了一个提交
            branch_tip = TIP
            k1 = True                                                       # K-3：已勾选的候选冻结在候选变更后同样失效
            log.append(commit(TIP, T("05:30"), "fix(#8): 合并主干最新改动"))
            comments = [(6001, T("03:30"), "独立审核 R-1 结论：0 P0 / 2 P1 / 3 P2"),
                        (6002, T("04:00"), "外审 codex 结论：无 P0，两条 P2 记账本")]
        else:
            hist.insert(1, (T("01:45"), sha("e9"), ["S-0"]))

    if k1:
        hist.append((T("03:25"), sha("e3"), ["S-A1", "S-A2", "K-1"]))
    prs[1] = dict(X_BATCH_PR, head_oid=branch_tip)
    text = complex_table(contract_section=contract_section, contract_ptr=False, a1=a1, a2=a2, k1=k1, r1=r1)
    rows = base_rows(log=log, hist=history(hist, X_PATH, X_IDS), prs=prs, iss=issue(X_NO, T("01:00"), comments=comments),
                     runs=runs, branches=branches, worktrees=worktrees, contract=X_CONTRACT, branch=X_BRANCH)
    return text, snapshot(X_NO, X_DIR, X_BRANCH, now, finish(rows, now))


# ---------------------------------------------------------------- unknown-gh
def build_unknown_gh():
    text, snap = build_simple(1)
    for key in ("gh.prs", "gh.issue", "gh.runs", "gh.tags"):
        snap["results"][key] = bad_(key, GH_GONE)
        snap["results"][key]["fetched_at"] = snap["now"]
    snap["results"]["gh.release_runs"] = bad_("gh.release_runs", GH_GONE)
    snap["results"]["gh.release_runs"]["fetched_at"] = snap["now"]
    return text, snap


# ---------------------------------------------------------------- stage-merged / published / closed、unknown-cmd
G_DIR, G_BRANCH, G_NO = "11-stage-demo", "batch/11-demo", 11
G_PATH = "docs/traces/%s/任务表.md" % G_DIR
G_IDS = ["S-0", "S-1"]
GC_SHA, GA_SHA, GM_SHA = sha("c0"), sha("a1"), sha("f1")
G_TABLE = table([("块 A 合同", ["- [x] S-0 合同与授权终点——PR #30 合入 [t:contract est:15m]"]),
                 ("Wave 1 实施", ["- [x] S-1 实现取数与解析——PR #31 合入 [t:impl est:30m]"])])
G_CONTRACT = {"sha": GC_SHA, "at": T("01:40"), "subject": "docs(#11): 三件套入库 (#30)", "path": "docs/traces/%s/合同.md" % G_DIR}
G_PR30 = pr(30, "docs(#11): 三件套入库", T("01:20"), merged=T("01:40"), author="agent-a", merged_by="owner-x",
            head="wt/11-contract", merge_commit=GC_SHA, body="合同与授权终点；Trace #11。",
            reviews=[("APPROVED", "owner-x", T("01:39"))])
G_PR31 = pr(31, "feat(#11): S-1 实现取数与解析", T("02:30"), merged=T("05:00"), author="agent-a", merged_by="owner-x",
            head=G_BRANCH, merge_commit=GM_SHA, body="Trace #11 批次 PR。", reviews=[("APPROVED", "owner-x", T("04:58"))],
            checks=[("selfcheck", "SUCCESS")], head_oid=GM_SHA)
G_LOG = [commit(GC_SHA, T("01:40"), "docs(#11): 三件套入库 (#30)"),
         commit(GA_SHA, T("02:20"), "feat(#11): S-1 实现取数与解析"),
         commit(GM_SHA, T("05:00"), "feat(#11): S-1 实现取数与解析 (#31)")]
G_HIST = [(T("01:30"), sha("e0"), []), (T("02:00"), sha("e1"), ["S-0"]), (T("05:05"), sha("e2"), ["S-0", "S-1"])]
G_TAG = {"name": "v0.3.0", "sha": GM_SHA, "at": T("05:20")}
STAGE_CFG = [{"key": "staging", "result_key": "config.staging", "label": "预发已升级"},
             {"key": "production", "result_key": "config.production", "label": "已上生产"}]
BUDGET_CFG = [{"key": "full_gate", "result_key": "config.full_gate", "label": "完整门禁", "cap": 5}]


def build_stage(kind):
    now = T("06:00")
    two_prs = kind == "two-prs"
    closed = kind == "closed"
    published = kind in ("published", "closed", "unknown-cmd")
    prs = [G_PR30, G_PR31]
    if two_prs:  # H-1：同分支两个 PR——#31 MERGED（批次 PR）＋ #32 OPEN（docs 收口）
        prs.append(pr(32, "docs(#11): 收口回写", T("05:30"), head=G_BRANCH, body="Trace #11 收口小 PR。", draft=True, head_oid=GM_SHA))
    iss = issue(G_NO, T("01:00"), state="CLOSED" if closed else "OPEN", closed=T("05:50") if closed else "",
                comments=[(7001, T("05:40"), "批次已合入主干，进入发布。")])
    runs = [run(910, T("04:50"), "success", GA_SHA, G_BRANCH)]
    rows = base_rows(log=G_LOG, hist=history(G_HIST, G_PATH, G_IDS), prs=prs, iss=iss, runs=runs,
                     tags=[dict(G_TAG, object=GM_SHA, commit=GM_SHA)] if published else [],
                     gh_tags=[G_TAG] if published else [], branches=[{"name": G_BRANCH, "sha": GM_SHA, "at": T("05:00")}],
                     contract=G_CONTRACT, branch=G_BRANCH,
                     release_runs=ok_("gh.release_runs", [run(950, T("05:10"), "success", GM_SHA, "main", "示例发布")]) if published else None,
                     compare=ok_("gh.compare", {"base": GM_SHA, "results": {}}))
    cfg = {"trace_branch": G_BRANCH}
    if published:
        cfg.update({"release_workflow": "示例发布", "stages": STAGE_CFG, "budgets": BUDGET_CFG})
        rows.append(ok_("config.staging", "v0.3.0"))
        rows.append(bad_("config.production", "超时 20s") if kind == "unknown-cmd" else ok_("config.production", "v0.3.0"))
        rows.append(ok_("config.full_gate", 3))
    return G_TABLE, snapshot(G_NO, G_DIR, G_BRANCH, now, finish(rows, now), cfg)


# ---------------------------------------------------------------- 案例表与人工核对断言
CASES = {
    "simple-t0": lambda: build_simple(0),
    "simple-t1": lambda: build_simple(1),
    "simple-t2": lambda: build_simple(2),
    "complex-f1": lambda: build_complex(1),
    "complex-f2": lambda: build_complex(2),
    "complex-f3": lambda: build_complex(3),
    "complex-f4": lambda: build_complex(4),
    "unknown-gh": build_unknown_gh,
    "unknown-cmd": lambda: build_stage("unknown-cmd"),
    "stage-merged": lambda: build_stage("merged"),
    "stage-published": lambda: build_stage("published"),
    "stage-closed": lambda: build_stage("closed"),
    "stage-two-prs": lambda: build_stage("two-prs"),
}
ALL_CASES = list(CASES) + ["trace1-replay"]


# 一句话说明 ＋ 逐项人工核对表（项 | expected 中必须出现的原文 | 视图 | 核对结论）。
# 视图：simple＝expected-simple.txt，complex＝expected-complex.txt，why＝expected-why.txt。
SUMMARY = {
    "trace1-replay": "本仓 Trace #1 的真实录制（`board.py --record`，`--now 2026-09-02T12:00:00Z`）：三件事——299 分钟最大空档（其中 219 分钟归因暂停）、`dd53ecf` → PR #9 的 24m36s 等待、9/9 PR 自合零批准。",
    "simple-t0": "单代理三步链的 T0：合同已批准但任务表未填指针（根节点自述未证＋合同 PR 自合），三个实施 / 审核模块尚无任何证据，下一步＝S-1。",
    "simple-t1": "T1：S-1 合入（模块 28/30 完成绿），S-2 只有 worktree 记录且已 65 分钟无新证据（模块 65/45 观察橙）。",
    "simple-t2": "T2：S-2 被勾选但始终没有 commit / PR / 评论 → 自述未证黄，头部存疑「自述未证 1」，整体阶段仍是「执行中」不判完成。",
    "complex-f1": "复杂链故障 1：S-A1 最近证据在 95 分钟前（> 90 分钟阈值）→ 卡住红，头部阻塞点名该步，附注「窗口状态未知，需元守护核」。",
    "complex-f2": "复杂链故障 2：S-A2 已勾选但只有 worktree 记录、无 commit / PR / 评论 → 自述未证黄。",
    "complex-f3": "复杂链故障 3：审核出结论后分支 HEAD（gh.prs 远端 head）从候选 `c3c3…` 变成 `d4d4…` → 已勾选的 t:gate 候选冻结 K-1 与审核结论 R-1 双双失效灰暗、卡片带 ↺重审；模块轮数 审 1 实 ＋ 外 1 推（时间窗回落）。",
    "complex-f4": "复杂链故障 4：合同 PR 由发起人自合且零批准，且合同步骤没有指针 → 根节点（块 A）自述未证黄 ＋ 头部存疑行。",
    "unknown-gh": "所有 `gh.*` 键不可得：依赖它们的步骤 / 模块 / 五级阶段 / 轮数 / 预算一律显示「未知」，不回落到「待办」或上一级结论；只靠 git 就能坐实的 S-1 仍判完成。",
    "unknown-cmd": "证据源配置声明的 `config.production` 命令超时：该级阶段显示「未知」并进头部阻塞，其余四级照常判定（不沿用旧结论）；证据链只写键与失败类别，不带 stderr。",
    "stage-merged": "五级阶段第一刻：批次 PR 已合入主干、尚未发布。",
    "stage-published": "五级阶段第二刻：发布工作流 run success ＋ gh.tags 出 tag，预发 / 生产命令取到同一 tag → 阶段「已上生产」、下一步「观察与收口」（推断链的「已完成」表达）。",
    "stage-closed": "五级阶段第三刻：Trace Issue 关闭 → 阶段「已收口」、下一步「无（Trace 已关闭）」。",
    "stage-two-prs": "热修 H-1：同一批次分支上两个 PR（#31 已 MERGED ＋ #32 OPEN 的 docs 收口）→ 批次 PR 取 #31，合入主干「是」，存疑记「另有 PR #32 开放」；尚未发布时预发 / 生产按 N-1 显示「未配置」（本例未配置）。",
}
OK = "已逐项人工核对，与接口约定一致"
CHECKS: dict[str, list] = {
    "trace1-replay": [
        ("最大空档 299 分钟含暂停归因（存疑行短句，K-4）", "空档 299推 分 10:48→15:46（暂停 219报）", "simple", OK),
        ("空档归因暂停 219 分钟", "commit 2183910 09-02 10:48:20 → PR #5 09-02 15:46:55；归因暂停 219报 分钟", "why", OK),
        ("dd53ecf → PR #9 等待 24m36s", "24m36s（commit dd53ecf 09-02 16:26:47 → PR #9 09-02 16:51:23）", "why", OK),
        ("9/9 PR 自合零批准", "PR 自合 9/9实 零批准", "simple", OK),
        ("合同 PR #2 自合零批准", "合同 PR #2 自合/零批准", "simple", OK),
        ("S-1 卡片标零批准（黄）", "[PR #2 ✓合入 · 自合 · 零批准]", "complex", OK + "；dump 无颜色，黄由 chip_status=doneq 承载"),
        ("Issue 已关闭 → 阶段已收口", "已收口（Issue 关闭 17:54）", "simple", OK),
    ],
    "simple-t0": [
        ("下一步＝S-1", "下一步    S-1 实现取数与解析（下一步）", "simple", OK),
        ("根节点黄（自述未证）", "块 A 合同 · 自述未证", "simple", OK),
        ("模块第一行勾选＋未证（R1-20）", "块 A 合同 勾选 1/1 · 未证 1", "simple", OK),
        ("存疑＝自述未证 1 ＋ 合同 PR 自合", "存疑      自述未证 1实（S-0） · 合同 PR #10 自合/零批准", "simple", OK),
        ("Wave 2 / Wave 3 全灰待做", "Wave 2 实施 · 待做", "simple", OK + "（Wave 1 因依赖已勾选显示「下一步」亮蓝，不是灰）"),
        ("阶段执行中", "阶段      执行中 · Wave 1 实施（1/4实 勾选）", "simple", OK),
    ],
    "simple-t1": [
        ("S-1 绿 28/30", "Wave 1 实施 · 完成 ───────────────────────────── 28/30 ─┐", "simple", OK),
        ("S-2 橙 65/45", "Wave 2 实施 · 观察 ───────────────────────────── 65/45 ─┐", "simple", OK),
        ("下一步＝S-2 观察", "下一步    S-2 补边界与快照测试（观察）", "simple", OK),
        ("S-1 步骤实际 28 分钟", "S-1 | 完成 |", "why", OK),
    ],
    "simple-t2": [
        ("S-2 勾了零 commit → 黄", "Wave 2 实施 · 自述未证", "simple", OK),
        ("头部自述未证 1", "存疑      自述未证 1实（S-2）", "simple", OK),
        ("整体不判完成", "阶段      执行中 · Wave 3 审核（3/4实 勾选）", "simple", OK),
        ("五级阶段未合入主干", "合入主干 否", "simple", OK),
    ],
    "complex-f1": [
        ("S-A1 卡住红", "Wave 1 实施 · 卡住", "simple", OK),
        ("头部阻塞点名 95 分钟", "阻塞      S-A1 95实 分钟无证据", "simple", OK + "；90 分钟为「观察」上界，取 95 分钟才越过阈值"),
        ("窗口状态未知附注", "⚠ 窗口状态未知，需元守护核", "simple", OK),
        ("步骤级卡住理由", "S-A1 | 卡住 |", "why", OK),
    ],
    "complex-f2": [
        ("S-A2 自述未证黄", "存疑      自述未证 1实（S-A2）", "simple", OK),
        ("模块聚合为自述未证", "Wave 1 实施 · 自述未证", "simple", OK),
        ("无阻塞", "阻塞      无", "simple", OK),
    ],
    "complex-f3": [
        ("候选与结论双双失效", "阻塞      审核结论失效 K-1/R-1", "simple", OK),
        ("已勾选的 t:gate 候选冻结也失效（K-2 / K-3）", "K-1 门禁 · 失效", "complex", OK + "；K-1 已勾选且为 t:gate，候选 SHA 变化后仍失效"),
        ("失效理由写明已勾选（K-3）", "已勾选但候选已变", "why", OK),
        ("候选 SHA 变化芯片", "[候选 c3c3c3 → 已变 d4d4d4]", "complex", OK),
        ("重审来源角标", "↺重审", "complex", OK + "（原文「↺重审来源」被卡片宽度截为「↺重审」）"),
        ("轮数 审 1 实 ＋ 外 1 推", "审 1实 · 外 1推", "simple", OK + "；外审评论首行无 Step ID，按活动窗口回落为推断级"),
        ("推断级归属写进证据链", "推（落在窗口", "why", OK),
    ],
    "complex-f4": [
        ("根节点黄", "块 A 合同 · 自述未证", "simple", OK),
        ("存疑行含合同 PR 自合零批准", "存疑      自述未证 1实（S-0） · 合同 PR #20 自合/零批准", "simple", OK),
        ("合同 PR 判定写进证据链", "合同 PR #20 | 存疑 |", "why", OK),
    ],
    "unknown-gh": [
        ("五级阶段未知不回落", "五级阶段  合入主干 未知 · 已发布 未知 · 预发已升级 未配置 · 已上生产 未配置 · 收口 未知", "simple", OK),
        ("轮数未知", "审 未知 · 外 未知 · 修 未知 · CI 红未知 绿未知", "simple", OK),
        ("预算未知", "预算      PR 未知   CI 次数 未知", "simple", OK),
        ("无证据步骤判未知而非待办", "S-3 | 未知 |", "why", OK),
        ("只靠 git 能坐实的步骤仍判完成", "S-1 | 完成 |", "why", OK),
    ],
    "unknown-cmd": [
        ("该级阶段未知", "五级阶段  合入主干 是 · 已发布 是 · 预发已升级 是 · 已上生产 未知（超时 20s） · 收口 否", "simple", OK),
        ("阶段未知进阻塞", "阻塞      阶段未知：已上生产", "simple", OK),
        ("失败类别写进证据链（A-1：只写键与类别）", "阶段·已上生产 | 未知 | image_tag | config.production | config.production：超时", "why", OK),
        ("上一级仍按自身证据判定", "阶段·预发已升级 | 是 |", "why", OK),
    ],
    "stage-merged": [
        ("阶段＝已合入主干", "阶段      已合入主干 · 2/2实 勾选", "simple", OK),
        ("五级阶段", "五级阶段  合入主干 是 · 已发布 否 · 预发已升级 未配置 · 已上生产 未配置 · 收口 否", "simple", OK),
    ],
    "stage-published": [
        ("阶段＝已上生产", "阶段      已上生产 · 2/2实 勾选", "simple", OK),
        ("下一步＝观察与收口（已完成表达）", "下一步    观察与收口", "simple", OK),
        ("五级阶段", "五级阶段  合入主干 是 · 已发布 是 · 预发已升级 是 · 已上生产 是 · 收口 否", "simple", OK),
        ("发布 run ＋ tag 双证据", "发布 run success", "why", OK),
        ("预算条有上限画条", "完整门禁 ▰▰▰▰▱▱ 3实/5", "simple", OK),
    ],
    "stage-two-prs": [
        ("合入主干按唯一 MERGED 的 PR 判定（规则①）", "五级阶段  合入主干 是 · 已发布 否 · 预发已升级 未配置 · 已上生产 未配置 · 收口 否", "simple", OK),
        ("存疑记另有 PR 开放", "另有 PR #32 开放", "simple", OK),
        ("Why 写明批次 PR 与规则", "批次 PR #31 MERGED → 合并提交 f1f1f1f；规则①：恰一个 MERGED 到 base；另有 #32 开放", "why", OK),
    ],
    "stage-closed": [
        ("阶段＝已收口", "阶段      已收口（Issue 关闭 13:50）· 2/2实 勾选", "simple", OK),
        ("下一步＝无", "下一步    无（Trace 已关闭）", "simple", OK),
        ("五级阶段全是", "收口 是", "simple", OK),
    ],
}


# ---------------------------------------------------------------- 落盘
def write_case(name, text, snap):
    out = os.path.join(FIXTURES, name)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "任务表.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(os.path.join(out, "snapshot.json"), "w", encoding="utf-8") as fh:
        json.dump(snap, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return out


def write_readme(name):
    rows = CHECKS.get(name) or []
    lines = ["# 夹具 %s" % name, "", SUMMARY.get(name, ""), "",
             "逐项人工核对（断言原文由 run_fixtures.py 直接比对，expected 被重生成也不会连带变绿）：", "",
             "| 项 | 期望（expected 中必须出现的原文） | 视图 | 人工核对结论 |", "| --- | --- | --- | --- |"]
    for item, needle, view, verdict in rows:
        lines.append("| %s | `%s` | %s | %s |" % (item, needle, view, verdict))
    lines += ["", "重生成：`python3 -B tests/board/make_fixtures.py --expected`（`trace1-replay` 的快照来自"
              " `board.py --record`，只重画 expected）。"]
    with open(os.path.join(FIXTURES, name, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")


def dump(case_dir, view, why=False):
    argv = [sys.executable, "-B", BOARD, "--fixture", case_dir, "--dump", "--view", view,
            "--width", str(WIDTH), "--height", str(HEIGHT)]
    if why:
        argv.append("--why")
    proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120,
                          env=dict(os.environ, PATH="/usr/bin:/bin"))
    if proc.returncode != 0:
        raise SystemExit("board.py 失败（%s %s）：%s" % (case_dir, view, proc.stderr.strip()[:400]))
    return proc.stdout


def write_expected(name):
    case_dir = os.path.join(FIXTURES, name)
    for fname, view, why in (("expected-simple.txt", "simple", False), ("expected-complex.txt", "complex", False),
                             ("expected-why.txt", "simple", True)):
        with open(os.path.join(case_dir, fname), "w", encoding="utf-8") as fh:
            fh.write(dump(case_dir, view, why))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="make_fixtures.py", allow_abbrev=False, description="生成看板合成夹具")
    ap.add_argument("--expected", action="store_true", help="同时用 board.py 重生成 expected-*.txt")
    ap.add_argument("--only", help="只处理某个案例名")
    args = ap.parse_args(argv)
    names = [args.only] if args.only else ALL_CASES
    for name in names:
        if name in CASES:
            text, snap = CASES[name]()
            write_case(name, text, snap)
        write_readme(name)
        if args.expected:
            write_expected(name)
        print("夹具 %s：%s" % (name, "任务表 / 快照 / README / expected" if args.expected else "任务表 / 快照 / README"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
