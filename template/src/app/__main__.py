"""``python -m app``：常驻循环的最小形态——周期性写心跳，收到 SIGTERM/SIGINT 后优雅退出。

出处：本骨架为 trace-kit 新增的最小可运行进程，无上游对应物。这里换成你的常驻循环：
保留「信号只置停止标记、主循环自己决定何时退出」这个形状，在途工作做完再返回。
"""

from __future__ import annotations

import signal
import sys
import threading
from datetime import datetime, timezone

from app import __version__, heartbeat_interval_seconds, heartbeat_path


def write_heartbeat(path) -> None:
    """写入当前 UTC 时间；健康检查看的是文件 mtime，内容只给人读。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8")


def main() -> int:
    stop = threading.Event()

    def request_stop(signum, _frame) -> None:
        # 信号处理器只置标记，不在这里做任何清理：让主循环在一个完整的迭代边界上退出，
        # 在途的那一次工作（这里只是写心跳）做完再返回。
        print(f"收到信号 {signal.Signals(signum).name}，准备优雅退出", flush=True)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    path = heartbeat_path()
    interval = heartbeat_interval_seconds()
    print(f"app {__version__} 启动：心跳文件 {path}，间隔 {interval:g} 秒", flush=True)

    while not stop.is_set():
        write_heartbeat(path)
        # 这里换成你的一轮工作；Event.wait 会被信号处理器的 set() 立即唤醒，不必等满间隔。
        stop.wait(interval)

    print("已优雅退出", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
