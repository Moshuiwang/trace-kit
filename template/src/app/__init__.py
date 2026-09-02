"""最小可运行的常驻进程骨架 ``app``。

出处：本骨架为 trace-kit 新增的最小可运行进程，无上游对应物；只为部署编排的
healthcheck / migrate 入口与镜像门禁提供一个真的能跑的目标。这里换成你的产品包。

四个入口：
- ``python -m app``             常驻循环：周期性写心跳，SIGTERM 后优雅退出；
- ``python -m app.healthcheck`` 退出码 0/1：心跳文件是否存在且足够新鲜；
- ``python -m app.migrate``     打印「无迁移」退出 0（这里换成你的迁移命令）。

心跳文件路径与新鲜度阈值只在本文件定义一次，常驻循环与健康检查共用，
两边各写一份迟早漂移。全部环境变量以 ``APP_`` 为前缀。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

__version__ = "0.1.0"


def heartbeat_path() -> Path:
    """心跳文件位置：``APP_HEARTBEAT_FILE``，默认落在系统临时目录（容器内即 tmpfs 可写目录）。"""

    configured = os.environ.get("APP_HEARTBEAT_FILE")
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "app-heartbeat"


def heartbeat_interval_seconds() -> float:
    """常驻循环两次心跳之间的间隔：``APP_HEARTBEAT_INTERVAL_SECONDS``，默认 5 秒。"""

    return float(os.environ.get("APP_HEARTBEAT_INTERVAL_SECONDS", "5"))


def heartbeat_max_age_seconds() -> float:
    """健康检查容忍的心跳最大年龄：``APP_HEARTBEAT_MAX_AGE_SECONDS``，默认 30 秒。

    默认值是心跳间隔的 6 倍：单次写入抖动不该把进程判成不健康，
    而连续错过多次心跳时必须在一个 healthcheck 周期内被发现。
    """

    return float(os.environ.get("APP_HEARTBEAT_MAX_AGE_SECONDS", "30"))
