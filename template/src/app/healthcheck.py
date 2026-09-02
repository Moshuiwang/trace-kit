"""``python -m app.healthcheck``：退出码 0 = 健康，1 = 不健康；判据是心跳文件的新鲜度。

出处：本骨架为 trace-kit 新增的最小可运行进程，无上游对应物。部署编排的
``healthcheck: ["CMD", "python", "-m", "app.healthcheck"]`` 调用它；这里换成你的判据
（例如本地探活端口），但保持「真的会变红」：进程卡死时心跳不再更新，本检查必须返回 1。
"""

from __future__ import annotations

import sys
import time

from app import heartbeat_max_age_seconds, heartbeat_path


def main() -> int:
    path = heartbeat_path()
    max_age = heartbeat_max_age_seconds()
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        print(f"不健康：心跳文件不存在：{path}", file=sys.stderr)
        return 1
    if age > max_age:
        print(f"不健康：心跳已 {age:.0f} 秒未更新（上限 {max_age:g} 秒）：{path}", file=sys.stderr)
        return 1
    print(f"健康：心跳 {age:.0f} 秒前更新（上限 {max_age:g} 秒）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
