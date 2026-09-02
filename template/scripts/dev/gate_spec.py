#!/usr/bin/env python3
"""从 CI 工作流 YAML 现读门禁的环境配方，供 `scripts/dev/check.sh` 一键复现。

出处：lingxi https://github.com/Moshuiwang/lingxi/issues/236（PR #233 漂移事故）；验证：5 个批次收口前「本机 full 绿」。

背景：上游一次 `Epic Full / gate` 报过 `ModuleNotFoundError`——根因是实施者本机虚拟环境
装了全套 extras，而门禁只装其中一组，同一棵树「本机全绿、CI 直接 ERROR」。修复很简单，
但发现它的唯一途径是把改动推上去让 CI 跑一次。

本文件解决的不是那次具体缺陷，而是让类似环境漂移能在本机复现：pip extras 组合与 Python
版本**只在 `.github/workflows/{ci,story}.yml` 里写一份**，本文件只读不抄——
`scripts/dev/check.sh` 不允许另起一份硬编码清单（「两处各写一份清单」迟早漂移）。
shellcheck 的版本锁在 pyproject.toml 的 `dev` 组里，CI 与本机都通过同一个 extras 取得，
因此不必再从工作流里读第二遍。

不使用 YAML 库：按锚点做正则解析、写法变了就直接失败，不为一个开发工具引入新依赖。
解析失败一律抛 `GateSpecError` 并说明原因，不安静地退回旧值——旧值退回等于本工具自己
制造出它要消灭的那类漂移。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
STORY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "story.yml"

_TOP_LEVEL_JOB_KEY = re.compile(r"^  [A-Za-z0-9_-]+:[ \t]*$")
_STEP_NAME = re.compile(r"^(\s*)- name:\s*(.+?)\s*$")
_RUN_LINE = re.compile(r"^(\s*)run:\s*(.*)$")
_PIP_INSTALL_EXTRAS = re.compile(r"install\s+'\.\[([^\]]+)\]'")
_PYTHON_VERSION = re.compile(r"python-version:\s*'([0-9]+\.[0-9]+)'")

# 两个 job 里安装依赖那一步的 step 名：工作流改了名字，这里必须跟着改，否则响亮失败。
GATE_INSTALL_STEP = "安装测试依赖"
FAST_INSTALL_STEP = "安装快速门禁依赖"


class GateSpecError(RuntimeError):
    """工作流结构变了、本文件的锚点没跟着更新——必须响亮失败，不能退回旧值。"""


def _job_block(text: str, job_name: str) -> str:
    """截出某个顶层 job 的文本块（从 `  <job>:` 到下一个同缩进 job key 之前）。"""

    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(rf"^  {re.escape(job_name)}:[ \t]*$", line):
            start = index
            break
    if start is None:
        raise GateSpecError(f"找不到顶层 job `{job_name}`：工作流结构可能已经变化")

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if _TOP_LEVEL_JOB_KEY.match(lines[index]):
            end = index
            break
    return "\n".join(lines[start:end])


def _step_block(job_text: str, step_name: str) -> str:
    """截出 job 内某个 step 的文本块（按 `- name:` 的缩进定位同级边界）。"""

    lines = job_text.splitlines()
    start = None
    indent = None
    for index, line in enumerate(lines):
        match = _STEP_NAME.match(line)
        if match and match.group(2).strip("'\"") == step_name:
            start = index
            indent = match.group(1)
            break
    if start is None:
        raise GateSpecError(f"找不到 step `{step_name}`：工作流结构可能已经变化")

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith(f"{indent}- name:"):
            end = index
            break
    return "\n".join(lines[start:end])


def _run_command_lines(step_text: str) -> list[str]:
    """提取 step 的 `run:` 命令，兼容单行与 `run: |` 块两种写法。"""

    lines = step_text.splitlines()
    for index, line in enumerate(lines):
        match = _RUN_LINE.match(line)
        if not match:
            continue
        indent, rest = match.group(1), match.group(2)
        if rest and rest not in ("|", ">"):
            return [rest.strip()]
        base_indent = len(indent)
        block: list[str] = []
        for later in lines[index + 1 :]:
            if later.strip() == "":
                continue
            later_indent = len(later) - len(later.lstrip(" "))
            if later_indent <= base_indent:
                break
            block.append(later.strip())
        if not block:
            raise GateSpecError("`run:` 块写法下没有找到任何命令行")
        return block
    raise GateSpecError("step 里找不到 `run:`")


def _pip_install_extras(command: str) -> list[str]:
    match = _PIP_INSTALL_EXTRAS.search(command)
    if not match:
        raise GateSpecError(f"这行命令不是预期的 `pip install '.[...]'` 形态：{command!r}")
    return [item.strip() for item in match.group(1).split(",") if item.strip()]


def _python_version(job_text: str) -> str:
    match = _PYTHON_VERSION.search(job_text)
    if not match:
        raise GateSpecError("job 里找不到 `python-version: 'X.Y'`")
    return match.group(1)


class JobSpec:
    """一个门禁 job 的环境配方：装哪些 extras、用哪个 Python 小版本。"""

    def __init__(self, *, extras: list[str], python_version: str) -> None:
        self.extras = extras
        self.python_version = python_version


def _parse_job(text: str, job_name: str, install_step: str) -> JobSpec:
    job = _job_block(text, job_name)
    install_cmd = _run_command_lines(_step_block(job, install_step))[0]
    return JobSpec(extras=_pip_install_extras(install_cmd), python_version=_python_version(job))


def parse_gate_spec(ci_yml_text: str) -> JobSpec:
    """解析 ci.yml 的 `gate` job（`Epic Full / gate`）。"""

    return _parse_job(ci_yml_text, "gate", GATE_INSTALL_STEP)


def parse_fast_spec(story_yml_text: str) -> JobSpec:
    """解析 story.yml 的 `fast` job（`Story / code fast`）。"""

    return _parse_job(story_yml_text, "fast", FAST_INSTALL_STEP)


def load_gate_spec() -> JobSpec:
    return parse_gate_spec(CI_WORKFLOW.read_text(encoding="utf-8"))


def load_fast_spec() -> JobSpec:
    return parse_fast_spec(STORY_WORKFLOW.read_text(encoding="utf-8"))


def _main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", choices=["gate", "fast"], help="要现读哪个 job 的环境配方")
    args = parser.parse_args()

    try:
        spec = load_gate_spec() if args.job == "gate" else load_fast_spec()
    except (GateSpecError, OSError) as error:
        print(f"gate_spec：解析 {args.job} 的环境配方失败：{error}", file=sys.stderr)
        return 1
    print(f"EXTRAS={','.join(spec.extras)}")
    print(f"PYTHON_VERSION={spec.python_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
