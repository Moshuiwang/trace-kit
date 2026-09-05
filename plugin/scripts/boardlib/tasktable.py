# -*- coding: utf-8 -*-
"""任务表解析（接口约定 §5）。归属：S-2。

    parse(text: str, path: str = "") -> TaskTable
        - `## ` 章节 → Section（标题去尾部括号说明）；Step 行 → Step（编号、勾选、标题、标签块、指针）
        - 无法解析的 `- [` 行进 unparsed；超限行进 overlong（只计数不截断）；绝不抛异常退出
    default_needs(table: TaskTable) -> None
        - 无 needs: 标签时按章节顺序补默认依赖：同章节上一条；章节首条＝上一（非空）章节末条
"""
from __future__ import annotations

import re
import unicodedata

from .model import Section, Step, StepType, TaskTable

SECTION_RE = re.compile(r"^## (.+?)\s*$")
STEP_RE = re.compile(r"^- \[( |x|X)\] (S-[0-9A-Za-z-]+|W0-\d+|[A-Z]-\d+(?:-\d+)?[a-z]?)\s+(.*)$")
CHECK_LINE_RE = re.compile(r"^\s*- \[")
TAG_BLOCK_RE = re.compile(r"\s*\[((?:t|needs|own|est):[^\[\]]*)\]\s*$")
TITLE_SPLIT_RE = re.compile(r"——| — |（")
PAREN_TAIL_RE = re.compile(r"\s*[（(][^（）()]*[）)]\s*$")
EST_RE = re.compile(r"^(\d+)([mh])$")

PR_RE = re.compile(r"PR #(\d+)")
MERGE_RE = re.compile(r"#(\d+) 合[入并]")
SHA_RE = re.compile(r"`([0-9a-f]{7,40})`")
COMMENT_RE = re.compile(r"issuecomment-(\d+)")
URL_RE = re.compile(r"https?://[^\s<>()（）\[\]`]+")

ID_MAX_CHARS = 6
TITLE_MAX_HAN = 18  # 18 个汉字 ＝ 36 列显示宽度
VALID_TYPES = {t.value for t in StepType}


def display_width(text: str) -> int:
    """东亚宽度：全角 / 宽字符计 2 列，组合字符计 0（与样稿 cw/dw 同口径）。"""
    width = 0
    for ch in text:
        if unicodedata.combining(ch) or ch == "️":
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def clean_section_title(title: str) -> str:
    """去掉章节标题尾部的括号说明（可多层）。"""
    title = title.strip()
    while True:
        stripped = PAREN_TAIL_RE.sub("", title)
        if stripped == title or not stripped:
            return title
        title = stripped


def parse_tags(block: str) -> dict:
    """标签块 `t:impl needs:S-1,S-2 own:x est:45m` → dict；四键全可选，未知键忽略。"""
    tags: dict = {}
    for token in block.split():
        if ":" not in token:
            continue
        key, _, value = token.partition(":")
        if key == "t":
            tags["t"] = value.strip()
        elif key == "needs":
            tags["needs"] = [x.strip() for x in re.split(r"[,、]", value) if x.strip()]
        elif key == "own":
            tags["own"] = value.strip()
        elif key == "est":
            tags["est"] = value.strip()
    return tags


def parse_est(text: str):
    """`45m` / `2h` → 分钟；其他一律无预估（None）。"""
    m = EST_RE.match(text or "")
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return n * 60 if unit == "h" else n


def split_title(body: str) -> tuple[str, str]:
    """编号后一句话到第一个 `——` / ` — ` / `（` 之前为标题；其后为指针区。"""
    m = TITLE_SPLIT_RE.search(body)
    if not m:
        return body.strip(), ""
    return body[: m.start()].strip(), body[m.start():].strip()


def extract_pointers(text: str) -> dict:
    prs: list[int] = []
    for pat in (PR_RE, MERGE_RE):
        for n in pat.findall(text):
            if int(n) not in prs:
                prs.append(int(n))
    shas: list[str] = []
    for sha in SHA_RE.findall(text):
        if sha not in shas:
            shas.append(sha)
    comments: list[int] = []
    for c in COMMENT_RE.findall(text):
        if int(c) not in comments:
            comments.append(int(c))
    urls: list[str] = []
    for u in URL_RE.findall(text):
        if u not in urls:
            urls.append(u)
    return {"prs": prs, "shas": shas, "comments": comments, "urls": urls}


def _parse_step(m: "re.Match[str]", line_no: int, section: int, raw: str) -> Step:
    checked = m.group(1) in ("x", "X")
    sid = m.group(2)
    body = m.group(3)
    tags: dict = {}
    tm = TAG_BLOCK_RE.search(body)
    if tm:
        tags = parse_tags(tm.group(1))
        body = body[: tm.start()].rstrip()
    title, _pointer_area = split_title(body)
    pointers = extract_pointers(body)
    stype = StepType(tags["t"]) if tags.get("t") in VALID_TYPES else StepType.IMPL
    return Step(
        id=sid, title=title, checked=checked, section=section, line_no=line_no, type=stype,
        needs=list(tags.get("needs", [])), owner=tags.get("own", ""), est_min=parse_est(tags.get("est", "")),
        prs=pointers["prs"], shas=pointers["shas"], comments=pointers["comments"], urls=pointers["urls"], raw=raw,
    )


def parse(text: str, path: str = "") -> TaskTable:
    sections: list[Section] = []
    unparsed: list[tuple[int, str]] = []
    overlong: list[tuple[int, str]] = []
    current: Section | None = None
    for line_no, line in enumerate((text or "").splitlines(), 1):
        sm = SECTION_RE.match(line)
        if sm:
            current = Section(index=len(sections), title=clean_section_title(sm.group(1)))
            sections.append(current)
            continue
        m = STEP_RE.match(line)
        if m and current is not None:
            step = _parse_step(m, line_no, current.index, line)
            current.steps.append(step)
            if len(step.id) > ID_MAX_CHARS:
                overlong.append((line_no, "%s 编号 %d 字符 > %d" % (step.id, len(step.id), ID_MAX_CHARS)))
            width = display_width(step.title)
            if width > TITLE_MAX_HAN * 2:
                overlong.append((line_no, "%s 标题 %d 列 > %d 汉字" % (step.id, width, TITLE_MAX_HAN)))
            continue
        if CHECK_LINE_RE.match(line):
            unparsed.append((line_no, line.strip()))
    table = TaskTable(path=path, sections=sections, unparsed=unparsed, overlong=overlong)
    default_needs(table)
    return table


def default_needs(table: TaskTable) -> None:
    """无 needs: 标签的 Step 补默认依赖；显式标签原样保留。"""
    last_of_prev: str | None = None
    for section in table.sections:
        prev_in_section: str | None = None
        for step in section.steps:
            if not step.needs:
                if prev_in_section is not None:
                    step.needs = [prev_in_section]
                elif last_of_prev is not None:
                    step.needs = [last_of_prev]
            prev_in_section = step.id
        if section.steps:
            last_of_prev = section.steps[-1].id
