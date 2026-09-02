#!/usr/bin/env python3
"""归属核对门禁：凡把某句规则的权威记成「产品合同要求」的行，都必须登记并逐字核对。

出处：lingxi https://github.com/Moshuiwang/lingxi/issues/238（2026-08-19 三路独立复查坐实两个绕过面）；验证：2026-08-19 起 185 个 PR。

散文约束挡不住「把自己的从紧要求错记成合同条款」这类笔误，只有把每一处"标注为合同"的
断言变成会核对、会变红的登记才挡得住。仓库里的归属多是**转述**而非逐字引用，程序判不了
语义，因此采用**登记制**，门禁只做机械的事：(1) 登记表引用的合同章节必须真实存在于
``docs/产品合同.md``；(2) 登记的那一行原文必须还能在源文件里**逐字**找到（防摘录过期还挂
在表里）；(3) 仓库里每一处含归属短语的行必须与登记表某一条**整行逐字相等**并按出现次数计
配额——子串匹配的两个绕过面（过短摘录覆盖住此后任何新增行；往已登记行后面追加从未核对
的新断言，旧摘录仍是新行的子串）由整行相等同时关闭；(4) 对不上合同正文、又不能擅自改写
归属的，登记为例外（强制带来源 Issue/PR、裁定日期、裁定人、理由），门禁**每一次运行**
（含判红那次）都可见地报出来，留给编排者与产品负责人裁定。

它证明的是「这句归属被人显式核对过一次、登记未过期、可被下一个人复核」，**不证明**转述
在语义上真的成立——那需要人读两边正文。这里换成你的：按示例逐条填写两张登记表。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DOCUMENT = REPOSITORY_ROOT / "docs" / "产品合同.md"

# 归属触发词是一条正则族而不是固定短语清单：「(产品合同｜合同) + 可选"明确" + 归属动词」覆盖
# 后缀写法（"合同要求""合同明确排除"……），「按/依据/根据 + 合同」覆盖前缀写法；新出现的归属
# 动词落在这两族里就会被自动捞到。不匹配裸的"合同"——仓库大量用它表示模块自身的接口/服务
# 合同，那不是在对产品合同文档做归属声明。
TRIGGER_PATTERN = re.compile(
    r"(?:产品合同|合同)(?:明确)?(?:要求|规定|明令|禁止|约定|条款|指出|依据|排除)"
    r"|(?:按|依据|根据)(?:产品)?合同"
)
# 「合同条款覆盖清单」是验收矩阵与 check_acceptance_matrix.py 自己的机制名字：在描述一个
# 已存在的治理机制，不是对某句具体规则做归属声明，单独排除这几个固定短语。
META_EXCLUDE_PATTERN = re.compile(r"合同条款覆盖清单|合同条款无断言覆盖|产品合同条款\s*→")
SCAN_SUFFIXES = (".py", ".md", ".sh", ".sql")
# H1-H3 都算合法的章节标题：H1（合同文档标题本身）用于引用合同整体而非某一节的归属。
HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
# 摘录长度下限：防止直接拿触发词本身（裸的"合同要求"四个字）当登记内容。
MIN_EXCERPT_LENGTH = 8
# 例外的「来源」必须是可点击追溯的 Issue/PR 编号，不接受任意字符串。
EXCEPTION_SOURCE_PATTERN = re.compile(r"^(Issue|PR) #\d+$")


class AttributionCheckError(ValueError):
    """扫描或解析失败——必须失败关闭，不能当作「没有归属断言」悄悄通过。"""


@dataclass(frozen=True)
class GroundedAttribution:
    """一条已核对的归属：``file`` 里逐字等于 ``line`` 的那一行，对应合同 ``section`` 一节。"""

    file: str
    line: str
    section: str


@dataclass(frozen=True)
class RegisteredException:
    """一条已登记但未核对通过的归属：不静默放行，携带来源与裁定信息，可见地报出来。"""

    file: str
    line: str
    source: str
    decided_on: str
    decided_by: str
    reason: str


# 登记表：``line`` 必须逐字等于源文件里那一行去除首尾空白后的内容——改动那一行（哪怕只加
# 一个字）都必须回来同步这里，这是刻意的。新增一条归属声明时，先核对它对应合同哪一节、把
# 整行原文和章节名登记进来；门禁的作用是挡住"忘了核对"，不是代替核对本身。
GROUNDED_ATTRIBUTIONS: tuple[GroundedAttribution, ...] = (
    # 示例（登记时去掉注释号）：
    # GroundedAttribution("docs/技术设计/架构.md", "凭据不进代码、日志与数据库（产品合同明令）。", "外部边界"),
)

# 已知例外：措辞源自具体 Issue/PR 的裁定（有留痕），但合同正文本身没有对应文字。
# 不静默放行、不擅自改写归属，登记来源与裁定信息，门禁通过与失败时都可见地报出来。
REGISTERED_EXCEPTIONS: tuple[RegisteredException, ...] = (
    # 示例（登记时去掉注释号）：
    # RegisteredException(
    #     "src/app/alerting.py", "# 告警不可用时主流程照常继续（Issue #1：合同要求主流程行为有明确定义）",
    #     "Issue #1", "2026-01-01", "产品负责人", "该句出自 Issue #1 的裁定，合同正文没有告警条款。",
    # ),
)


def excluded_paths() -> set[Path]:
    """合同文档本身是权威源，不对自己做归属核对；本脚本与它的单元测试的源码里大量出现触发词
    字面串（触发词定义、登记表示例、测试夹具），扫描自己等于在核对实现细节而不是产品事实。"""

    return {CONTRACT_DOCUMENT, Path(__file__).resolve(), REPOSITORY_ROOT / "tests" / "test_ci_scripts.py"}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPOSITORY_ROOT, check=True, capture_output=True, text=True
    )
    excluded = excluded_paths()
    paths = []
    for raw_path in result.stdout.split("\0"):
        if not raw_path or not raw_path.endswith(SCAN_SUFFIXES) or raw_path.startswith(".tmp/"):
            continue
        full_path = REPOSITORY_ROOT / raw_path
        if full_path not in excluded and full_path.is_file():
            paths.append(full_path)
    return paths


def contract_sections(text: str) -> set[str]:
    """解析合同文档的标题集合，跳过代码围栏与 HTML 注释块。

    只跳过代码围栏不够：编辑合同时把某一节临时注释掉是常见动作，若注释块里恰好留了一份
    同名标题，门禁会把这份"已经不是合同正文"的注释当成真实章节，核对照样判绿。
    """

    sections: set[str] = set()
    in_fence = False
    in_comment = False
    for line in text.splitlines():
        if in_comment:
            if "-->" not in line:
                continue
            in_comment = False
            line = line[line.index("-->") + 3 :]
        # 一行内可能有多段注释（含跨行注释的收尾）；逐个去掉自封闭的片段，剩余文本才拿去判断。
        while "<!--" in line:
            start = line.index("<!--")
            end_marker = line.find("-->", start)
            if end_marker == -1:
                line = line[:start]
                in_comment = True
                break
            line = line[:start] + line[end_marker + 3 :]
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        match = None if in_fence else HEADING.match(line)
        if match:
            sections.add(match.group(2))
    return sections


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return str(path)


def find_triggered_lines(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise AttributionCheckError(f"无法读取 {_display_path(path)}：{error}") from error
    hits = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        # 只挖掉元排除短语本身、再看剩下的文本是否还含触发词：一句话完全可以前半下断言、
        # 后半指向覆盖清单，"整行出现过元短语就整行跳过"会让真实断言随之静默消失。
        if TRIGGER_PATTERN.search(META_EXCLUDE_PATTERN.sub("", stripped)):
            hits.append((line_number, stripped))
    return hits


def _check_registry_shape(sections: set[str], failures: list[str]) -> None:
    for grounded in GROUNDED_ATTRIBUTIONS:
        if len(grounded.line) < MIN_EXCERPT_LENGTH:
            failures.append(f"登记表里 {grounded.file} 的登记行短于 {MIN_EXCERPT_LENGTH} 个字符，过短的登记容易被后续任意新增的同类短行意外撞上，请登记完整的行原文。")
        if grounded.section not in sections:
            failures.append(f"登记表里 {grounded.file} 的归属指向章节「{grounded.section}」，但产品合同文档里找不到这个标题（改名了，还是删除了？）")
    for exception in REGISTERED_EXCEPTIONS:
        if len(exception.line) < MIN_EXCERPT_LENGTH:
            failures.append(f"例外登记里 {exception.file} 的登记行短于 {MIN_EXCERPT_LENGTH} 个字符。")
        if not (exception.source and exception.decided_on and exception.decided_by):
            failures.append(f"例外登记 {exception.file} 缺少来源 Issue/PR、裁定日期或裁定人三项之一——例外必须能被追溯，不能只写理由。")
        elif not EXCEPTION_SOURCE_PATTERN.match(exception.source):
            failures.append(f"例外登记 {exception.file} 的来源 {exception.source!r} 不是「Issue #数字」或「PR #数字」这类可追溯的格式。")
        if exception.decided_on:
            try:
                date.fromisoformat(exception.decided_on)
            except ValueError:
                failures.append(f"例外登记 {exception.file} 的裁定日期 {exception.decided_on!r} 不是合法的 ISO 日期（YYYY-MM-DD）。")
        if not exception.reason.strip():
            failures.append(f"例外登记 {exception.file} 的 reason 是空字符串——例外必须写清楚为什么对不上合同正文。")


def evaluate() -> tuple[list[str], list[str], str]:
    """返回 (阻断性失败列表, 例外债务说明列表, 汇总信息)。

    例外债务在**任何**运行结果下都单独返回，调用方必须在成功与失败两条路径上都打印它。
    """

    try:
        contract_text = CONTRACT_DOCUMENT.read_text(encoding="utf-8")
    except OSError as error:
        raise AttributionCheckError(f"无法读取产品合同文档 {CONTRACT_DOCUMENT}：{error}") from error
    sections = contract_sections(contract_text)
    if not sections:
        raise AttributionCheckError("产品合同文档里一个标题都没解析到，无法核对归属")

    failures: list[str] = []
    _check_registry_shape(sections, failures)

    # 登记的行必须还能在源文件里逐字找到；同时按 (文件, 整行) 建立出现次数配额。
    entries = [("登记表登记", e) for e in GROUNDED_ATTRIBUTIONS] + [("例外登记", e) for e in REGISTERED_EXCEPTIONS]
    file_lines: dict[str, set[str] | None] = {}
    remaining_budget: dict[tuple[str, str], int] = {}
    for label, entry in entries:
        if entry.file not in file_lines:
            try:
                text = (REPOSITORY_ROOT / entry.file).read_text(encoding="utf-8")
                file_lines[entry.file] = {line.strip() for line in text.splitlines()}
            except (OSError, UnicodeDecodeError) as error:
                failures.append(f"登记表引用的文件读不出来：{entry.file}（{error}）")
                file_lines[entry.file] = None
        lines = file_lines[entry.file]
        if lines is not None and entry.line not in lines:
            failures.append(f"{label}的行已经在源文件里找不到了（逐字比对）：{entry.file} —— {entry.line!r}。原句被改动或删除时，请同步更新登记表。")
        remaining_budget[(entry.file, entry.line)] = remaining_budget.get((entry.file, entry.line), 0) + 1

    # 每一处归属短语都必须与登记表或例外表里的某一条整行逐字相等，且按出现次数核对：每条登记
    # 只能兑现登记时核对过的那一次出现，把已登记的整行复制到别处，多出来的那次要重新登记。
    triggered_total = 0
    for path in tracked_files():
        relative = _display_path(path)
        for line_number, line in find_triggered_lines(path):
            triggered_total += 1
            if remaining_budget.get((relative, line), 0) > 0:
                remaining_budget[(relative, line)] -= 1
                continue
            failures.append(
                f"{relative}:{line_number}：出现「合同要求」类归属短语但未登记（或已经超出登记表里这句原文的"
                f"出现次数配额）——{line!r}。请先核对它是否真的对应产品合同正文，再登记进 "
                "scripts/ci/check_contract_attribution.py 的 GROUNDED_ATTRIBUTIONS（对上了）或 "
                "REGISTERED_EXCEPTIONS（对不上、且不能擅自改写归属时）。"
            )

    exception_notes = [
        f"- {e.file}：{e.line!r}\n  来源：{e.source}（{e.decided_on}，{e.decided_by}）—— {e.reason}"
        for e in REGISTERED_EXCEPTIONS
    ]
    summary = (
        f"归属核对：扫描到 {triggered_total} 处「合同要求」类归属短语，{len(GROUNDED_ATTRIBUTIONS)} 条登记为"
        f"已核对对应合同正文，{len(REGISTERED_EXCEPTIONS)} 条登记为已知例外（未改写归属，待裁定）"
    )
    return failures, exception_notes, summary


def main(argv: list[str] | None = None) -> int:
    # 无任何可选参数——但仍要显式解析并拒绝未知参数；allow_abbrev=False 关掉前缀缩写匹配。
    parser = argparse.ArgumentParser(description="归属核对门禁", allow_abbrev=False)
    parser.parse_args(argv)
    try:
        failures, exception_notes, summary = evaluate()
    except AttributionCheckError as error:
        print(f"归属核对检查失败：{error}", file=sys.stderr)
        return 1
    if failures:
        print("归属核对检查失败：", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        if exception_notes:
            print("以下已登记例外仍然有效（与本次失败无关，一并报出）：", file=sys.stderr)
            print("\n".join(exception_notes), file=sys.stderr)
        return 1
    print(summary)
    if exception_notes:
        print("已知例外：")
        print("\n".join(exception_notes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
