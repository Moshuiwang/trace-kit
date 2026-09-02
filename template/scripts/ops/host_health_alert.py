#!/usr/bin/env python3
"""宿主级容器健康告警：docker inspect 判定 → 群告警 + 恢复通知 + 去重 + 单实例。

出处：lingxi https://github.com/Moshuiwang/lingxi/issues/373（D5 裁定，PR #390）；验证：stage 两次真实注入（#373 S-H2-7、#521 W0-2a）

补的盲区：应用内告警跑在进程自己里，发现不了「承载它的容器本身已不健康、甚至已不在运行」——出问题的正是发告警这条
链路所在的进程。本脚本刻意跑在**容器之外**（宿主 timer/cron），只依赖 Python3 标准库与 `docker` 命令，不 import 项目包、
不进任何镜像，容器全灭也跑得动；只读 `docker container inspect --format '{{json .State}}'`（只在容器命名空间查名字、
只取 State，不碰装着凭据的 Config.Env），不监听端口，只发出站 HTTP。
触发（直接信 docker 的判定，不自己攒计数）：容器不存在 missing；`State.Restarting` 重启循环 restarting；
`State.Running == false` stopped；`State.Health.Status == "unhealthy"`（docker 的 `retries` 已隐含「持续」）。
`starting`（仍在 start_period 内）与没配 HEALTHCHECK 的容器都**不**触发。
去重：同一容器同一原因只在首次进入时告警一次，原因变化算新事件；状态**只在发送成功后落盘**，发送失败不落盘、下一轮
自然重试。恢复：回到 healthy（或本来就无 healthcheck）时发一条恢复通知并清空记忆；告警态下看到 `starting` 既不算新触发
也不确认恢复（否则宽限期一结束又来一条）。发送失败只写本地日志、不崩溃；`fcntl.flock` 单实例，拿不到锁不是故障。
退出码 0 = 本轮检查已完成（**不代表容器都健康**，拿不到锁也是 0）；2 = 脚本自身故障（凭据文件缺失/权限不对、docker
不可用、状态文件写不了），需要人工介入。凭据只从 `--env-file`（须 0600 且属主为当前用户）读 ALERT_WEBHOOK_URL，值不进
argv、不进日志；发送出口只有 `send_alert()` 一处——**这里换成你的群 webhook 格式**。
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping, NamedTuple, Sequence

# 默认监控目标：compose 项目名 `app` 下常驻服务 `app` 的容器名（这里换成你的容器名）。
DEFAULT_CONTAINERS = ("app-app-1",)
DEFAULT_STATE_DIR = "/opt/app/monitoring"
DEFAULT_TIMEOUT_SECONDS = 10.0
REQUIRED_ENV_KEYS = ("ALERT_WEBHOOK_URL",)
REASON_OK, REASON_STARTING, REASON_NO_HEALTHCHECK = "healthy", "starting", "no_healthcheck"
REASON_MISSING, REASON_STOPPED, REASON_RESTARTING, REASON_UNHEALTHY = "missing", "stopped", "restarting", "unhealthy"
REASON_LABEL = {REASON_MISSING: "容器不存在", REASON_STOPPED: "容器存在但未运行",
                REASON_RESTARTING: "容器处于重启循环", REASON_UNHEALTHY: "健康检查持续失败（unhealthy）"}
RECOVERY_REASONS = frozenset({REASON_OK, REASON_NO_HEALTHCHECK})
ACTION_NONE, ACTION_ALERT, ACTION_RECOVERY = "none", "alert", "recovery"


class HostMonitorError(RuntimeError):
    """脚本自身的、需要人工介入的故障；消息只含错误类别与字段名，不回显任何取值。"""

class Classification(NamedTuple):
    name: str
    reason: str
    trigger: bool

def classify(name: str, state: Mapping[str, object] | None) -> Classification:
    """触发条件的唯一判定入口；入参是 `docker inspect` 的 State 字段，None 表示容器不存在。"""
    if state is None:
        return Classification(name, REASON_MISSING, True)
    health = state.get("Health")
    status = health.get("Status") if isinstance(health, Mapping) else None
    if state.get("Restarting") is True:
        return Classification(name, REASON_RESTARTING, True)
    if state.get("Running") is False:
        return Classification(name, REASON_STOPPED, True)
    if status in (REASON_UNHEALTHY, REASON_STARTING):
        return Classification(name, status, status == REASON_UNHEALTHY)
    return Classification(name, REASON_OK if status else REASON_NO_HEALTHCHECK, False)

def decide_action(classification: Classification, prior: str | None) -> tuple[str, str | None]:
    """去重与恢复通知的状态机；本身不做 I/O。状态就是「上一次已确认送达的告警原因」，
    None = 当前不在告警态。返回 (动作, 发送成功后应落盘的新状态)。"""
    if classification.trigger:
        return (ACTION_NONE, prior) if prior == classification.reason else (ACTION_ALERT, classification.reason)
    if prior and classification.reason in RECOVERY_REASONS:
        return ACTION_RECOVERY, None
    # 告警态下遇到 starting：既不触发也不恢复，原样保留记忆，等下一轮拿到确定结果。
    return ACTION_NONE, prior

def render_message(action: str, classification: Classification, *, host: str, now: str) -> str:
    status = REASON_LABEL.get(classification.reason, classification.reason) if action == ACTION_ALERT else "已恢复正常"
    title = "告警" if action == ACTION_ALERT else "恢复"
    return f"[宿主监控] {title}\n容器：{classification.name}\n状态：{status}\n主机：{host}\n时间：{now}"

def docker_inspect_one(name: str, *, docker_bin: str, timeout_seconds: float) -> Mapping[str, object] | None:
    """返回 State 字段；None 表示「容器不存在」这一正常情况。daemon 不可达等其余非零退出是脚本故障，
    抛 HostMonitorError——不能把「问不到 daemon」悄悄当成「容器不存在」，否则 daemon 抖动恢复时会误报假恢复。"""
    command = [docker_bin, "container", "inspect", "--format", "{{json .State}}", name]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except FileNotFoundError as error:
        raise HostMonitorError(f"docker_binary_not_found:{docker_bin}") from error
    except subprocess.TimeoutExpired as error:
        raise HostMonitorError("docker_inspect_timeout") from error
    if proc.returncode != 0:
        if any(marker in (proc.stderr or "") for marker in ("No such object", "No such container")):
            return None
        raise HostMonitorError(f"docker_inspect_daemon_error:{proc.returncode}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        raise HostMonitorError("docker_inspect_invalid_json") from error
    return data if isinstance(data, Mapping) else None

def load_credentials(path: Path) -> dict[str, str]:
    """校验 0600 与属主，解析 KEY=VALUE（不做变量展开，只剥一层引号）；错误信息不回显取值。"""
    if not path.is_file():
        raise HostMonitorError("env_file_not_found")
    file_stat = os.stat(path)
    if file_stat.st_mode & 0o777 != 0o600:
        raise HostMonitorError(f"env_file_permission_unsafe:{oct(file_stat.st_mode & 0o777)}")
    if file_stat.st_uid != os.getuid():
        raise HostMonitorError("env_file_owner_mismatch")
    values: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not key.strip():
            raise HostMonitorError(f"env_file_malformed_line:{lineno}")
        value = value.strip()
        values[key.strip()] = value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value
    if missing := [key for key in REQUIRED_ENV_KEYS if not values.get(key)]:
        raise HostMonitorError(f"env_file_missing_keys:{','.join(missing)}")
    return values

def load_state(path: Path) -> dict[str, str]:
    """状态文件不存在、损坏或格式不对都按「从空状态开始」处理，不崩溃。"""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(name): reason for name, reason in raw.items() if isinstance(reason, str)} if isinstance(raw, Mapping) else {}

def save_state(path: Path, states: Mapping[str, str]) -> None:
    """原子落盘（写临时文件后 os.replace），避免并发/崩溃留下半截 JSON。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_text(json.dumps(dict(states), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
    except OSError as error:
        raise HostMonitorError(f"state_file_write_failed:{type(error).__name__}") from error

def send_alert(webhook_url: str, text: str, *, timeout_seconds: float) -> None:
    """唯一的发送出口——这里换成你的群 webhook 格式（请求体、鉴权头、成功判定）。
    默认按最通用的 incoming webhook 形状 POST `{"text": ...}`；HTTP 非 2xx、超时、连接失败都抛
    HostMonitorError，由调用方按「发送失败不落盘、下一轮重试」处理。"""
    body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(webhook_url, data=body, method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise HostMonitorError(f"alert_send_transport_error:{type(error).__name__}") from error

@contextlib.contextmanager
def single_instance_lock(path: Path) -> Iterator[bool]:
    """fcntl.flock 独占锁；拿不到锁时 yield False，不是脚本故障（只是上一轮还没跑完）。
    锁随 fd 关闭自动释放，因此不显式 LOCK_UN——进程被杀时内核同样会释放，不会留下死锁。"""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True
    finally:
        os.close(fd)

def configure_logger(log_file: str) -> logging.Logger:
    """本地日志文件（宿主基础设施层刻意独立留痕）；建不了文件就退到 stderr。"""
    try:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        handler: logging.Handler = logging.FileHandler(log_file, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler(sys.stderr)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[handler], force=True)
    return logging.getLogger("host_monitor")

def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="宿主级容器健康告警：docker inspect 判定 + 群 webhook 通知。")
    parser.add_argument("--env-file", required=True, help="凭据文件路径，须 0600；内容为 ALERT_WEBHOOK_URL=... 一行")
    parser.add_argument("--containers", nargs="+", default=list(DEFAULT_CONTAINERS), help="要监控的容器名列表")
    parser.add_argument("--state-file", default=f"{DEFAULT_STATE_DIR}/state.json", help="去重状态文件路径")
    parser.add_argument("--log-file", default=f"{DEFAULT_STATE_DIR}/host-monitor.log", help="本地日志文件路径")
    parser.add_argument("--lock-file", default=f"{DEFAULT_STATE_DIR}/host-monitor.lock", help="单实例锁文件路径")
    parser.add_argument("--docker-bin", default="docker", help="docker 可执行文件名或路径")
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="docker inspect 与 webhook 单次超时秒数")
    parser.add_argument("--dry-run", action="store_true", help="只判定、打日志，不真实发送、不落盘状态（安装后先验证判定逻辑）")
    args = parser.parse_args(argv)
    logger = configure_logger(args.log_file)
    with single_instance_lock(Path(args.lock_file)) as acquired:
        if not acquired:
            logger.warning("拿不到单实例锁，上一轮可能还在执行，本轮安静跳过")
            return 0
        try:
            credentials = load_credentials(Path(args.env_file))
            if shutil.which(args.docker_bin) is None:
                raise HostMonitorError(f"docker_binary_not_found:{args.docker_bin}")
        except HostMonitorError as error:
            logger.error("前置校验失败，本轮未执行任何检查 error=%s", error)
            return 2
        state_path = Path(args.state_file)
        states = load_state(state_path)
        host = socket.gethostname()
        changed = fatal = False
        for name in args.containers:
            try:
                entry = docker_inspect_one(name, docker_bin=args.docker_bin, timeout_seconds=args.timeout_seconds)
            except HostMonitorError as error:
                logger.error("docker inspect 执行失败，本轮跳过该容器 container=%s error=%s", name, error)
                fatal = True
                continue
            classification = classify(name, entry)
            action, target = decide_action(classification, states.get(name))
            if action == ACTION_NONE:
                continue
            now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            text = render_message(action, classification, host=host, now=now)
            if args.dry_run:
                logger.info("dry-run，未真实发送 container=%s action=%s reason=%s", name, action, classification.reason)
                continue
            try:
                send_alert(credentials["ALERT_WEBHOOK_URL"], text, timeout_seconds=args.timeout_seconds)
            except Exception as error:  # noqa: BLE001 - 发送路径任何异常都不能让整轮崩掉
                logger.error("告警发送失败，状态未落盘，下一轮会重试 container=%s action=%s error=%s", name, action, error)
                continue
            states.pop(name, None)
            if target:
                states[name] = target
            changed = True
            logger.info("已发送 container=%s action=%s reason=%s", name, action, classification.reason)
        if changed:
            try:
                save_state(state_path, states)
            except HostMonitorError as error:
                logger.error("状态文件写入失败，下一轮可能重复告警 error=%s", error)
                fatal = True
        return 2 if fatal else 0

if __name__ == "__main__":
    raise SystemExit(run())
