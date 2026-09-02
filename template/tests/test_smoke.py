#!/usr/bin/env python3
"""``app`` 骨架的冒烟用例：包能导入、两个一次性入口的退出码、常驻进程的优雅退出。

出处：本骨架为 trace-kit 新增的最小可运行进程，无上游对应物；用例形状照 lingxi
https://github.com/Moshuiwang/lingxi/blob/caa845d77fbd2d6381de304dc6047498aa84c782/tests/test_ci_layering.py
（标准库 unittest、子进程跑真入口、不 mock 被测命令）。

这三件事都是**部署编排会真的依赖**的契约，不是"覆盖率"：
- ``python -m app.healthcheck`` 的 0/1 决定容器被判健康还是被重启；
- ``python -m app.migrate`` 的退出码决定迁移 job 成功还是拦住后续服务；
- ``python -m app`` 对 SIGTERM 的响应决定 ``docker stop`` 是优雅收尾还是 10 秒后被杀。
因此每条用例都起真的子进程跑真的入口，不 import 后直接调函数——那样测不到
``__main__`` 的信号注册与退出码传递。
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
SEMANTIC_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
# 子进程等待上限：本机与 CI runner 的波动都远小于它，触发它意味着进程真的卡住了。
STARTUP_TIMEOUT_SECONDS = 20.0


def _child_environment(**overrides: str) -> dict[str, str]:
    """让子进程一定 import 到**本仓库这棵树**里的 app，而不是碰巧装在环境里的另一个版本。"""
    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = f"{SOURCE_ROOT}{os.pathsep}{existing}" if existing else str(SOURCE_ROOT)
    environment.update(overrides)
    return environment


def _run_module(module: str, **overrides: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-m", module],
        cwd=REPOSITORY_ROOT,
        env=_child_environment(**overrides),
        capture_output=True,
        text=True,
        timeout=STARTUP_TIMEOUT_SECONDS,
    )


class PackageVersionTest(unittest.TestCase):
    """版本号只在 ``src/app/__init__.py`` 写一次，打包元数据从那里读。"""

    def test_import_app_exposes_a_semantic_version(self) -> None:
        import app

        self.assertTrue(SEMANTIC_VERSION.match(app.__version__), app.__version__)

    def test_pyproject_reads_the_version_from_the_package_instead_of_repeating_it(self) -> None:
        # 否定用例的形状：如果有人把版本号抄进 pyproject.toml 的 `version = "0.1.0"`，
        # 就出现了两个会各自漂移的版本源，这条会红。
        pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('dynamic = ["version"]', pyproject)
        self.assertIn('version = {attr = "app.__version__"}', pyproject)
        self.assertNotRegex(pyproject, r'(?m)^version\s*=\s*"')


class MigrateEntrypointTest(unittest.TestCase):
    def test_migrate_exits_zero_so_the_migration_job_does_not_block_startup(self) -> None:
        result = _run_module("app.migrate")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("无迁移", result.stdout)


class HealthcheckEntrypointTest(unittest.TestCase):
    """健康检查必须**真的会变红**：心跳缺失或过期时退出码是 1，不是"打印一句警告然后 0"。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="app-smoke-healthcheck-")
        self.heartbeat = Path(self._tmp.name) / "heartbeat"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_heartbeat_is_unhealthy(self) -> None:
        result = _run_module("app.healthcheck", APP_HEARTBEAT_FILE=str(self.heartbeat))

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("不健康", result.stderr)

    def test_fresh_heartbeat_is_healthy(self) -> None:
        self.heartbeat.write_text("now\n", encoding="utf-8")

        result = _run_module("app.healthcheck", APP_HEARTBEAT_FILE=str(self.heartbeat))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("健康", result.stdout)

    def test_stale_heartbeat_is_unhealthy(self) -> None:
        """进程卡死的形状：文件还在、但 mtime 不再更新，超过阈值必须判 1。"""
        self.heartbeat.write_text("stale\n", encoding="utf-8")
        stale = time.time() - 3600
        os.utime(self.heartbeat, (stale, stale))

        result = _run_module(
            "app.healthcheck",
            APP_HEARTBEAT_FILE=str(self.heartbeat),
            APP_HEARTBEAT_MAX_AGE_SECONDS="30",
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("不健康", result.stderr)


class GracefulShutdownTest(unittest.TestCase):
    """``python -m app`` 收到 SIGTERM 后自己退出、退出码 0——不靠外部 kill -9。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="app-smoke-main-")
        self.heartbeat = Path(self._tmp.name) / "heartbeat"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _start_resident_process(self) -> subprocess.Popen[str]:
        process = subprocess.Popen(
            [sys.executable, "-B", "-m", "app"],
            cwd=REPOSITORY_ROOT,
            env=_child_environment(
                APP_HEARTBEAT_FILE=str(self.heartbeat),
                APP_HEARTBEAT_INTERVAL_SECONDS="0.1",
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self.heartbeat.exists():
                return process
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                self.fail(f"常驻进程提前退出（{process.returncode}）：{stdout}{stderr}")
            time.sleep(0.02)
        process.kill()
        self.fail(f"{STARTUP_TIMEOUT_SECONDS:g} 秒内没有写出心跳文件：{self.heartbeat}")

    def test_sigterm_makes_the_loop_finish_the_current_iteration_and_exit_zero(self) -> None:
        process = self._start_resident_process()
        try:
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=STARTUP_TIMEOUT_SECONDS)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

        self.assertEqual(process.returncode, 0, stderr)
        self.assertIn("SIGTERM", stdout)
        self.assertIn("已优雅退出", stdout)

    def test_sigint_takes_the_same_path(self) -> None:
        """Ctrl-C 与编排发来的 SIGTERM 走同一条收尾路径，不是两套各自维护的退出逻辑。"""
        process = self._start_resident_process()
        try:
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=STARTUP_TIMEOUT_SECONDS)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

        self.assertEqual(process.returncode, 0, stderr)
        self.assertIn("已优雅退出", stdout)


if __name__ == "__main__":
    unittest.main()
