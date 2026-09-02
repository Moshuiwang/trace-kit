#!/usr/bin/env python3
"""部署编排的静态契约检查（文本级：不依赖 docker，也不依赖 YAML 解析库）。

出处：lingxi https://github.com/Moshuiwang/lingxi/issues/62（2ece428，24 次修订）；验证：每次 verify_repository（298 个合并 PR）

守住 compose、Dockerfile 与 .gitignore 里那些**改坏了不会有任何东西报错**的约束：镜像 tag 是不是可变的、一次性作业有没有被
配上重启策略、常驻服务有没有健康检查与停止宽限期与资源上限、需要持久的路径有没有落在持久卷上、compose 里有没有混进构建
定义、凭据文件有没有被提交——全是「部署当天才会暴露」的一类。刻意不依赖 docker（挂在 scripts/ci/verify_repository.sh 上，
没装 docker 的机器也要跑出同一结论）、也不依赖 PyYAML（为一个门禁引入依赖本末倒置）；需要**渲染后**才能比对的断言（stage
与生产同构）由 scripts/ci/verify_compose_structure.sh 做，两者互补。判定落在去掉整行注释之后的文本上——注释里就写着「本文
件没有 `build:` 键」，天真的 grep 会误判。失败关闭：断言失败、文件缺失、`services:` 解析不出来都判红，本脚本无参数。
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY, DOCKERFILE, GITIGNORE = ROOT / "deploy", ROOT / "Dockerfile", ROOT / ".gitignore"
COMPOSE_BASE, ENV_EXAMPLE = DEPLOY / "compose.yaml", DEPLOY / ".env.example"
COMPOSE_OVERRIDES = (DEPLOY / "compose.stage.yaml", DEPLOY / "compose.prod.yaml")
M = re.MULTILINE
# 不可变 tag 的形状（<8 位日期>-<12 位 sha>，见 deploy/README.md）；env_file 只许叫 `./.env.<环境>.<服务>`
# ——这个形状匹配 .gitignore 的 `.env.*` 规则，天然不入库；一次性作业的标记是 `profiles: ["job"]`。
IMMUTABLE_TAG = re.compile(r"^\d{8}-[0-9a-f]{12}$")
ENV_FILE_NAME = re.compile(r"^\./\.env\.[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*$")
JOB_PROFILE = re.compile(r"^\s*profiles:\s*\[.*\bjob\b.*\]\s*$", M)
FAILURES: list[str] = []

def read_stripped(path: pathlib.Path) -> str:
    """读文件并把整行注释换成空行（保留行号）；文件缺失即判红并返回空串，不静默跳过。"""
    if not path.is_file():
        FAILURES.append(f"{path.relative_to(ROOT)} 不存在（失败关闭：缺文件即红）")
        return ""
    return "\n".join("" if line.lstrip().startswith("#") else line for line in path.read_text(encoding="utf-8").splitlines())

def service_blocks(text: str) -> dict[str, str]:
    """把 `services:` 下一级的每个 service 切成一块（按缩进定界，不做完整 YAML 解析）。"""
    section = re.search(r"^services:\s*$\n((?:[ \t].*\n|[ \t]*\n)*)", text, M)
    lines = [line for line in (section.group(1) if section else "").splitlines() if line.strip()]
    indent, name = min((len(line) - len(line.lstrip()) for line in lines), default=0), None
    blocks: dict[str, list[str]] = {}
    for line in lines:
        head = re.match(rf"^ {{{indent}}}([\w.-]+):\s*$", line)
        if head:
            name = head.group(1)
            blocks[name] = []
        elif name:
            blocks[name].append(line)
    return {key: "\n".join(value) for key, value in blocks.items()}

def scalar(block: str, key: str) -> str | None:
    match = re.search(rf"^\s*{key}:\s*(\S+)\s*$", block, M)
    return match.group(1).strip("'\"") if match else None

def listed(block: str, key: str) -> list[str]:
    """`<key>:` 的两种写法都收：单值 `key: ./x`，或其后缩进列表里的 `- ./x`。"""
    found = re.findall(rf"^\s*{key}:\s*(\S+)\s*$", block, M)
    for items in re.findall(rf"^\s*{key}:\s*\n((?:\s*-\s*\S+\s*\n?)+)", block, M):
        found += re.findall(r"-\s*(\S+)", items)
    return found

def check_common(path: pathlib.Path, text: str) -> None:
    """三个 compose 文件都要过：零 `build:`；镜像引用逐字不可变。"""
    if re.search(r"^\s*build:(\s|$)", text, M):
        FAILURES.append(f"{path.relative_to(ROOT)} 含 `build:` 键。生产只拉镜像、不构建——有构建定义，生产机上就有「顺手改一行再 build 一下」这条路径，镜像 tag 就不再是被冻结的版本")
    for number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^\s*image:\s*(\S.*?)\s*$", line)
        image = match.group(1) if match else ""
        if image and ("${APP_IMAGE_REGISTRY:?" not in image or "${APP_IMAGE_TAG:?" not in image):
            FAILURES.append(f"{path.relative_to(ROOT)}:{number} 镜像引用 `{image}` 必须逐字含 `${{APP_IMAGE_REGISTRY:?` 与 `${{APP_IMAGE_TAG:?`：带默认值（`:-`）或写死 tag 意味着漏设变量时会**静默**拉一个别的镜像；tag 形如 <YYYYMMDD>-<12 位 sha>，禁止 latest 或分支名")
        if re.search(r":latest(\s|$)", image):
            FAILURES.append(f"{path.relative_to(ROOT)}:{number} 镜像引用用了 latest：不可回溯，「切回上一个 tag」失去意义")

def check_privileges(label: str, block: str) -> None:
    """基线与覆盖都要过：覆盖文件后加载后生效，一行 `user: root` 就能把基线整个盖掉。"""
    user = scalar(block, "user")
    if user is not None and user.split(":")[0] in {"0", "root"}:
        FAILURES.append(f"{label} 以 root 运行（user: {user}）")
    if re.search(r"^\s*(privileged:\s*true|cap_add:)", block, M):
        FAILURES.append(f"{label} 配了 privileged/cap_add：当前实现不需要任何额外能力")
    if re.search(r"^\s*read_only:\s*false", block, M):
        FAILURES.append(f"{label} 关掉了 read_only")

def check_base_services(services: dict[str, str]) -> None:
    """结构只在 compose.yaml 定义，因此常驻服务与一次性作业的形状差异全在这里判。"""
    if not services:
        FAILURES.append("deploy/compose.yaml 没有解析到任何 service（`services:` 段缺失或缩进不对）")
    for name, block in services.items():
        label, restart = f"compose.yaml 的 {name}", scalar(block, "restart")
        if JOB_PROFILE.search(block):
            if restart != "no":
                FAILURES.append(f'{label} 在 job profile 里，必须显式 `restart: "no"`（现为 {restart}）：一次性作业配了重启策略，会把「作业正常退出」变成无限重启循环、把一次失败的迁移变成反复撞墙并掩盖真正原因')
            for key in ("healthcheck", "stop_grace_period"):
                if re.search(rf"^\s*{key}:", block, M):
                    FAILURES.append(f"{label} 是一次性作业，不该有 {key}（那是常驻服务的概念）")
        else:
            if restart != "unless-stopped":
                FAILURES.append(f"{label} 是常驻服务，必须 `restart: unless-stopped`（现为 {restart}）")
            if not re.search(r"^\s*healthcheck:\s*$", block, M):
                FAILURES.append(f"{label} 没有 healthcheck：依赖不可用时必须如实变红，不能只靠 PID 存活")
            if scalar(block, "stop_grace_period") is None:
                FAILURES.append(f"{label} 没有显式 stop_grace_period：Docker 默认 10 秒往往不够，SIGKILL 会落在「副作用已发生、尚未写回」的窗口")
            if scalar(block, "max-size") is None or scalar(block, "max-file") is None:
                FAILURES.append(f"{label} 的 logging 缺 max-size/max-file 上限：容器日志会无界增长写满宿主盘")
        check_privileges(label, block)
        if scalar(block, "user") is None:
            FAILURES.append(f"{label} 没有显式 `user:`，无法在 compose 层面核对非 root")
        if scalar(block, "read_only") != "true":
            FAILURES.append(f"{label} 缺 `read_only: true`：除持久卷与 tmpfs 外不得写本地状态")
        # 只核对三项上限的结构（键都在），不核对数值——数值是容量判断，不是机械可判定的对错。
        for key in ("cpus", "memory", "pids"):
            if scalar(block, key) is None:
                FAILURES.append(f"{label} 的 deploy.resources.limits 缺 {key}：没有上限，一个服务失控（内存泄漏、子进程扇出）就能饿死同机其他服务")
        # 需要跨部署持久的路径必须落在挂载点下：指向容器本地路径的状态每次镜像替换都会丢，而这个后果
        # 往往要过很久才暴露；`read_only: true` 拦不住它——挂载点本身就是可写的。
        mounts = [item.split(":")[1] for item in listed(block, "volumes") if ":" in item]
        for key, value in re.findall(r"^\s+(\w*(?:_DIR|_PATH)):\s*(/\S+)\s*$", block, M):
            if not any(value == mount or value.startswith(mount.rstrip("/") + "/") for mount in mounts):
                FAILURES.append(f"{label} 的 {key}={value} 不在任何挂载点下（现有挂载点：{mounts or '无'}）：需要跨部署持久的路径必须指向持久卷，否则每次镜像替换都丢数据")

def check_override(path: pathlib.Path, text: str, base: dict[str, str]) -> list[str]:
    """覆盖文件只放配置值：不新增结构、不放松安全设置；返回它引用的 env_file 列表。"""
    seen: dict[str, list[str]] = {}
    for name, block in service_blocks(text).items():
        label, restart = f"{path.relative_to(ROOT)} 的 {name}", scalar(block, "restart")
        if name not in base:
            FAILURES.append(f"{label} 只在覆盖文件里出现：结构须在 compose.yaml 定义，覆盖文件只放配置值")
        elif restart is not None and JOB_PROFILE.search(base[name]) and restart != "no":
            FAILURES.append(f'{label} 用覆盖把 restart 改成了 {restart}；一次性作业必须是 "no"')
        check_privileges(label, block)
        for env_file in listed(block, "env_file"):
            seen.setdefault(env_file, []).append(name)
    for env_file, names in sorted(seen.items()):
        if not ENV_FILE_NAME.match(env_file):
            FAILURES.append(f"{path.relative_to(ROOT)} 的 env_file `{env_file}` 不是 `./.env.<环境>.<服务>` 形状，会逃出 .gitignore 的 `.env.*` 规则")
        if len(names) > 1:
            FAILURES.append(f"{path.relative_to(ROOT)}：{'、'.join(names)} 共用 env_file `{env_file}`：凭据必须按服务分文件，每个进程只拿自己那份")
    return list(seen)

def check_env_example() -> None:
    text = read_stripped(ENV_EXAMPLE)
    tag = re.search(r"^APP_IMAGE_TAG=(\S+)\s*$", text, M)
    if tag is None or not IMMUTABLE_TAG.match(tag.group(1)):
        FAILURES.append("deploy/.env.example 的 APP_IMAGE_TAG 示范值缺失或不是 <YYYYMMDD>-<12 位 sha> 形状：模板里写什么，部署时多半就照抄什么")
    if not re.search(r"^APP_IMAGE_REGISTRY=", text, M):
        FAILURES.append("deploy/.env.example 缺 APP_IMAGE_REGISTRY 示范行")

def check_gitignore_and_tracking(env_files: list[str]) -> None:
    """凭据文件三重护栏：名字匹配 `.env.*`（上面已查）、.gitignore 忽略它、git 里确实没有它。"""
    rules = {line.strip() for line in read_stripped(GITIGNORE).splitlines() if line.strip()}
    if not rules & {".env.*", ".env*"}:
        FAILURES.append(".gitignore 没有 `.env.*` 规则：deploy/.env.<环境>.* 凭据文件会被提交")
    if "!.env.example" not in rules:
        FAILURES.append(".gitignore 没有 `!.env.example` 放行：样例文件会被忽略，没人知道要配哪些变量")
    proc = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--", "deploy"], capture_output=True, text=True, check=False) if shutil.which("git") else None
    if proc is None or proc.returncode != 0:
        FAILURES.append("git ls-files 不可用（没装 git 或不在 git 仓库内），无法核对凭据文件是否被提交（失败关闭）")
        return
    for path in sorted(proc.stdout.split()):
        name = path.rsplit("/", 1)[-1]
        if name != ".env.example" and (name.startswith(".env") or "./" + name in env_files):
            FAILURES.append(f"{path} 已被提交进版本库：凭据文件绝不入库，deploy 下只允许 .env.example")

def check_dockerfile() -> None:
    """镜像里已经切了非 root，compose 那一层再核对一次；凭据一律运行期注入。"""
    text = read_stripped(DOCKERFILE)
    users = re.findall(r"^USER\s+(\S+)\s*$", text, M)
    if not users:
        FAILURES.append("Dockerfile 没有 USER 指令：镜像以 root 运行")
    for user in (u for u in users if u.split(":")[0] in {"0", "root"}):
        FAILURES.append(f"Dockerfile 的 `USER {user}` 是 root")
    if re.search(r"^\s*(ENV|ARG)\s+\S*(SECRET|TOKEN|PASSWORD|DSN)\S*=\S", text, M | re.IGNORECASE):
        FAILURES.append("Dockerfile 用 ENV/ARG 给凭据形状的变量赋了值：凭据一律运行期注入，写进镜像等于发布到镜像仓库")

def main() -> int:
    base_text = read_stripped(COMPOSE_BASE)
    base = service_blocks(base_text)
    check_common(COMPOSE_BASE, base_text)
    check_base_services(base)
    env_files: list[str] = []
    for path in COMPOSE_OVERRIDES:
        text = read_stripped(path)
        check_common(path, text)
        env_files += check_override(path, text, base)
    check_env_example()
    check_gitignore_and_tracking(env_files)
    check_dockerfile()
    if FAILURES:
        print("部署编排契约：不通过", file=sys.stderr)
        print("\n".join(f"  - {failure}" for failure in FAILURES), file=sys.stderr)
        return 1
    print(f"部署编排契约：通过（service：{', '.join(sorted(base))}；3 个 compose、.env.example、.gitignore、Dockerfile）")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
