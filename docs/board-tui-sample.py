#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 出处：trace-kit Issue #12（Trace 看板 v0 输入 Issue）2026-09-02 与产品负责人逐轮迭代的 TUI 样稿；数据为内嵌样例，不读仓库。
# 用途：给实现看板的 Trace 当视觉与交互基准，不是交付物。三组用例：1 演示（执行中，合成数据）；2 Trace #1 真实收口态；3 单代理三步最小用例。
# 运行：python3 docs/board-tui-sample.py            （在 tmux window 里，建议 ≥120 列）
#       python3 docs/board-tui-sample.py --dump 1 --width 150 --height 60   （纯文本快照）
"""Trace 看板 TUI 样稿 v3：按依赖分层的纵向流程图。步骤为大框，机器证据（PR / CI / 候选 / 审核结论 / tag / 评论）为小节点。
边只有一种：灰线 + 箭头。动效在节点上：运行中的框边一圈流水、分子闪烁。时长格式 "实际或已跑/预估"（分钟）。
键：1/2/3 用例   ↑/↓ 逐行   fn+↑/↓ (PageUp/PageDown) 翻页   fn+←/→ (Home/End) 顶/底   a 动效开关   q 退出
"""
import os, sys, select, signal, termios, tty, unicodedata, argparse, shutil

C = dict(todo=245, ready=39, running=75, watch=208, stalled=196, human=135, done=71, doneq=220, stale=240)
EDGE = 245; BRIGHT = 231; INK = 252; LABEL = 245; DIM = 240
DASHED = set()  # 不再用虚框
ATTENTION = set()  # 不加标记：颜色足够
WARN = "\u26a0"  # 文本样式，tmux 按 1 格计；颜色由我们涂黄
TYPE = {"impl": "实施", "review": "审核", "gate": "门禁", "human": "人工", "deploy": "发布", "research": "研究", "contract": "合同"}
ANIM = {"running", "watch"}  # 哪些状态的节点有动效

def N(*a):
    d = dict(zip(("id", "kind", "type", "status", "title", "sub", "wave", "needs", "t"), a)); d.setdefault("t", ""); return d
DATA = {
 1: dict(name="演示：执行中（合成数据）", nodes=[
  N("C0", "chip", "contract", "doneq", "合同 PR #20 ✓合入 · 发起人自合 · 零批准", "", "W0", []),
  N("S-0-1", "step", "research", "done", "只读盘点与分级清单", "plan", "W0", ["C0"], "20/"),
  N("E-0-1", "chip", "", "done", "评论 ✓ 02:10", "", "W0", ["S-0-1"]),
  N("S-0-2", "step", "research", "done", "Wave 0：外部窗口核实", "plan", "W0", ["E-0-1"], "35/"),
  N("E-0-2", "chip", "", "done", "PR #19 ✓ 自测✓ CI✓ 24s", "", "W0", ["S-0-2"]),
  N("S-1a", "step", "impl", "done", "打包 plugin/", "impl_a", "W1", ["E-0-2"], "41/45"),
  N("E-1a", "chip", "", "done", "PR #21 ✓ 自测✓ CI✓ 26s", "", "W1", ["S-1a"]),
  N("S-1b", "step", "impl", "stalled", "打包 template/ 分层 CI", "impl_b", "W1", ["E-0-2"], "130/90"),
  N("E-1b", "chip", "", "stalled", "8c58a7 · 95m 前 · 无 PR", "", "W1", ["S-1b"]),
  N("S-1c", "step", "impl", "doneq", "examples 示例清单", "impl_c", "W1", ["E-0-2"], "?/30"),
  N("E-1c", "chip", "", "doneq", "无 commit · 无 PR", "", "W1", ["S-1c"]),
  N("S-1d", "step", "impl", "running", "deploy 骨架", "impl_d ↺重审来源", "W1", ["E-0-2"], "38/60"),
  N("E-1d", "chip", "", "running", "PR #24 打开 · CI 跑 3m", "", "W1", ["S-1d"]),
  N("S-2b", "step", "research", "ready", "验收夹具与探针", "acceptor", "W2", ["E-0-2"], "/40"),
  N("E-2b", "chip", "", "todo", "待：PR / 评论", "", "W2", ["S-2b"]),
  N("K-2", "chip", "", "stale", "候选 dd53ec 冻结 → 已变 8c58a7", "", "W2", ["E-1a", "E-1b", "E-1c", "E-1d"]),
  N("R-2", "step", "review", "stale", "独立审核（子代理 · 第 1 轮）", "fable xhigh", "W2", ["K-2"], "25/60"),
  N("E-2", "chip", "", "stale", "结论 0 P0 / 2 P1 / 3 P2 · 已失效", "", "W2", ["R-2"]),
  N("X-2", "step", "review", "todo", "外部审核（codex · 可选）", "未派", "W2", ["K-2"], "/20"),
  N("E-x2", "chip", "", "todo", "未派", "", "W2", ["X-2"]),
  N("F-2", "step", "impl", "todo", "统一修复包", "impl_a", "W2", ["E-2", "E-x2"], "/30"),
  N("E-f2", "chip", "", "todo", "修复包 PR 待", "", "W2", ["F-2"]),
  N("R-2r", "step", "review", "todo", "定向复核（同一审核者 · 第 2 轮）", "", "W2", ["E-f2"], "/15"),
  N("E-r2", "chip", "", "todo", "复核结论 待", "", "W2", ["R-2r"]),
  N("S-3", "step", "gate", "todo", "完整门禁 Epic Full", "", "W2", ["E-r2", "E-2b"], "/8"),
  N("E-3", "chip", "", "todo", "CI run 待", "", "W2", ["S-3"]),
  N("S-4", "step", "human", "human", "产品负责人批准发布", "待裁定 1 项", "W3", ["E-3"], ""),
  N("S-5", "step", "deploy", "todo", "发布 tag v0.2.0", "", "W3", ["S-4"], "/10"),
  N("E-5", "chip", "", "todo", "tag 待", "", "W3", ["S-5"]),
  N("S-6", "step", "impl", "todo", "收口评论与残留盘点", "", "W3", ["E-5"], "/20"),
  N("E-6", "chip", "", "todo", "收口评论 待", "", "W3", ["S-6"]),
 ], header=dict(stage="Executing · W1→W2（5/17 步骤完成）", block="S-1b 95 分钟无外部证据（窗口未知，需 guardian 核）；R-2 审核结论失效",
   nxt="S-2b 可立即做；R-2 等 S-1b / S-1d 后重审", budget=[("子代理人次", 5, 10), ("完整门禁", 2, 6), ("审核轮次", 1, 3)],
   doubt="自述未证 1（S-1c）· 合同 PR #20 由发起人自合、零批准", evidence="12 分钟前 · commit 8c58a7（S-1d）")),
 2: dict(name="Trace #1（真实，已关闭）", nodes=[
  N("S-0a", "step", "research", "doneq", "克隆 + 推送冒烟", "出生即勾选", "W0", [], "?/"),
  N("E-0a", "chip", "", "doneq", "无独立证据", "", "W0", ["S-0a"]),
  N("S-0b", "step", "research", "done", "Trace Issue #1 + 分级清单", "", "W0", ["E-0a"], "4/"),
  N("E-0b", "chip", "", "done", "评论 ✓ 02:26 UTC", "", "W0", ["S-0b"]),
  N("S-1", "step", "impl", "done", "三件套 + METHOD 入库", "合同 v1", "W0", ["E-0b"], "9/"),
  N("E-1", "chip", "", "doneq", "PR #2 ✓合入 · 发起人自合 · 零批准", "", "W0", ["S-1"]),
  N("S-2a", "step", "impl", "done", "plugin/ 五 skill", "", "W1", ["E-1"], "9/"),
  N("E-2a", "chip", "", "done", "PR #3 ✓合入 · 自合", "", "W1", ["S-2a"]),
  N("S-2b", "step", "impl", "done", "template/ 文档与约定", "跨暂停 219 分钟", "W1", ["E-1"], "?/"),
  N("E-2b", "chip", "", "done", "PR #5 ✓合入 · 自合", "", "W1", ["S-2b"]),
  N("S-2c", "step", "impl", "done", "template/ 分层 CI", "跨暂停 219 分钟", "W1", ["E-1"], "?/"),
  N("E-2c", "chip", "", "done", "PR #6 ✓合入 · 自合", "", "W1", ["S-2c"]),
  N("S-2d", "step", "impl", "done", "template/deploy 骨架", "跨暂停 219 分钟", "W1", ["E-1"], "?/"),
  N("E-2d", "chip", "", "done", "PR #7 ✓合入 · 自合", "", "W1", ["S-2d"]),
  N("S-2e", "step", "impl", "done", "examples/lingxi 清单", "", "W1", ["E-1"], "10/"),
  N("E-2e", "chip", "", "done", "PR #4 ✓合入 · 自合", "", "W1", ["S-2e"]),
  N("S-3", "step", "impl", "done", "集成 init.sh 与自检", "", "W2", ["E-2a", "E-2b", "E-2c", "E-2d", "E-2e"], "10/"),
  N("E-3", "chip", "", "done", "PR #8 ✓合入 · 自合 · kit-selfcheck ✓ 30s", "", "W2", ["S-3"]),
  N("S-4a", "step", "gate", "done", "自验证①自回灌", "同 PR #8", "W2", ["E-3"], "?/"),
  N("E-4a", "chip", "", "doneq", "共用 PR #8（无独立制品）", "", "W2", ["S-4a"]),
  N("S-4b", "step", "gate", "done", "自验证②空项目冒烟", "同 PR #8", "W2", ["E-3"], "?/"),
  N("E-4b", "chip", "", "doneq", "共用 PR #8（无独立制品）", "", "W2", ["S-4b"]),
  N("K-5", "chip", "", "done", "候选 dd53ecf 冻结 08:26 UTC", "", "W2", ["E-4a", "E-4b"]),
  N("S-5", "step", "review", "done", "独立审核（Fable xhigh · 第 1 轮）", "P0 0·P1 4·P2 10", "W2", ["K-5"], "25/"),
  N("E-5", "chip", "", "done", "结论评论 ✓ · 8 处变异实测红→绿", "", "W2", ["S-5"]),
  N("F-5", "step", "impl", "done", "统一修复包", "编排者直接坐实", "W2", ["E-5"], "16/"),
  N("E-f5", "chip", "", "done", "PR #9 ✓合入 · 自合 · kit-selfcheck ✓", "", "W2", ["F-5"]),
  N("R-5", "step", "review", "done", "定向复核（同一审核者 · 第 2 轮）", "P1/P2 全闭合", "W2", ["E-f5"], "15/"),
  N("E-r5", "chip", "", "done", "复核评论 ✓ 09:07 UTC", "", "W2", ["R-5"]),
  N("S-6a", "step", "deploy", "done", "发布 v0.1.0", "", "W3", ["E-r5"], "2/"),
  N("E-6a", "chip", "", "done", "PR #10 ✓合入 · 自合 · tag v0.1.0 → 47aaef5 · CI ✓", "", "W3", ["S-6a"]),
  N("S-6b", "step", "impl", "done", "收口评论与残留盘点", "", "W3", ["E-6a"], "1/"),
  N("E-6b", "chip", "", "done", "收口评论 ✓ 09:09 UTC", "", "W3", ["S-6b"]),
  N("H-1", "step", "human", "human", "Template 仓库开关", "机器人 403", "W3", ["E-6b"], "174/"),
  N("S-7", "step", "impl", "done", "根 README 改写", "", "W4", ["E-6b"], "45/"),
  N("E-7", "chip", "", "done", "commit 300ded8 ✓", "", "W4", ["S-7"]),
 ], header=dict(stage="Closed · Complete（17/18；H-1 待人类）", block="H-1 Template 开关：机器人 403，待产品负责人", nxt="无（Trace 已关闭）",
   budget=[("子代理人次", 8, 10), ("kit-selfcheck", 4, 0), ("审核轮次", 2, 2)],
   doubt="出生即勾选 1（S-0a）· 共用 PR 2（S-4a/4b）· 合同 PR #2 自合、零批准 · 9/9 PR 自合", evidence="09:54 UTC · commit 300ded8（S-7）")),
 3: dict(name="简单用例：单代理 3 步（T1 时刻）", nodes=[
  N("C0", "chip", "contract", "doneq", "合同 PR #30 ✓合入 · 发起人自合", "", "W1", []),
  N("S-1", "step", "impl", "done", "实现 validateEmail", "", "W1", ["C0"], "28/30"),
  N("E-1", "chip", "", "done", "PR #31 ✓ 自测✓ CI✓ 18s", "", "W1", ["S-1"]),
  N("S-2", "step", "impl", "watch", "补边界测试", "65 分钟无证据", "W1", ["E-1"], "65/45"),
  N("E-2", "chip", "", "watch", "commit 1f2e3d · 65m 前 · 无 PR", "", "W1", ["S-2"]),
  N("S-3", "step", "review", "todo", "独立审核", "", "W2", ["E-2"], "/20"),
  N("E-3", "chip", "", "todo", "审核结论 待", "", "W2", ["S-3"]),
 ], header=dict(stage="Executing · W1（1/3 完成）", block="S-2 65 分钟无外部证据（观察；90 分钟转卡住）", nxt="S-3 等 S-2",
   budget=[("子代理人次", 1, 2), ("完整门禁", 0, 2), ("审核轮次", 0, 1)], doubt="合同 PR #30 由发起人自合、零批准", evidence="65 分钟前 · commit 1f2e3d（S-2）")),
}

# ---------- 宽度与画布 ----------
def cw(ch):
    if unicodedata.combining(ch) or ch == "\ufe0f": return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
def dw(s): return sum(cw(c) for c in s)
def trunc(s, n):
    if dw(s) <= n: return s
    out, w = "", 0
    for c in s:
        if w + cw(c) > n - 1: break
        out += c; w += cw(c)
    return out + "…"
def pad(s, n): return s + " " * max(0, n - dw(s))
def wrap2(s, n):
    """按显示宽度折成最多两行；超出第二行末尾加省略号。"""
    lines, cur, w = [], "", 0
    for c in s:
        k = cw(c)
        if w + k > n and len(lines) == 0:
            lines.append(cur); cur, w = "", 0
        cur += c; w += k
    lines.append(cur)
    if len(lines) > 2: lines = lines[:2]
    if dw(lines[-1]) > n: lines[-1] = trunc(lines[-1], n)
    while len(lines) < 2: lines.append("")
    return lines

class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.cells = [[(" ", None) for _ in range(w)] for _ in range(h)]
    def put(self, x, y, s, color=None, bold=False):
        if y < 0 or y >= self.h: return
        for c in s:
            k = cw(c)
            if k == 0: continue
            if x >= self.w: break
            if x >= 0:
                self.cells[y][x] = (c, (color, bold))
                if k == 2 and x + 1 < self.w: self.cells[y][x + 1] = ("", (color, bold))
            x += k
    def render_row(self, row):
        line, cur = "", None
        for ch, st in row:
            if ch == "": continue
            if st != cur:
                line += "\x1b[0m"
                if st and st[0] is not None: line += "\x1b[38;5;%dm" % st[0]
                if st and st[1]: line += "\x1b[1m"
                cur = st
            line += ch
        return line + "\x1b[0m"
    def render(self): return [self.render_row(r) for r in self.cells]

BITS = {1: "╵", 2: "╷", 3: "│", 4: "╴", 8: "╶", 12: "─", 10: "┌", 6: "┐", 9: "└", 5: "┘", 14: "┬", 13: "┴", 11: "├", 7: "┤", 15: "┼"}
class Lines:
    def __init__(self): self.cells = {}
    def add(self, x, y, bits): self.cells[(x, y)] = self.cells.get((x, y), 0) | bits
    def vline(self, x, y1, y2, attach_top=False, attach_bottom=False):
        for y in range(y1, y2 + 1): self.add(x, y, (1 if (y > y1 or attach_top) else 0) | (2 if (y < y2 or attach_bottom) else 0))
    def hline(self, x1, x2, y):
        a, b = min(x1, x2), max(x1, x2)
        for x in range(a, b + 1): self.add(x, y, (4 if x > a else 0) | (8 if x < b else 0))

# ---------- 图 ----------
def build_graph(d):
    nodes = {n["id"]: dict(n) for n in d["nodes"]}
    order = [n["id"] for n in d["nodes"]]
    layer = {}
    def L(i):
        if i in layer: return layer[i]
        ps = [p for p in nodes[i]["needs"] if p in nodes]
        layer[i] = 0 if not ps else max(L(p) for p in ps) + 1
        return layer[i]
    for i in order: L(i)
    edges, dummies = [], {}
    for i in order:
        for p in nodes[i]["needs"]:
            if p not in nodes: continue
            if layer[i] - layer[p] == 1: edges.append((p, i)); continue
            prev = p
            for k in range(layer[p] + 1, layer[i]):
                did = "·%s→%s·%d" % (p, i, k); dummies[did] = k; edges.append((prev, did)); prev = did
            edges.append((prev, i))
    for did, k in dummies.items(): nodes[did] = dict(id=did, kind="dummy", type="", status="todo", title="", sub="", wave="", needs=[], t=""); layer[did] = k
    rows = [[] for _ in range(max(layer.values()) + 1)]
    for i in order: rows[layer[i]].append(i)
    for did in dummies: rows[layer[did]].append(did)
    return nodes, edges, rows

def layout(d, W):
    nodes, edges, rows = build_graph(d)
    GAP = 2; preds = {}
    for s, t in edges: preds.setdefault(t, []).append(s)
    posidx = {}
    for r, ids in enumerate(rows):
        if r > 0:
            orig = {i: k for k, i in enumerate(ids)}
            def bc(i):
                ps = [p for p in preds.get(i, []) if p in posidx]
                return (sum(posidx[p] for p in ps) / len(ps)) if ps else 1e9
            ids.sort(key=lambda i: (bc(i), orig[i]))
        for k, i in enumerate(ids): posidx[i] = k
    def w0(i, bw):
        n = nodes[i]
        if n["kind"] == "step": return bw
        if n["kind"] == "chip": return min(max(dw(n["title"]) + 2, 10), 46)
        return 1
    box_w = 34
    step_rows = [ids for ids in rows if any(nodes[i]["kind"] == "step" for i in ids)]
    while box_w > 24 and any(sum(w0(i, box_w) for i in ids) + GAP * (len(ids) - 1) > W - 2 for ids in step_rows): box_w -= 1
    chip_cap = {}
    for ids in rows:
        chips = [i for i in ids if nodes[i]["kind"] == "chip"]
        if not chips: continue
        room = W - 2 - GAP * (len(ids) - 1) - sum(w0(i, box_w) for i in ids if nodes[i]["kind"] != "chip")
        if sum(w0(i, box_w) for i in chips) > room:
            for i in chips: chip_cap[i] = max(10, room // len(chips))
    def width_of(i): return min(w0(i, box_w), chip_cap[i]) if i in chip_cap else w0(i, box_w)
    row_h = [max([5 if nodes[i]["kind"] == "step" else 1 for i in ids] + [1]) for ids in rows]
    geo = {}
    for r, ids in enumerate(rows):
        total = sum(width_of(i) for i in ids) + GAP * (len(ids) - 1); x = max(0, (W - total) // 2)
        if len(ids) == 1:
            ps = [p for p in preds.get(ids[0], []) if p in geo]
            if len(ps) == 1: x = max(0, min(W - width_of(ids[0]), geo[ps[0]][4] - width_of(ids[0]) // 2))
        for i in ids:
            w = width_of(i); geo[i] = [x, 0, w, row_h[r], x + w // 2]; x += w + GAP
    def strip_plan(r):
        es = [(s, t) for s, t in edges if s in rows[r] and t in rows[r + 1]]
        srcs = {s for s, _ in es}; tgts = {t for _, t in es}
        by_t = len(tgts) <= len(srcs); groups = {}
        for s, t in es: groups.setdefault(t if by_t else s, []).append((s, t))
        items = []
        for k, ges in groups.items():
            xs = [geo[s][4] for s, _ in ges] + [geo[t][4] for _, t in ges]; items.append((min(xs), max(xs), k))
        items.sort(); lanes = []
        for a, b, k in items:
            for lane in lanes:
                if lane[0] + 2 < a: lane[0] = b; lane[1].append(k); break
            else: lanes.append([b, [k]])
        return es, groups, [l[1] for l in lanes]
    y = 0; strips = []
    for r, ids in enumerate(rows):
        for i in ids: geo[i][1] = y
        y += row_h[r]
        if r + 1 < len(rows):
            es, groups, lanes = strip_plan(r); strips.append((y, es, groups, lanes)); y += len(lanes) + 2
    return nodes, edges, rows, geo, strips, y

def draw_graph(d, W):
    nodes, edges, rows, geo, strips, H = layout(d, W)
    cv = Canvas(W, H + 1); ln = Lines(); anim = []  # anim: (border_cells[(x,y,ch)], color, num_cells[(x,y,ch)])
    for i, (x, y, w, h, cx) in geo.items():
        n = nodes[i]; st = n["status"]; col = C[st]
        if n["kind"] == "step":
            hz = "┄" if st in DASHED else "─"; vt = "┆" if st in DASHED else "│"; inner = w - 2
            tag = "%s %s" % (n["id"], TYPE.get(n["type"], "")); tt = n.get("t") or ""
            right = (" " + tt + " " + hz + "┐") if tt else "┐"
            left = "┌" + hz + " " + tag + " "; fill = w - dw(left) - dw(right)
            if fill < 0: left = "┌" + hz + " " + trunc(tag, max(3, dw(tag) + fill)) + " "; fill = max(0, w - dw(left) - dw(right))
            bold = st in ("stalled", "ready", "running", "watch")
            cv.put(x, y, left + hz * fill, col, bold)
            tx = x + dw(left) + fill + 1
            if tt: cv.put(tx - 1, y, " ", col); cv.put(tx, y, tt, 250 if st in ANIM or st == "stalled" else DIM, bold); cv.put(tx + dw(tt), y, " " + hz + "┐", col, bold)
            else: cv.put(x + w - 1, y, "┐", col, bold)
            t1, t2 = wrap2(n["title"], inner - 2)
            for k, line in ((1, t1), (2, t2)):
                cv.put(x, y + k, vt, col); cv.put(x + 1, y + k, " " + pad(line, inner - 2) + " ", INK); cv.put(x + w - 1, y + k, vt, col)
            sub = (n["wave"] + " · " + n["sub"]) if n["wave"] and n["sub"] else (n["wave"] or n["sub"])
            cv.put(x, y + 3, vt, col); cv.put(x + 1, y + 3, " " + pad(trunc(sub, inner - 2), inner - 2) + " ", DIM); cv.put(x + w - 1, y + 3, vt, col)
            cv.put(x, y + 4, "└" + hz * (w - 2) + "┘", col)
            if st in ANIM:
                tcells = set(range(tx, tx + dw(tt))) if tt else set()
                border = [(xx, y, cv.cells[y][xx][0]) for xx in range(x, x + w) if xx not in tcells] + [(x + w - 1, yy, cv.cells[yy][x + w - 1][0]) for yy in (y + 1, y + 2, y + 3)] \
                       + [(xx, y + 4, cv.cells[y + 4][xx][0]) for xx in range(x + w - 1, x - 1, -1)] + [(x, yy, cv.cells[yy][x][0]) for yy in (y + 3, y + 2, y + 1)]
                num = [(tx + k, y, ch) for k, ch in enumerate(tt.split("/")[0])]
                anim.append(([b for b in border if b[2] != ""], col, num))
        elif n["kind"] == "chip":
            cv.put(x, y, "[" + pad(trunc(n["title"], w - 2), w - 2) + "]", col, st in ("stalled", "running", "watch"))
    for (y0, es, groups, lanes) in strips:
        ybot = y0 + len(lanes)
        for lane, keys in enumerate(lanes):
            yl = y0 + lane
            for k in keys:
                for s, t in groups[k]:
                    sx, tx = geo[s][4], geo[t][4]
                    sy = geo[s][1] + (5 if nodes[s]["kind"] == "step" else 1 if nodes[s]["kind"] == "chip" else geo[s][3])
                    ln.vline(sx, sy, yl, attach_top=True); ln.hline(sx, tx, yl); ln.vline(tx, yl, ybot, attach_bottom=True)
        for s, t in es: cv.put(geo[t][4], ybot, "▼" if nodes[t]["kind"] != "dummy" else "│", EDGE)
    for i, n in nodes.items():
        if n["kind"] == "dummy":
            x, y, w, h, cx = geo[i]; ln.vline(cx, y - 1, y + h, attach_top=True, attach_bottom=True)
    for (x, y), b in ln.cells.items():
        if 0 <= y < cv.h and 0 <= x < cv.w and cv.cells[y][x][0] == " ": cv.cells[y][x] = (BITS.get(b, "│"), (EDGE, False))
    return cv, anim

def bar(n, cap, width=6):
    if not cap: return "▰" * width + " %d 次" % n
    k = max(0, min(width, round(width * n / cap)))
    return "▰" * k + "▱" * (width - k) + " %d/%d" % (n, cap)

def render(case, W, H, scroll):
    d = DATA[case]; h = d["header"]; cv = Canvas(W, H); y = 0
    cv.put(0, y, "Trace 看板 · " + d["name"], INK, True); y += 1
    keys = "[1] 演示  [2] Trace #1  [3] 简单用例   ↑↓ 逐行  fn+↑↓ 翻页  fn+←→ 顶/底   a 动效   q 退出"
    for x in range(W): cv.put(x, y, "═", DIM)
    cv.put(W - dw(keys) - 1, y, " " + keys, LABEL); y += 1
    def kv(k, v, color=INK):
        nonlocal y
        cv.put(0, y, pad(k, 10), LABEL); cv.put(10, y, trunc(v, W - 10), color); y += 1
    kv("阶段", h["stage"]); kv("阻塞", h["block"], 196 if ("无证据" in h["block"] or "失效" in h["block"]) else INK); kv("下一步", h["nxt"], 39)
    cv.put(0, y, pad("预算", 10), LABEL); x = 10
    for k, n, cap in h["budget"]:
        s = "%s %s" % (k, bar(n, cap)); cv.put(x, y, s, 208 if cap and n / cap >= 0.8 else INK); x += dw(s) + 3
    cv.put(x, y, "（合同 §5 上限；人次为自述）", DIM); y += 1
    kv("存疑", h["doubt"], 220); kv("外部证据", h["evidence"])
    for x in range(W): cv.put(x, y, "═", DIM)
    y += 1
    body, anim = draw_graph(d, W)
    avail = H - y - 1
    scroll = max(0, min(scroll, max(0, body.h - avail)))
    for i in range(avail):
        r = scroll + i
        if r < body.h: cv.cells[y + i] = body.cells[r]
    ly = H - 1; x = 0; cv.put(x, ly, "节点 ", LABEL); x += 5
    legend_anim = []
    for s, lab in (("done", "完成"), ("doneq", "自述未证"), ("running", "运行中"), ("ready", "下一步"), ("watch", "观察"), ("stalled", "卡住"), ("human", "待人类"), ("todo", "待做"), ("stale", "失效")):
        if s in ("running", "watch"):
            sw = "┌──┐"; cv.put(x, ly, sw + lab, C[s])
            legend_anim.append(([(x + k, ly, ch) for k, ch in enumerate(sw)], C[s], [])); x += dw(sw + lab) + 1
        else:
            t = "■" + lab; cv.put(x, ly, t, C[s]); x += dw(t) + 1
    cv.put(x + 1, ly, "[ ]=机器证据   连线=依赖", DIM)
    off = y - scroll
    vis = lambda cells: [(cx, cy + off, ch) for cx, cy, ch in cells if 0 <= cy - scroll < avail]
    anim = [(vis(b), col, vis(num)) for b, col, num in anim] + legend_anim
    return cv.render(), scroll, anim, avail

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dump", type=int); ap.add_argument("--width", type=int); ap.add_argument("--height", type=int)
    a = ap.parse_args()
    size = shutil.get_terminal_size((150, 52)); W = a.width or size.columns; H = a.height or size.lines
    if a.dump:
        lines, _, _, _ = render(a.dump, W, H, 0); print("\n".join(lines)); return
    case, scroll, animate = 1, 0, True
    fd = sys.stdin.fileno(); old = termios.tcgetattr(fd)
    resized = [True]; signal.signal(signal.SIGWINCH, lambda *_: resized.__setitem__(0, True))
    prev, dirty, phase, anim, avail = [], True, 0, [], 1
    try:
        tty.setcbreak(fd); sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
        while True:
            if resized[0]:
                size = shutil.get_terminal_size((150, 52)); W, H = size.columns, size.lines; resized[0] = False; prev = []; dirty = True; sys.stdout.write("\x1b[2J")
            if dirty:
                lines, scroll, anim, avail = render(case, W, H, scroll)
                out = [("\x1b[%d;1H%s\x1b[K" % (i + 1, ln)) for i, ln in enumerate(lines) if i >= len(prev) or prev[i] != ln]
                if out: sys.stdout.write("".join(out)); sys.stdout.flush()
                prev = lines; dirty = False
            if animate and anim:
                out = []
                for border, col, num in anim:
                    n = len(border)
                    for k, (x, y, ch) in enumerate(border):
                        hot = n and ((k - phase) % n) in (0, 1, 2, 3)
                        out.append("\x1b[%d;%dH\x1b[38;5;%dm%s%s\x1b[0m" % (y + 1, x + 1, BRIGHT if hot else col, "\x1b[1m" if hot else "", ch))
                    for (x, y, ch) in num:
                        out.append("\x1b[%d;%dH\x1b[38;5;%dm%s\x1b[0m" % (y + 1, x + 1, BRIGHT if (phase // 2) % 2 == 0 else DIM, ch))
                if out: sys.stdout.write("".join(out)); sys.stdout.flush()
                phase += 1
            r, _, _ = select.select([fd], [], [], 0.18 if (animate and anim) else 1.0)
            if not r: continue
            ch = os.read(fd, 16).decode(errors="ignore")
            if ch in ("q", "Q", "\x03"): break
            if ch in ("1", "2", "3"): case, scroll, dirty = int(ch), 0, True
            elif ch in ("a", "A"): animate, dirty = not animate, True
            elif ch in ("\x1b[B", "\x1bOB"): scroll += 1; dirty = True
            elif ch in ("\x1b[A", "\x1bOA"): scroll = max(0, scroll - 1); dirty = True
            elif ch in ("\x1b[6~",): scroll += max(1, avail - 2); dirty = True
            elif ch in ("\x1b[5~",): scroll = max(0, scroll - max(1, avail - 2)); dirty = True
            elif ch in ("\x1b[H", "\x1b[1~", "\x1bOH", "\x1b[7~"): scroll = 0; dirty = True
            elif ch in ("\x1b[F", "\x1b[4~", "\x1bOF", "\x1b[8~"): scroll += 99999; dirty = True
    finally:
        sys.stdout.write("\x1b[?25h\x1b[?1049l"); sys.stdout.flush(); termios.tcsetattr(fd, termios.TCSADRAIN, old)

if __name__ == "__main__":
    main()
