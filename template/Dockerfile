# 生产镜像最小骨架：一份 Dockerfile、一个进程。
# 出处：lingxi https://github.com/Moshuiwang/lingxi/issues/62（非 root、固定底座、只 COPY 构建所需、
# 日志不缓冲）；验证：stage 20+ 次升级、生产首发（2026-09-02）。
#
# 只用 plain `docker build` 支持的语法：不使用 BuildKit 专有的 RUN --mount、heredoc 或缓存后端，
# "能不能构建"这件事不该取决于构建机装了什么插件。
#
# 基础镜像固定 tag 而不是浮动的 `python:3-slim`：同一提交今天和下周构建应拿到同一代底座。
# 这里换成你的：需要逐字节可复现（两次构建内容级等价）时把 tag 换成 digest（python@sha256:…），
# 更新底座 = 改这一行 + 重跑镜像门禁，是一次有留痕的显式变更。
FROM python:3.12-slim

# 日志走 stdout / stderr 且不缓冲：缓冲会让容器日志在崩溃时丢掉最后一段——恰恰是最需要的那一段。
ENV PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

# 非 root 运行。固定 uid/gid 而不是让系统分配：宿主机绑定挂载的属主要能对上，
# 浮动 uid 会让"换个机器部署就写不进卷"成为一种偶发故障。10001 落在系统账号区间之外。
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

# 只 COPY 构建 wheel 真正需要的两样；.dockerignore 已经默认排除其余（脚本、测试、文档、凭据）。
# 装完即删构建目录：最终 rootfs 里没有源码树，制品就是 `pip install` 装出来的那一份，
# 与测试跑 PYTHONPATH=src 的形态分叉只会在这里暴露。
WORKDIR /build
COPY pyproject.toml /build/pyproject.toml
COPY src /build/src
RUN python -m pip install --no-cache-dir --no-compile /build \
 && rm -rf /build

USER app
WORKDIR /
# 常驻进程：收到 SIGTERM 后把在途工作做完再退出（见 src/app/__main__.py）；
# 部署编排的 healthcheck 用 `python -m app.healthcheck`，迁移 job 用 `python -m app.migrate`。
CMD ["python", "-m", "app"]
