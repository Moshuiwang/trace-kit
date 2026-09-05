# -*- coding: utf-8 -*-
"""渲染（接口约定 §8）。归属：S-3。

出处：trace-kit #12 v2 十二条裁定与 v3 增补第 1 / 2 条；https://github.com/Moshuiwang/lingxi/issues/578（模块三行、边框档位）；
决策清单 D-1 / D-2 / D-7。画布、连线、分层排版从样稿 `docs/board-tui-sample.py`（分支 sample/board-v0）演化而来，运行期不依赖样稿。

对外：
    frame(board, view, W, H, scroll=0, phase=0, note="") -> (lines, anim, avail)
        lines：H 行 ANSI 文本；anim：动效单元 [(border_cells, color, num_cells)]，坐标为屏幕绝对坐标；avail：正文可视行数。
    dump(board, view, W=150, H=52, why=False) -> str      纯文本，无 ANSI，每行右侧无空白；why=True 追加证据链表。
    scroll_limit(board, view, W, H) -> int                 该视图最大滚动行数（tui 夹取 scroll 用）。
三个入口都先调 board.validate()。

排版要点：
    - 简易版：节点＝模块（任务表 `##` 章节），5 行框；层间连线压成 1 行（只有需要横向换道的边才多占行）；同层模块并排；
      W ≥ 120 每行最多 5 张、否则 3 张；6 模块链在 150×52 一屏不滚动（6×5 + 5×1 = 35 行 ≤ 41 行正文）。
    - 复杂版：节点＝Step 卡片（5 行）＋证据小节点（1 行方括号），沿用样稿层间 3 行（竖线 / 箭头 / 空行），允许滚动。
    - 边框四档（D-1）：未审 ┌─┐│└┘；1 轮 ╔═╗║╚╝；2 轮 ┏━┓┃┗┛；3 轮 ┏╍┓┇┗┛；3 轮以上同 3 轮＋标题 ⟲N（208 色加粗）。
    - 颜色表示状态；来源角标（实 / 报 / 推）240 色；「未知」245 色斜体；卡片文字超宽只裁不加省略号（超限由头部计数）。
"""
from __future__ import annotations

import re
import unicodedata

from .model import GRADE_MARK, Grade, Status, Tier, beijing

# ---------- 颜色与常量（沿用样稿 C 表） ----------
C = {
    Status.TODO: 245, Status.READY: 39, Status.RUNNING: 75, Status.WATCH: 208, Status.STALLED: 196,
    Status.HUMAN: 135, Status.DONE: 71, Status.DONEQ: 220, Status.STALE: 240, Status.UNKNOWN: 245,
}
EDGE, BRIGHT, INK, LABEL, DIM = 245, 231, 252, 245, 240
WARN, HOT, RED, BLUE, GREEN, UNKNOWN_COLOR = 220, 208, 196, 39, 71, 245
ANIM = {Status.RUNNING, Status.WATCH}
BOLD_STATUS = {Status.STALLED, Status.READY, Status.RUNNING, Status.WATCH}
TYPE = {"impl": "实施", "review": "审核", "gate": "门禁", "human": "人工", "deploy": "发布", "research": "研究", "contract": "合同"}
BORDER = {
    Tier.NONE: "┌─┐│└┘", Tier.ONE: "╔═╗║╚╝", Tier.TWO: "┏━┓┃┗┛", Tier.THREE: "┏╍┓┇┗┛", Tier.MORE: "┏╍┓┇┗┛",
}
TIER_LABEL = {Tier.NONE: "未审", Tier.ONE: "1轮", Tier.TWO: "2轮", Tier.THREE: "3轮", Tier.MORE: "3轮+"}
STATUS_LEGEND = (
    (Status.DONE, "完成"), (Status.DONEQ, "自述未证"), (Status.RUNNING, "运行中"), (Status.READY, "下一步"),
    (Status.WATCH, "观察"), (Status.STALLED, "卡住"), (Status.HUMAN, "待人类"), (Status.TODO, "待做"),
    (Status.STALE, "失效"), (Status.UNKNOWN, "未知"),
)
KEYS_HINT = "v 视图  r 刷新  ↑↓ 逐行  PgUp/PgDn 翻页  Home/End 顶/底  a 动效  q 退出"
VIEW_LABEL = {"simple": "简易版", "complex": "复杂版"}
HEADER_ROWS = 10          # 标题行、视图/按键行、七项（阶段 / 五级阶段 / 阻塞 / 下一步 / 预算 / 存疑 / 外部证据）、分隔线
GAP = 2                   # 同层节点间距
SIMPLE_BOX_MAX, COMPLEX_BOX_MAX, BOX_MIN = 60, 34, 20
CHIP_MIN, CHIP_MAX = 10, 46
MARK_RE = re.compile(r"\d+[实报推]|未知")


# ---------- 显示宽度 ----------
def cw(ch: str) -> int:
    if unicodedata.combining(ch) or ch == "\ufe0f":
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def dw(s: str) -> int:
    return sum(cw(c) for c in s)


def fit(s: str, n: int) -> str:
    """裁到 n 显示列，不加省略号（超限由头部计数）。"""
    if dw(s) <= n:
        return s
    out, w = "", 0
    for c in s:
        k = cw(c)
        if w + k > n:
            break
        out += c
        w += k
    return out


def pad(s: str, n: int) -> str:
    return s + " " * max(0, n - dw(s))


def wrap2(s: str, n: int) -> list[str]:
    """按显示宽度折成两行；第二行超宽只裁不加省略号。"""
    lines, cur, w = [], "", 0
    for c in s:
        k = cw(c)
        if w + k > n and not lines:
            lines.append(cur)
            cur, w = "", 0
        cur += c
        w += k
    lines.append(cur)
    lines = [fit(x, n) for x in lines[:2]]
    while len(lines) < 2:
        lines.append("")
    return lines


def short_title(title: str) -> str:
    """章节标题去掉尾部括号说明（与任务表解析口径一致）。"""
    return re.sub(r"\s*[（(][^（）()]*[）)]\s*$", "", title or "").strip()


# ---------- 画布 ----------
class Canvas:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.cells = [[(" ", None) for _ in range(w)] for _ in range(h)]

    def put(self, x, y, s, color=None, bold=False, italic=False):
        if y < 0 or y >= self.h or not s:
            return
        st = (color, bold, italic)
        row = self.cells[y]
        for c in s:
            k = cw(c)
            if k == 0:
                continue
            if x >= self.w:
                break
            if x >= 0:
                if row[x][0] == "" and x > 0:      # 覆盖了宽字符的右半：把左半也清掉，避免错位
                    row[x - 1] = (" ", None)
                elif x + 1 < self.w and row[x + 1][0] == "" and row[x][0] != "":   # 覆盖了宽字符的左半：清掉右半
                    row[x + 1] = (" ", None)
                row[x] = (c, st)
                if k == 2:
                    if x + 1 < self.w:
                        if x + 2 < self.w and row[x + 2][0] == "" and row[x + 1][0] != "":
                            row[x + 2] = (" ", None)
                        row[x + 1] = ("", st)
                    else:
                        row[x] = (" ", None)       # 宽字符放不下：留空
            x += k

    def style(self, x, y, color=None, bold=False, italic=False):
        if 0 <= y < self.h and 0 <= x < self.w and self.cells[y][x][0] != "":
            self.cells[y][x] = (self.cells[y][x][0], (color, bold, italic))

    @staticmethod
    def render_row(row) -> str:
        out, cur = [], None
        for ch, st in row:
            if ch == "":
                continue
            if st != cur:
                out.append("\x1b[0m")
                if st:
                    col, bold, italic = st
                    if col is not None:
                        out.append("\x1b[38;5;%dm" % col)
                    if bold:
                        out.append("\x1b[1m")
                    if italic:
                        out.append("\x1b[3m")
                cur = st
            out.append(ch)
        return "".join(out) + "\x1b[0m"

    @staticmethod
    def plain_row(row) -> str:
        return "".join(ch for ch, _ in row).rstrip()

    def render(self) -> list[str]:
        return [self.render_row(r) for r in self.cells]

    def plain(self) -> list[str]:
        return [self.plain_row(r) for r in self.cells]


BITS = {1: "╵", 2: "╷", 3: "│", 4: "╴", 8: "╶", 12: "─", 10: "┌", 6: "┐", 9: "└", 5: "┘", 14: "┬", 13: "┴", 11: "├", 7: "┤", 15: "┼"}


class Lines:
    def __init__(self):
        self.cells = {}

    def add(self, x, y, bits):
        self.cells[(x, y)] = self.cells.get((x, y), 0) | bits

    def vline(self, x, y1, y2, attach_top=False, attach_bottom=False):
        for y in range(y1, y2 + 1):
            self.add(x, y, (1 if (y > y1 or attach_top) else 0) | (2 if (y < y2 or attach_bottom) else 0))

    def hline(self, x1, x2, y):
        a, b = min(x1, x2), max(x1, x2)
        for x in range(a, b + 1):
            self.add(x, y, (4 if x > a else 0) | (8 if x < b else 0))


def put_marked(cv, x, y, text, color=INK, bold=False, italic=False):
    """写一段文字：数字后的来源角标（实 / 报 / 推）用暗色，「未知」用 245 斜体。返回写完后的 x。"""
    pos = 0
    for m in MARK_RE.finditer(text):
        if m.start() > pos:
            seg = text[pos:m.start()]
            cv.put(x, y, seg, color, bold, italic)
            x += dw(seg)
        tok = m.group(0)
        if tok == "未知":
            cv.put(x, y, tok, UNKNOWN_COLOR, False, True)
        else:
            cv.put(x, y, tok[:-1], color, bold, italic)
            cv.put(x + dw(tok[:-1]), y, tok[-1], DIM, False, False)
        x += dw(tok)
        pos = m.end()
    if pos < len(text):
        seg = text[pos:]
        cv.put(x, y, seg, color, bold, italic)
        x += dw(seg)
    return x


# ---------- 文案 ----------
def dur_text(actual, elapsed, est, status) -> str:
    """「实际或已跑 / 预估」（#12 v2 第 6 条；https://github.com/Moshuiwang/lingxi/issues/581：无 est 标签显示 /─）。"""
    if actual is not None:
        left = str(actual)
    elif elapsed is not None:
        left = str(elapsed)
    elif status in (Status.DONE, Status.DONEQ):
        left = "?"
    else:
        left = ""
    return "%s/%s" % (left, est if est is not None else "─")


def _val_text(v) -> str:
    try:
        return v.text()
    except AttributeError:
        return str(v)


def rounds_text(r) -> str:
    """rounds_line 为空时的兜底：审 N · 外 N · 修 N · CI 红N 绿N。"""
    return "审 %s · 外 %s · 修 %s · CI 红%s 绿%s" % (
        _val_text(r.review), _val_text(r.external), _val_text(r.fixpack), _val_text(r.ci_red), _val_text(r.ci_green))


def _review_n(mv) -> str:
    v = mv.rounds.review
    if getattr(v, "available", True):
        try:
            return str(int(v.value))
        except (TypeError, ValueError):
            pass
    return ">3"


def stage_text(st):
    """五级阶段一项：(文字, 颜色, 斜体)。configured=False → 未配置；available=False → 未知。"""
    if not st.configured:
        return "未配置", DIM, False
    if not st.value.available:
        return "未知", UNKNOWN_COLOR, True
    return ("是", GREEN, False) if st.value.value else ("否", LABEL, False)


def budget_text(label, val, cap):
    """预算条：(文字, 颜色)。自报数不参与超支判断（https://github.com/Moshuiwang/lingxi/issues/581）。"""
    if not getattr(val, "available", True):
        return "%s 未知" % label, INK
    mark = GRADE_MARK.get(getattr(val, "grade", Grade.MEASURED), "")
    try:
        n = int(val.value)
    except (TypeError, ValueError):
        return "%s %s%s" % (label, val.value, mark), INK
    if cap:
        k = max(0, min(6, round(6 * n / cap)))
        over = n / cap >= 0.8 and val.grade != Grade.REPORTED
        return "%s %s%s %d%s/%d" % (label, "▰" * k, "▱" * (6 - k), n, mark, cap), (HOT if over else INK)
    return "%s ▰▰▰▰▰▰ %d%s 次" % (label, n, mark), INK


# ---------- 图：节点、分层、排版 ----------
def _nodes_simple(board):
    nodes, order = {}, []
    for k, mv in enumerate(board.modules):
        nid = "M%d" % k
        nodes[nid] = dict(id=nid, kind="module", status=mv.status, needs=["M%d" % j for j in mv.needs], mv=mv)
        order.append(nid)
    return nodes, order


def _nodes_complex(board):
    nodes, order, sid_of = {}, [], {}
    for sv in board.steps:
        sid = sv.step.id
        while sid in nodes:
            sid += "'"
        sid_of.setdefault(sv.step.id, sid)
        nodes[sid] = dict(id=sid, kind="step", status=sv.status, needs=[], sv=sv)
        order.append(sid)
        if sv.chip:
            cid = "E:" + sid
            nodes[cid] = dict(id=cid, kind="chip", status=sv.chip_status, needs=[sid], title=sv.chip)
            order.append(cid)
    for sv in board.steps:
        sid = sid_of[sv.step.id]
        needs = []
        for p in sv.step.needs:
            pid = sid_of.get(p)
            if pid is None or pid == sid:
                continue
            needs.append("E:" + pid if ("E:" + pid) in nodes else pid)
        nodes[sid]["needs"] = needs
    return nodes, order


def _layers(nodes, order):
    """最长路径分层；遇环忽略回边。"""
    layer, state = {}, {}

    def L(i):
        if i in layer:
            return layer[i]
        if state.get(i) == 1:
            return -1
        state[i] = 1
        ps = [L(p) for p in nodes[i]["needs"] if p in nodes]
        ps = [p for p in ps if p >= 0]
        layer[i] = (max(ps) + 1) if ps else 0
        state[i] = 2
        return layer[i]

    for i in order:
        L(i)
    return layer


def _wrap_rows(nodes, order, layer, per_row):
    """同层卡片超过 per_row 张时折成多行（小节点不计数）。"""
    rows = []
    if not layer:
        return rows
    for lv in range(max(layer.values()) + 1):
        ids = [i for i in order if layer[i] == lv]
        chunk, cards = [], 0
        for i in ids:
            is_card = nodes[i]["kind"] in ("step", "module")
            if is_card and cards >= per_row:
                rows.append(chunk)
                chunk, cards = [], 0
            chunk.append(i)
            cards += 1 if is_card else 0
        rows.append(chunk)
    return rows


def _build_graph(nodes, order, per_row):
    layer0 = _layers(nodes, order)
    rows = _wrap_rows(nodes, order, layer0, per_row)
    layer = {i: r for r, ids in enumerate(rows) for i in ids}
    edges, dummies = [], {}
    for i in order:
        for p in nodes[i]["needs"]:
            if p not in layer:
                continue
            d = layer[i] - layer[p]
            if d <= 0:
                continue
            if d == 1:
                edges.append((p, i))
                continue
            prev = p
            for k in range(layer[p] + 1, layer[i]):
                did = "·%s→%s·%d" % (p, i, k)
                dummies[did] = k
                edges.append((prev, did))
                prev = did
            edges.append((prev, i))
    for did, k in dummies.items():
        nodes[did] = dict(id=did, kind="dummy", status=Status.TODO, needs=[])
        rows[k].append(did)
        layer[did] = k
    return edges, rows, layer


def layout(nodes, order, W, compact):
    per_row = 5 if W >= 120 else 3
    edges, rows, layer = _build_graph(nodes, order, per_row)
    preds = {}
    for s, t in edges:
        preds.setdefault(t, []).append(s)
    posidx = {}
    for r, ids in enumerate(rows):
        if r > 0:
            orig = {i: k for k, i in enumerate(ids)}

            def bc(i):
                ps = [p for p in preds.get(i, []) if p in posidx]
                return (sum(posidx[p] for p in ps) / len(ps)) if ps else 1e9

            ids.sort(key=lambda i: (bc(i), orig[i]))
        for k, i in enumerate(ids):
            posidx[i] = k

    def w0(i, bw):
        kind = nodes[i]["kind"]
        if kind in ("step", "module"):
            return bw
        if kind == "chip":
            return min(max(dw(nodes[i]["title"]) + 2, CHIP_MIN), CHIP_MAX)
        return 1

    box_w = SIMPLE_BOX_MAX if compact else COMPLEX_BOX_MAX
    card_rows = [ids for ids in rows if any(nodes[i]["kind"] in ("step", "module") for i in ids)]
    while box_w > BOX_MIN and any(sum(w0(i, box_w) for i in ids) + GAP * (len(ids) - 1) > W - 2 for ids in card_rows):
        box_w -= 1
    chip_cap = {}
    for ids in rows:
        chips = [i for i in ids if nodes[i]["kind"] == "chip"]
        if not chips:
            continue
        room = W - 2 - GAP * (len(ids) - 1) - sum(w0(i, box_w) for i in ids if nodes[i]["kind"] != "chip")
        if sum(w0(i, box_w) for i in chips) > room:
            for i in chips:
                chip_cap[i] = max(CHIP_MIN, room // len(chips))

    def width_of(i):
        return min(w0(i, box_w), chip_cap[i]) if i in chip_cap else w0(i, box_w)

    row_h = [max([5 if nodes[i]["kind"] in ("step", "module") else 1 for i in ids] + [1]) for ids in rows]
    geo = {}
    for r, ids in enumerate(rows):
        real = [i for i in ids if nodes[i]["kind"] != "dummy"]
        dums = [i for i in ids if nodes[i]["kind"] == "dummy"]
        total = sum(width_of(i) for i in real) + GAP * (len(real) - 1)
        x, desired = max(0, (W - total) // 2), {}
        for i in real:                                   # 期望位置：前驱重心正下方；无前驱则居中排布
            ps = [p for p in preds.get(i, []) if p in geo]
            desired[i] = (int(round(sum(geo[p][4] for p in ps) / len(ps))) - width_of(i) // 2) if ps else x
            x += width_of(i) + GAP
        pos = _pack_row(real, desired, width_of, W)
        for i in real:
            geo[i] = [pos[i], 0, width_of(i), row_h[r], pos[i] + width_of(i) // 2]
        taken = [(geo[i][0] - 1, geo[i][0] + geo[i][2] + 1) for i in real]
        used = set()
        for d in dums:                                   # 穿层虚节点：尽量竖直穿过前驱正下方的空列
            ps = [p for p in preds.get(d, []) if p in geo]
            col = _free_col(geo[ps[0]][4] if ps else W // 2, taken, used, W)
            used.add(col)
            geo[d] = [col, 0, 1, row_h[r], col]
    rowset = [set(ids) for ids in rows]

    def strip_plan(r):
        es = [(s, t) for s, t in edges if s in rowset[r] and t in rowset[r + 1]]
        srcs = {s for s, _ in es}
        tgts = {t for _, t in es}
        by_t = len(tgts) <= len(srcs)
        groups = {}
        for s, t in es:
            groups.setdefault(t if by_t else s, []).append((s, t))
        items, straight = [], []
        for k, ges in groups.items():
            xs = [geo[s][4] for s, _ in ges] + [geo[t][4] for _, t in ges]
            if compact and min(xs) == max(xs):
                straight.append(k)
                continue
            items.append((min(xs), max(xs), k))
        items.sort()
        lanes = []
        for a, b, k in items:
            for lane in lanes:
                if lane[0] + 2 < a:
                    lane[0] = b
                    lane[1].append(k)
                    break
            else:
                lanes.append([b, [k]])
        return es, groups, [ln[1] for ln in lanes], straight

    y, strips = 0, []
    for r, ids in enumerate(rows):
        for i in ids:
            geo[i][1] = y
        y += row_h[r]
        if r + 1 < len(rows):
            es, groups, lanes, straight = strip_plan(r)
            strips.append((y, es, groups, lanes, straight))
            y += len(lanes) + (1 if compact else 2)
    return edges, rows, geo, strips, y


def _pack_row(ids, desired, width_of, W):
    """按期望位置排一行：互不重叠者各就各位；重叠者合成一簇、簇按成员期望中心的均值居中；最后夹进 [0, W]。"""
    order = sorted(ids, key=lambda i: (desired[i], ids.index(i)))
    clusters = []                                    # [x, 宽, 成员, 期望中心之和]
    for i in order:
        w = width_of(i)
        clusters.append([desired[i], w, [i], desired[i] + w // 2])
        while len(clusters) > 1 and clusters[-2][0] + clusters[-2][1] + GAP > clusters[-1][0]:
            a, b = clusters.pop(), clusters.pop()
            members = b[2] + a[2]
            width = sum(width_of(m) for m in members) + GAP * (len(members) - 1)
            centers = b[3] + a[3]
            clusters.append([int(round(centers / len(members))) - width // 2, width, members, centers])
    pos, prev_end = {}, -GAP
    for c in clusters:
        x = int(round(max(c[0], prev_end + GAP, 0)))
        for m in c[2]:
            pos[m] = x
            x += width_of(m) + GAP
        prev_end = x - GAP
    overflow = prev_end - W
    if overflow > 0 and pos:
        shift = min(overflow, min(pos.values()))
        for m in pos:
            pos[m] -= shift
    return pos


def _free_col(want, taken, used, W):
    def ok(c):
        return 0 <= c < W and c not in used and not any(a <= c < b for a, b in taken)

    for d in range(W):
        for c in (want - d, want + d):
            if ok(c):
                return c
    return max(0, min(W - 1, want))


# ---------- 画节点 ----------
def _title_row(cv, x, y, w, tl, hz, tr, left_text, tag, dur, col, bold, dur_color, anim_border):
    """卡片标题行：`tl hz 文字 [tag] hz…hz dur hz tr`；返回 (tag 单元格集合, dur 单元格集合)。"""
    right = (" " + dur + " " + hz + tr) if dur else tr
    fixed = dw(tl + hz + " ") + dw(" ") + dw(right) + (dw(tag) + 1 if tag else 0)
    left_text = fit(left_text, max(0, w - fixed))
    cx = x
    cv.put(cx, y, tl + hz + " ", col, bold)
    cx += 3
    cv.put(cx, y, left_text, col, bold)
    cx += dw(left_text)
    tag_cells = set()
    if tag:
        cv.put(cx, y, " ", col)
        cv.put(cx + 1, y, tag, HOT, True)
        tag_cells = set(range(cx + 1, cx + 1 + dw(tag)))
        cx += 1 + dw(tag)
    cv.put(cx, y, " ", col)
    cx += 1
    rx = x + w - dw(right)
    cv.put(cx, y, hz * max(0, rx - cx), col, bold)
    dur_cells = set()
    if dur:
        cv.put(rx, y, " ", col)
        cv.put(rx + 1, y, dur, dur_color, bold)
        dur_cells = set(range(rx + 1, rx + 1 + dw(dur)))
        cv.put(rx + 1 + dw(dur), y, " " + hz + tr, col, bold)
    else:
        cv.put(x + w - 1, y, tr, col, bold)
    if anim_border is not None:
        skip = tag_cells | dur_cells
        anim_border.extend((xx, y, cv.cells[y][xx][0]) for xx in range(x, x + w) if xx not in skip)
    return tag_cells, dur_cells


def _box_anim(cv, x, y, w, border_top, col, dur_cells, anim):
    border = list(border_top)
    border += [(x + w - 1, yy, cv.cells[yy][x + w - 1][0]) for yy in (y + 1, y + 2, y + 3)]
    border += [(xx, y + 4, cv.cells[y + 4][xx][0]) for xx in range(x + w - 1, x - 1, -1)]
    border += [(x, yy, cv.cells[yy][x][0]) for yy in (y + 3, y + 2, y + 1)]
    num = []
    for xx in sorted(dur_cells):
        ch = cv.cells[y][xx][0]
        if ch == "/":
            break
        num.append((xx, y, ch))
    anim.append(([b for b in border if b[2] != ""], col, num))


def _text_style(status):
    if status == Status.STALE:
        return DIM, False
    if status == Status.UNKNOWN:
        return UNKNOWN_COLOR, True
    return INK, False


def draw_module(cv, x, y, w, mv, anim):
    st, tier = mv.status, mv.tier
    col = C[st]
    tl, hz, tr, vt, bl, br = BORDER[tier]
    bold = st in BOLD_STATUS
    tag = ("⟲%s" % _review_n(mv)) if tier == Tier.MORE else ""
    dur = dur_text(mv.actual_min, mv.elapsed_min, mv.est_min, st)
    dur_color = 250 if (st in ANIM or st == Status.STALLED) else DIM
    border_top = [] if st in ANIM else None
    _, dur_cells = _title_row(cv, x, y, w, tl, hz, tr, short_title(mv.section.title), tag, dur, col, bold, dur_color, border_top)
    tcol, ital = _text_style(st)
    inner = w - 4
    lines = (mv.what or "", mv.rounds_line or rounds_text(mv.rounds), mv.evidence_line or "")
    for k, line in enumerate(lines, 1):
        cv.put(x, y + k, vt, col)
        cv.put(x + 1, y + k, " " * (w - 2), None)
        put_marked(cv, x + 2, y + k, fit(line, inner), tcol, False, ital)
        cv.put(x + w - 1, y + k, vt, col)
    cv.put(x, y + 4, bl + hz * (w - 2) + br, col)
    if border_top is not None:
        _box_anim(cv, x, y, w, border_top, col, dur_cells, anim)


def draw_step(cv, x, y, w, sv, anim):
    st = sv.status
    col = C[st]
    tl, hz, tr, vt, bl, br = BORDER[Tier.NONE]
    bold = st in BOLD_STATUS
    step = sv.step
    head = "%s %s" % (step.id, TYPE.get(getattr(step.type, "value", str(step.type)), ""))
    dur = dur_text(sv.actual_min, sv.elapsed_min, sv.est_min, st)
    dur_color = 250 if (st in ANIM or st == Status.STALLED) else DIM
    border_top = [] if st in ANIM else None
    _, dur_cells = _title_row(cv, x, y, w, tl, hz, tr, head, "", dur, col, bold, dur_color, border_top)
    tcol, ital = _text_style(st)
    inner = w - 4
    t1, t2 = wrap2(step.title, inner)
    for k, line in ((1, t1), (2, t2)):
        cv.put(x, y + k, vt, col)
        cv.put(x + 1, y + k, " " * (w - 2), None)
        cv.put(x + 2, y + k, line, tcol, False, ital)
        cv.put(x + w - 1, y + k, vt, col)
    cv.put(x, y + 3, vt, col)
    cv.put(x + 1, y + 3, " " * (w - 2), None)
    sub = " · ".join(s for s in (getattr(step, "owner", ""),) if s)
    cx = x + 2
    if sub:
        sub = fit(sub, inner)
        cv.put(cx, y + 3, sub, DIM)
        cx += dw(sub)
    if sv.rework:
        mark = fit((" " if sub else "") + "↺重审来源", max(0, x + w - 2 - cx))
        cv.put(cx, y + 3, mark, HOT)
    cv.put(x + w - 1, y + 3, vt, col)
    cv.put(x, y + 4, bl + hz * (w - 2) + br, col)
    if border_top is not None:
        _box_anim(cv, x, y, w, border_top, col, dur_cells, anim)


def draw_chip(cv, x, y, w, node):
    st = node["status"]
    cv.put(x, y, "[" + pad(fit(node["title"], w - 2), w - 2) + "]", C[st], st in (Status.STALLED, Status.RUNNING, Status.WATCH), st == Status.UNKNOWN)


def draw_graph(board, view, W):
    """正文画布：返回 (Canvas, anim, 正文高度)。"""
    compact = view == "simple"
    nodes, order = _nodes_simple(board) if compact else _nodes_complex(board)
    edges, rows, geo, strips, H = layout(nodes, order, W, compact)
    cv, ln, anim = Canvas(W, max(H, 1)), Lines(), []
    for i, (x, y, w, h, cx) in geo.items():
        n = nodes[i]
        if n["kind"] == "module":
            draw_module(cv, x, y, w, n["mv"], anim)
        elif n["kind"] == "step":
            draw_step(cv, x, y, w, n["sv"], anim)
        elif n["kind"] == "chip":
            draw_chip(cv, x, y, w, n)

    def bottom(s):
        kind = nodes[s]["kind"]
        return geo[s][1] + (5 if kind in ("step", "module") else 1 if kind == "chip" else geo[s][3])

    for (y0, es, groups, lanes, straight) in strips:
        ybot = y0 + len(lanes)
        for lane, keys in enumerate(lanes):
            yl = y0 + lane
            for k in keys:
                for s, t in groups[k]:
                    sx, tx = geo[s][4], geo[t][4]
                    ln.vline(sx, bottom(s), yl, attach_top=True)
                    ln.hline(sx, tx, yl)
                    ln.vline(tx, yl, ybot, attach_bottom=True)
        for k in straight:
            for s, t in groups[k]:
                ln.vline(geo[s][4], bottom(s), ybot, attach_top=True, attach_bottom=True)
        for s, t in es:
            cv.put(geo[t][4], ybot, "▼" if nodes[t]["kind"] != "dummy" else "│", EDGE)
    for i, n in nodes.items():
        if n["kind"] == "dummy":
            x, y, w, h, cx = geo[i]
            ln.vline(cx, y - 1, y + h, attach_top=True, attach_bottom=True)
    for (x, y), b in ln.cells.items():
        if 0 <= y < cv.h and 0 <= x < cv.w and cv.cells[y][x][0] == " ":
            cv.cells[y][x] = (BITS.get(b, "│"), (EDGE, False, False))
    return cv, anim, H


# ---------- 头部、图例、整帧 ----------
def _legend_rows(W, view):
    """图例：[(段列表)]，每段 (文字, 颜色, 是否流动框)；按宽度流式换行（150 列一行，75 列两行）。"""
    segs = [("节点", LABEL, False)]
    for st, lab in STATUS_LEGEND:
        segs.append((("┌──┐" if st in ANIM else "■") + lab, C[st], st in ANIM))
    segs.append(("边框", LABEL, False))
    for tier in Tier:
        tl, hz, tr = BORDER[tier][:3]
        segs.append((tl + hz + tr + ("⟲N " if tier == Tier.MORE else "") + TIER_LABEL[tier], INK, False))
    segs.append((("[ ]=机器证据 " if view == "complex" else "") + "连线=依赖", DIM, False))
    rows, cur, width = [], [], 0
    for seg in segs:
        w = dw(seg[0])
        if cur and width + 1 + w > W:
            rows.append(cur)
            cur, width = [], 0
        cur.append(seg)
        width += w + (1 if len(cur) > 1 else 0)
    if cur:
        rows.append(cur)
    return rows[:3]


def _draw_legend(cv, rows, y0, anim):
    for r, segs in enumerate(rows):
        y, x = y0 + r, 0
        for k, (text, color, flow) in enumerate(segs):
            if k:
                x += 1
            cv.put(x, y, text, color)
            if flow:
                anim.append(([(x + j, y, ch) for j, ch in enumerate("┌──┐")], color, []))
            x += dw(text)


def _draw_header(cv, board, view, W, scroll, limit, note):
    h = board.header
    right = "更新 " + beijing(board.generated_at) + ("  " + note if note else "")
    cv.put(W - dw(right), 0, right, DIM)
    title = fit("Trace 看板 · " + (h.title or ""), max(0, W - dw(right) - 1))
    cv.put(0, 0, title, INK, True)
    if h.warnings:
        warn = fit("  ⚠ " + " · ".join(h.warnings), max(0, W - dw(right) - 1 - dw(title)))
        cv.put(dw(title), 0, warn, WARN, True)
    y = 1
    for x in range(W):
        cv.put(x, y, "═", DIM)
    vlabel = " 视图 " + VIEW_LABEL[view] + " "
    cv.put(0, y, vlabel, INK, True)
    tail = KEYS_HINT
    if limit > 0:
        tail = "↕ %d/%d   %s" % (scroll, limit, tail)
    if dw(vlabel) + dw(tail) + 3 <= W:
        cv.put(W - dw(tail) - 1, y, " " + tail, LABEL)
    elif limit > 0:
        ind = " ↕ %d/%d " % (scroll, limit)
        cv.put(W - dw(ind), y, ind, LABEL)
    y = 2

    def kv(label, text, color=INK, bold=False, italic=False):
        nonlocal y
        cv.put(0, y, pad(label, 10), LABEL)
        put_marked(cv, 10, y, fit(text or "", W - 10), color, bold, italic)
        y += 1

    kv("阶段", h.stage)
    cv.put(0, y, pad("五级阶段", 10), LABEL)
    parts = [(st.label + " ",) + stage_text(st) for st in h.stages]
    need = sum(dw(a) + dw(b) for a, b, _, _ in parts)
    sep = " · " if need + 3 * max(0, len(parts) - 1) + 10 <= W else " "
    x = 10
    for k, (seg, text, color, ital) in enumerate(parts):
        if k:
            cv.put(x, y, sep, DIM)
            x += dw(sep)
        cv.put(x, y, seg, INK)
        x += dw(seg)
        cv.put(x, y, text, color, False, ital)
        x += dw(text)
    if not h.stages:
        cv.put(10, y, "未知", UNKNOWN_COLOR, False, True)
    y += 1
    block = h.block or ""
    kv("阻塞", block, RED if block and block not in ("无", "—", "-") else INK)
    kv("下一步", h.nxt, BLUE)
    cv.put(0, y, pad("预算", 10), LABEL)
    x = 10
    for label, val, cap in h.budget:
        text, color = budget_text(label, val, cap)
        if x + dw(text) > W:
            break
        x = put_marked(cv, x, y, text, color) + 3
    if not h.budget:
        cv.put(10, y, "无", DIM)
    y += 1
    kv("存疑", h.doubt, WARN)
    kv("外部证据", h.evidence)
    for x in range(W):
        cv.put(x, y, "═", DIM)
    return y + 1


def _check_view(view):
    if view not in VIEW_LABEL:
        raise ValueError("视图只能是 simple / complex：%r" % (view,))
    return view


def _compose(board, view, W, H, scroll, phase, note):
    """整帧画布：返回 (Canvas, anim, avail, scroll, limit)。"""
    board.validate()
    view = _check_view(view)
    W, H = max(20, int(W)), max(HEADER_ROWS + 2, int(H))
    body, banim, body_h = draw_graph(board, view, W)
    legend = _legend_rows(W, view)
    avail = max(1, H - HEADER_ROWS - len(legend))
    limit = max(0, body_h - avail)
    scroll = max(0, min(int(scroll), limit))
    cv = Canvas(W, H)
    y0 = _draw_header(cv, board, view, W, scroll, limit, note)
    for i in range(avail):
        r = scroll + i
        if r < body.h:
            cv.cells[y0 + i] = body.cells[r]
    anim = []
    off = y0 - scroll

    def vis(cells):
        return [(cx, cy + off, ch) for cx, cy, ch in cells if 0 <= cy - scroll < avail]

    for border, col, num in banim:
        border, num = vis(border), vis(num)
        if border or num:
            anim.append((border, col, num))
    _draw_legend(cv, legend, y0 + avail, anim)
    if phase > 0:
        for border, col, num in anim:
            n = len(border)
            for k, (x, y, ch) in enumerate(border):
                if n and ((k - phase) % n) in (0, 1, 2, 3):
                    cv.style(x, y, BRIGHT, True)
            for (x, y, ch) in num:
                cv.style(x, y, BRIGHT if (phase // 2) % 2 == 0 else DIM)
    return cv, anim, avail, scroll, limit


def frame(board, view, W, H, scroll=0, phase=0, note=""):
    cv, anim, avail, _, _ = _compose(board, view, W, H, scroll, phase, note)
    return cv.render(), anim, avail


def scroll_limit(board, view, W, H) -> int:
    _, _, _, _, limit = _compose(board, view, W, H, 0, 0, "")
    return limit


def why_table(board) -> str:
    rows = ["证据链（--why）：对象 | 状态 | 证据类型 | 来源 | 取值 | 取值时间（UTC+8） | 可得"]
    items = []
    for mv in board.modules:
        items.extend(mv.why)
    for sv in board.steps:
        items.extend(sv.why)
    items.extend(board.why)
    for w in items:
        ev = getattr(w.evidence, "value", w.evidence)
        rows.append("%s | %s | %s | %s | %s | %s | %s" % (
            w.subject, w.status, ev, w.source, w.value, beijing(w.at, "%Y-%m-%d %H:%M"), "是" if w.available else "否"))
    return "\n".join(r.rstrip() for r in rows) + "\n"


def dump(board, view, W=150, H=52, why=False) -> str:
    cv, _, _, _, _ = _compose(board, view, W, H, 0, 0, "")
    lines = cv.plain()
    while lines and not lines[-1]:
        lines.pop()
    text = "\n".join(lines) + "\n"
    if why:
        text += "\n" + why_table(board)
    return text
