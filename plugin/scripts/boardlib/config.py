# -*- coding: utf-8 -*-
"""证据源配置（接口约定 §9；归属 S-4）。项目专属证据全部经此声明；引擎不含任何项目名词。

对外名字（S-2 / board.py 按名调用，不可变）：
    load(path) -> Config                       # path=None → 空配置；文件缺失 / TOML 语法错 / 未知键 / 类型错 → ConfigError
    Config / CommandSpec                        # 见下
    ShellProvider(per_cmd_timeout).run(spec, key=None) -> ProviderResult
    compare_tag(published, result) -> Val       # == → True；!= → False；任一不可得 → available=False

== 配置文件 schema（TOML；每一节都可省略；未知键 / 类型错误 → ConfigError，信息带键路径）==

    [trace]                           # 可选
    number = 123                      # int > 0；Trace Issue 号（缺省由 board.py --trace / docs/traces/ 推断）
    branch = "batch/123-xx"           # str；批次分支（缺省按 PR 推断）

    [repo]                            # 可选
    slug = "owner/repo"               # str；GitHub 仓库（缺省 git remote）

    [orchestrator]                    # 可选：编排窗口存活（不声明 → 头部固定附注「窗口状态未知」）
    tmux_session = "<session>"        # str；tmux session 名
    window_pattern = "^xx-b[0-9]+$"   # str；窗口名正则（load 时编译，编译失败即报错）

    [release]                         # 可选
    workflow = "<publish-workflow>"   # str；发布工作流的 name（gh run list --workflow）

    [stages.staging]                  # 可选；只认 staging / production 两个键（§7.4）；不写＝「未配置」
    command = "ssh -n <host> '...'"   # str，必填；只读命令，bash -o pipefail -c 执行
    parse = "regex:(?m)^\\S+:([^:\\s]+)$"   # str；解析规则（见下），缺省 text
    timeout = 20                      # int > 0，秒；缺省用 ShellProvider(per_cmd_timeout)
    grade = "measured"                # measured / reported / inferred；缺省 measured
    label = "预发"                    # str，可选；缺省＝键

    [budget.<key>]                    # 可选；预算计数条，顺序＝文件顺序；键任意（[A-Za-z0-9_.-]，全局唯一）
    label = "完整门禁"                # 缺省＝键
    cap = 5                           # int > 0，可选；缺省无上限（只计数、不画上限）
    command = "..." ; parse = "int" ; timeout = 25 ; grade = "measured"

    [[evidence]]                      # 可选；附加证据行（头部「最后外部证据」）
    key = "prod_healthy"              # str，必填，全局唯一
    label = "生产 healthy"
    command = "..." ; parse = "count:healthy" ; timeout = 25 ; grade = "measured"

解析规则 parse（作用于 stdout；失败 → ProviderResult.ok=False，error 带规则名）：
    text            去首尾空白的整段输出（缺省）
    int             整段输出去空白后按十进制整数
    lines           非空行列表（每行 rstrip）
    regex:<pat>     re.search（可用 (?m) / (?i) 内联标志）；取第一捕获组，无捕获组取整体匹配；不匹配 → 失败
    json:<a.b.0>    json.loads 后按点路径取值（数字段作列表下标；空路径＝整个文档）；路径不存在 → 失败
    count:<pat>     匹配 re.search(pat) 的行数（int）

执行约定：每条命令 `bash -o pipefail -c <command>`、stdin=DEVNULL、独立进程组、显式超时（超时杀整个进程组，
含挂死的 ssh）、cwd＝一次性临时目录（账本 R1-26：不在目标仓库里执行；命令本身不做沙箱——它是项目仓库经 PR 审阅的声明）；
非零退出 / 超时 / 无法启动 / 解析失败一律 ok=False 带 error，不抛异常、不给默认值。
error 只写失败类别（账本 A-1）：「非零退出 N」「超时 Ns」「无输出」「解析失败（<规则>）」「无法启动」——stderr / 输出片段常含主机名，
会随 `--dump --why` 进公开面，所以只留在 `ShellProvider.last_stderr[<结果键>]`（不进快照、不渲染）。
pipefail 意味着管道里任一环失败即失败（勿用 head 之类会提前关闭管道的命令）。
结果键：ProviderResult.key = "config.<key>"（stages 的 key 即 staging / production）；三组之间 key 不得重复。
ProviderResult.cmd 记录命令原文，会随 --record 写进 snapshot.json——含主机名的配置不要把快照提交进公开仓库。
"""
from __future__ import annotations

import json
import os
import re
import signal
import shutil
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .model import Grade, ProviderResult, Val

STAGE_KEYS = ("staging", "production")
PARSE_PLAIN = ("text", "int", "lines")
PARSE_PREFIXED = ("regex:", "json:", "count:")
DEFAULT_PARSE = "text"
_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_TOP_KEYS = ("trace", "repo", "orchestrator", "release", "stages", "budget", "evidence")
_SPEC_KEYS = ("command", "parse", "timeout", "grade", "label", "cap", "key")


class ConfigError(ValueError):
    """配置文件不可用：信息形如「<键路径>：<问题>（<文件>）」。"""


class ParseError(ValueError):
    """输出解析失败（只在模块内使用；对外表现为 ProviderResult.ok=False）。"""


@dataclass
class CommandSpec:
    """一条证据命令（阶段 / 预算 / 附加证据共用）。"""

    key: str
    command: str
    parse: str = DEFAULT_PARSE
    timeout: Optional[int] = None
    grade: Grade = Grade.MEASURED
    label: str = ""
    cap: Optional[int] = None
    kind: str = "evidence"  # stage / budget / evidence

    @property
    def result_key(self) -> str:
        return "config." + self.key


@dataclass
class Config:
    """解析后的证据源配置；无配置时全部 None / 空。"""

    path: Optional[str] = None
    trace_number: Optional[int] = None
    trace_branch: Optional[str] = None
    repo_slug: Optional[str] = None
    tmux_session: Optional[str] = None
    window_pattern: Optional[str] = None
    release_workflow: Optional[str] = None
    stages: dict[str, CommandSpec] = field(default_factory=dict)
    budgets: list[CommandSpec] = field(default_factory=list)
    evidence: list[CommandSpec] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def specs(self) -> list[CommandSpec]:
        """全部命令，顺序：阶段（staging、production）→ 预算 → 附加证据。"""
        return [self.stages[k] for k in STAGE_KEYS if k in self.stages] + list(self.budgets) + list(self.evidence)


# ---------- 读取与校验 ----------

def load(path: Optional[str]) -> Config:
    if path is None:
        return Config()
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        raise ConfigError("配置文件不存在：%s" % path) from None
    except OSError as exc:
        raise ConfigError("配置文件不可读：%s（%s）" % (path, exc)) from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError("TOML 语法错误：%s（%s）" % (exc, path)) from None
    return _build(data, path)


def _err(where: str, problem: str, path: Optional[str]) -> ConfigError:
    return ConfigError("%s：%s（%s）" % (where, problem, path or "-"))


def _table(data: Any, where: str, path: Optional[str]) -> dict:
    if not isinstance(data, dict):
        raise _err(where, "期望表（[%s]），得到 %s" % (where, type(data).__name__), path)
    return data


def _check_keys(data: dict, allowed: tuple, where: str, path: Optional[str]) -> None:
    for k in data:
        if k not in allowed:
            raise _err("%s.%s" % (where, k) if where else str(k), "未知键（只认 %s）" % " / ".join(allowed), path)


def _str(data: dict, key: str, where: str, path: Optional[str], required: bool = False) -> Optional[str]:
    if key not in data:
        if required:
            raise _err("%s.%s" % (where, key), "必填", path)
        return None
    v = data[key]
    if not isinstance(v, str):
        raise _err("%s.%s" % (where, key), "期望字符串，得到 %s" % type(v).__name__, path)
    if required and not v.strip():
        raise _err("%s.%s" % (where, key), "不能为空", path)
    return v


def _int(data: dict, key: str, where: str, path: Optional[str]) -> Optional[int]:
    if key not in data:
        return None
    v = data[key]
    if isinstance(v, bool) or not isinstance(v, int):
        raise _err("%s.%s" % (where, key), "期望正整数，得到 %r" % (v,), path)
    if v <= 0:
        raise _err("%s.%s" % (where, key), "必须 > 0，得到 %d" % v, path)
    return v


def _regex(pattern: str, where: str, path: Optional[str]) -> None:
    try:
        re.compile(pattern)
    except re.error as exc:
        raise _err(where, "正则不可编译：%s" % exc, path) from None


def check_parse_rule(rule: str, where: str = "parse", path: Optional[str] = None) -> str:
    """校验解析规则串；非法 → ConfigError。返回原串。"""
    if rule in PARSE_PLAIN:
        return rule
    for prefix in PARSE_PREFIXED:
        if rule.startswith(prefix):
            arg = rule[len(prefix):]
            if prefix in ("regex:", "count:"):
                if not arg:
                    raise _err(where, "%s 后需要正则" % prefix, path)
                _regex(arg, where, path)
            return rule
    raise _err(where, "未知解析规则 %r（只认 %s）" % (rule, " / ".join(PARSE_PLAIN + tuple(p + "<…>" for p in PARSE_PREFIXED))), path)


def _spec(data: Any, where: str, path: Optional[str], key: str, kind: str) -> CommandSpec:
    tbl = _table(data, where, path)
    _check_keys(tbl, _SPEC_KEYS, where, path)
    command = _str(tbl, "command", where, path, required=True)
    parse = _str(tbl, "parse", where, path)
    if parse is None:
        parse = DEFAULT_PARSE
    check_parse_rule(parse, where + ".parse", path)
    grade_text = _str(tbl, "grade", where, path)
    try:
        grade = Grade(grade_text) if grade_text is not None else Grade.MEASURED
    except ValueError:
        raise _err(where + ".grade", "只认 %s，得到 %r" % (" / ".join(g.value for g in Grade), grade_text), path) from None
    label = _str(tbl, "label", where, path) or key
    if not _KEY_RE.match(key):
        raise _err(where, "键只允许 [A-Za-z0-9_.-]，得到 %r" % key, path)
    return CommandSpec(
        key=key, command=command, parse=parse, timeout=_int(tbl, "timeout", where, path), grade=grade,
        label=label, cap=_int(tbl, "cap", where, path), kind=kind,
    )


def _build(data: dict, path: Optional[str]) -> Config:
    _table(data, "", path)
    _check_keys(data, _TOP_KEYS, "", path)
    conf = Config(path=path, raw=data)

    if "trace" in data:
        t = _table(data["trace"], "trace", path)
        _check_keys(t, ("number", "branch"), "trace", path)
        conf.trace_number = _int(t, "number", "trace", path)
        conf.trace_branch = _str(t, "branch", "trace", path)
    if "repo" in data:
        r = _table(data["repo"], "repo", path)
        _check_keys(r, ("slug",), "repo", path)
        conf.repo_slug = _str(r, "slug", "repo", path)
    if "orchestrator" in data:
        o = _table(data["orchestrator"], "orchestrator", path)
        _check_keys(o, ("tmux_session", "window_pattern"), "orchestrator", path)
        conf.tmux_session = _str(o, "tmux_session", "orchestrator", path)
        conf.window_pattern = _str(o, "window_pattern", "orchestrator", path)
        if conf.window_pattern is not None:
            _regex(conf.window_pattern, "orchestrator.window_pattern", path)
    if "release" in data:
        rel = _table(data["release"], "release", path)
        _check_keys(rel, ("workflow",), "release", path)
        conf.release_workflow = _str(rel, "workflow", "release", path)

    seen: dict[str, str] = {}

    def claim(key: str, where: str) -> None:
        if key in seen:
            raise _err(where, "键 %r 与 %s 重复（结果键 config.%s 必须唯一）" % (key, seen[key], key), path)
        seen[key] = where

    if "stages" in data:
        st = _table(data["stages"], "stages", path)
        for k, v in st.items():
            where = "stages.%s" % k
            if k not in STAGE_KEYS:
                raise _err(where, "只认 %s" % " / ".join(STAGE_KEYS), path)
            claim(k, where)
            spec = _spec(v, where, path, k, "stage")
            if "cap" in v:
                raise _err(where + ".cap", "阶段命令不接受 cap", path)
            if "key" in v:
                raise _err(where + ".key", "阶段的键就是表名，不接受 key", path)
            conf.stages[k] = spec
    if "budget" in data:
        bd = _table(data["budget"], "budget", path)
        for k, v in bd.items():
            where = "budget.%s" % k
            tbl = _table(v, where, path)
            if "key" in tbl:
                raise _err(where + ".key", "预算的键就是表名，不接受 key", path)
            claim(str(k), where)
            conf.budgets.append(_spec(tbl, where, path, str(k), "budget"))
    if "evidence" in data:
        ev = data["evidence"]
        if not isinstance(ev, list):
            raise _err("evidence", "期望表数组（[[evidence]]），得到 %s" % type(ev).__name__, path)
        for i, v in enumerate(ev):
            where = "evidence[%d]" % i
            tbl = _table(v, where, path)
            key = _str(tbl, "key", where, path, required=True)
            claim(key, where)
            conf.evidence.append(_spec(tbl, where, path, key, "evidence"))
    return conf


# ---------- 输出解析 ----------

def _short(text: str, n: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n] + "…"


def parse_output(rule: str, text: str) -> Any:
    """按规则解析 stdout；失败抛 ParseError。"""
    if rule == "text":
        return text.strip()
    if rule == "int":
        s = text.strip()
        try:
            return int(s)
        except ValueError:
            raise ParseError("不是整数：%r" % _short(s)) from None
    if rule == "lines":
        return [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if rule.startswith("regex:"):
        m = re.search(rule[len("regex:"):], text)
        if not m:
            raise ParseError("正则无匹配：%r" % _short(text))
        return m.group(1) if m.re.groups else m.group(0)
    if rule.startswith("json:"):
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ParseError("不是 JSON：%s" % exc) from None
        dotted = rule[len("json:"):]
        for part in dotted.split(".") if dotted else []:
            if isinstance(data, list):
                try:
                    data = data[int(part)]
                except (ValueError, IndexError):
                    raise ParseError("路径 %r 在列表段 %r 失败" % (dotted, part)) from None
            elif isinstance(data, dict) and part in data:
                data = data[part]
            else:
                raise ParseError("路径 %r 在 %r 处不存在" % (dotted, part))
        return data
    if rule.startswith("count:"):
        pat = re.compile(rule[len("count:"):])
        return sum(1 for ln in text.splitlines() if pat.search(ln))
    raise ParseError("未知解析规则 %r" % rule)


# ---------- 通用 shell provider ----------

def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, AttributeError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def _tail(text: str) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return _short(lines[-1], 160) if lines else ""


class ShellProvider:
    """按 CommandSpec 执行只读 shell 命令；任何失败都落在 ProviderResult.ok=False，不抛异常。

    `last_stderr[<结果键>]`：最近一次该键的 stderr 尾行 / 解析失败细节（可能含主机名），只供本机排障，不进快照、不渲染。"""

    def __init__(self, per_cmd_timeout: int = 25):
        self.per_cmd_timeout = per_cmd_timeout
        self.last_stderr: dict[str, str] = {}

    def run(self, spec: CommandSpec, key: Optional[str] = None) -> ProviderResult:
        key = key or spec.result_key
        timeout = spec.timeout or self.per_cmd_timeout
        base = dict(key=key, cmd=spec.command, fetched_at=datetime.now(timezone.utc), grade=spec.grade)
        self.last_stderr.pop(key, None)
        workdir = tempfile.mkdtemp(prefix="board-cmd-")          # 账本 R1-26：一次性 cwd，不在目标仓库里执行
        try:
            try:
                proc = subprocess.Popen(
                    ["bash", "-o", "pipefail", "-c", spec.command], stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                    start_new_session=True, cwd=workdir,
                )
            except OSError as exc:
                self.last_stderr[key] = str(exc)
                return ProviderResult(ok=False, error="无法启动", **base)
            try:
                out, err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill_group(proc)
                try:
                    proc.communicate(timeout=5)
                except (subprocess.TimeoutExpired, OSError, ValueError):
                    pass
                return ProviderResult(ok=False, error="超时 %ds" % timeout, **base)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        if _tail(err):
            self.last_stderr[key] = _tail(err)
        if proc.returncode != 0:
            return ProviderResult(ok=False, error="非零退出 %d" % proc.returncode, **base)
        try:
            value = parse_output(spec.parse, out)
        except ParseError as exc:
            self.last_stderr[key] = "解析失败（%s）：%s" % (spec.parse, exc)
            if not (out or "").strip():
                return ProviderResult(ok=False, error="无输出", **base)
            return ProviderResult(ok=False, error="解析失败（%s）" % spec.parse, **base)
        return ProviderResult(ok=True, value=value, **base)


# ---------- 阶段比对 ----------

def _scalar(value: Any) -> Optional[str]:
    if isinstance(value, list):
        value = next((v for v in value if str(v).strip()), None)
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def compare_tag(published: Optional[str], result: Optional[ProviderResult]) -> Val:
    """预发 / 生产 tag 与已发布 tag 比对：相等 → True；不等 → False；任一不可得 → available=False（渲染「未知」）。"""
    if result is None:
        return Val.unknown("config.stage")
    src = result.key or result.cmd
    if not result.ok:
        return Val(None, result.grade, src, result.fetched_at, False)
    got = _scalar(result.value)
    want = _scalar(published)
    if got is None or want is None:
        return Val(None, result.grade, src, result.fetched_at, False)
    return Val(got == want, result.grade, src, result.fetched_at, True)
