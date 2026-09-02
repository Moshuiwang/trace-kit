"""``python -m app.migrate``：本骨架没有数据库，打印「无迁移」并退出 0。

出处：本骨架为 trace-kit 新增的最小可运行进程，无上游对应物。部署编排把迁移作为
一次性 job（不配 restart）在常驻服务之前跑一遍；这里换成你的迁移命令（例如
``alembic upgrade head``），保持「成功退出 0、失败非 0」的退出码语义，编排靠它判定。
"""

from __future__ import annotations

import sys


def main() -> int:
    print("无迁移：本骨架没有数据库，这里换成你的迁移命令。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
