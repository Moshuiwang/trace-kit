# 部署编排

> 出处：lingxi [#62](https://github.com/Moshuiwang/lingxi/issues/62)（31 次修订）；验证：stage 20+ 次升级、prod 首发（2026-09-02）。

- **是什么**：单机 Docker Compose 编排骨架——常驻服务 `app` + 一次性作业 `migrate`，stage 与生产共用同一份结构、只有配置值不同；配套两条门禁（[文本级](../scripts/ci/check_deploy_contract.py) / [渲染级](../scripts/ci/verify_compose_structure.sh)）、[生产部署 runbook](生产部署runbook.md)、[验收前部署配置清单](验收前部署配置清单.md)与[宿主监控告警](监控告警.md)。
- **怎么用**：按下文「准备 → 部署前置检查 → 安装与升级」逐字执行；改编排前后先跑「本地验证」两条脚本。
- **换什么**：`compose.yaml` 的 `name:`、服务（常驻照 `app`、一次性照 `migrate` 加）与 `stop_grace_period` 推导；`.env.example` 的变量与镜像仓库前缀；资源数值；文档里每处「这里换成你的」。

本目录**不是部署设计文档**，只写「怎么执行」。验收前要配齐什么、缺一项会死在哪里、配完怎么自检，见验收前部署配置清单；生产首次部署的分步骤、镜像 digest 固定、单实例纪律、首发不灰度、回滚判据与观察期，见生产部署 runbook。

## 本版包含哪些进程

| 服务 | 形态 | 入口 | 说明 |
| --- | --- | --- | --- |
| `app` | **常驻服务** | 镜像默认入口（这里换成你的） | `restart`、`stop_grace_period`、`healthcheck`（`python -m app.healthcheck`）三样都有；这里换成你的常驻进程说明 |
| `migrate` | **一次性作业**（`job` profile，默认不启动） | `python -m app.migrate` | 部署时跑一次的数据库迁移；**不配 restart**，失败必须停下来让人看见 |

**常驻服务与一次性作业是两类东西**：一次性作业放在 `job` profile 里，裸 `docker compose up -d` 不会启动它，要显式 `--profile job run --rm <名字>`；给它配 restart 会把「作业正常退出」变成无限重启循环，并让人误以为服务已经上线。新增服务时对号入座，不要混用。

## 镜像 tag 语义

```
<仓库前缀>/app:<YYYYMMDD>-<commit sha 前 12 位>

例：registry.example/your-org/app:20260101-0123456789ab
```

- **日期段**标识发布批次，**sha 段**标识源码提交。
- 带上 sha 才是**不可变**的：同一个 tag 永远指向同一份源码，「回滚 = 切回上一个 tag」这件事才有意义。
- **禁止 `latest` 或分支名**。`scripts/ci/check_deploy_contract.py` 会拦住它们。
- 与源码验收用的 git tag **不混用**：那只固定源码，不是镜像 tag。

## 版本号规则

版本号（SemVer、整仓单一版本、随发布批次升版并打 git tag `v<版本号>`）的约定见仓库根 `CHANGELOG.md`。镜像 tag 维持上面的 `日期-sha` 格式不变，版本号与镜像的对应关系由 tag 指向的提交记录承载，不重造镜像命名（出处：[#417](https://github.com/Moshuiwang/lingxi/issues/417)）。

## 准备

一个环境要**三个**文件，不是一个：

```bash
cp deploy/.env.example deploy/.env.stage      # 只留 APP_IMAGE_REGISTRY / APP_IMAGE_TAG（及可选覆盖）
$EDITOR deploy/.env.stage.app                 # app 进程的凭据与配置
$EDITOR deploy/.env.stage.migrate             # 只有迁移连接串
```

三个名字都匹配 `.gitignore` 的 `.env.*` 规则，**不入库**；镜像里不预置任何凭据。变量形状逐条见 [`.env.example`](.env.example)。

**为什么按服务拆而不是共用一份**：每个进程只拿自己真正需要的变量。共用一份 env 等于把业务库口令、迁移 DDL 角色、外部应用密钥一起塞给每个进程；进程再把环境继承给子进程时，凭据就一路流进了它们不该到达的地方。`check_deploy_contract.py` 会拦住两个服务共用同一个 env_file。

## 部署前置检查（preflight，逐条通过才能 `up`）

### 1. 凭据文件权限

凭据不进代码、日志、数据库；本骨架用文件注入，因此**文件权限就是这条边界的全部**——一个 0644 的 env 文件等于把生产口令摊给机器上任何一个账号。三个文件都必须 **0600 且属主为部署用户**。用 `install` 一步到位，别先 `cp` 再 `chmod`（那中间有一个短暂的可读窗口）：

```bash
umask 077
install -m 600 -o "$(id -un)" -g "$(id -gn)" /dev/null deploy/.env.stage
install -m 600 -o "$(id -un)" -g "$(id -gn)" /dev/null deploy/.env.stage.app
install -m 600 -o "$(id -un)" -g "$(id -gn)" /dev/null deploy/.env.stage.migrate
# 然后再往里写内容
```

`up` 之前逐条核对，任一不符就停下：

```bash
for f in deploy/.env.stage deploy/.env.stage.app deploy/.env.stage.migrate; do
  stat -c '%n %a %U' "$f"
done
# 期望每行都是 `<文件> 600 <部署用户>`；生产同型，把 stage 换成 prod
```

> 长期凭据迁移到操作系统级密钥管理（Docker secrets / systemd credentials / 云托管密钥服务）是登记在案的后续路线；在那之前，文件权限是唯一的保护，因此上面这一步不是建议而是前置条件。

### 2. 主机读取身份

私有镜像仓库不登录就拉不下来——`docker compose up` 会停在 `failed to authorize ... 403 Forbidden`。部署机必须先有一份**只读**拉取身份，且**不得使用任何个人凭据**，也不得复用 CI 的令牌：

```bash
echo "<只读拉取令牌，由 ops 供给>" | docker login <你的镜像仓库> -u "<只读拉取用户>" --password-stdin
```

## 安装与升级

**`--env-file` 不能省。** `env_file:` 只把变量注入**容器**，它**不参与 compose 文件自身的 `${VAR:?}` 插值**。省掉它，compose 会直接报 `APP_IMAGE_REGISTRY` 未设并退出。

```bash
# 1. 先跑迁移（一次性作业）
docker compose --env-file deploy/.env.stage \
  -f deploy/compose.yaml -f deploy/compose.stage.yaml \
  --profile job run --rm migrate

# 2. 再启动常驻服务
docker compose --env-file deploy/.env.stage \
  -f deploy/compose.yaml -f deploy/compose.stage.yaml up -d

# 3. 回读
docker compose --env-file deploy/.env.stage \
  -f deploy/compose.yaml -f deploy/compose.stage.yaml ps
docker compose --env-file deploy/.env.stage \
  -f deploy/compose.yaml -f deploy/compose.stage.yaml logs app
```

**上面两项 preflight 未通过时不要执行 `up`。** 升级前先把当前容器日志 flush 到宿主持久目录（容器 stdout 日志不跨重部署持久，见 runbook「监控与日志」）。

生产把 `.env.stage` 换成 `.env.prod`、`compose.stage.yaml` 换成 `compose.prod.yaml`，其余逐字相同——两份覆盖文件**结构完全一致**，只有 env_file、卷名与数值不同（`scripts/ci/verify_compose_structure.sh` 每次 CI 都比对这一点）。

**生产只拉镜像，不构建**：三个 compose 文件里没有任何 `build:` 键。这不是纪律而是机制。

**`up -d` 配置未变时不会重启容器**：改的是挂载目录里的文件、宿主侧数据而不是 compose 配置时，compose 判 up-to-date 什么都不做。要重启用全形式 `docker compose --env-file deploy/.env.stage -f deploy/compose.yaml -f deploy/compose.stage.yaml restart app`——裸跑 `docker compose restart app` 缺 `--env-file`/`-f`，会按 base compose 重建出缺 env_file 的容器。

## 回滚

```bash
# 把 deploy/.env.prod 里的 APP_IMAGE_TAG（与 APP_IMAGE_DIGEST）改回上一个批次，然后：
docker compose --env-file deploy/.env.prod \
  -f deploy/compose.yaml -f deploy/compose.prod.yaml up -d
```

回滚不触碰数据库，也不触碰持久卷。**前提是迁移遵守「先加后删」**：破坏性变更必须拆成两次发布，否则回滚就从「切 tag 重启」变成「恢复数据库备份」。判据与步骤见 runbook「回滚判据与步骤」。

## 恢复入口

```bash
docker compose --env-file deploy/.env.prod -f deploy/compose.yaml -f deploy/compose.prod.yaml down
docker compose --env-file deploy/.env.prod -f deploy/compose.yaml -f deploy/compose.prod.yaml up -d
```

`down` 不带 `-v`，持久卷保留。数据库备份与恢复按你的数据库托管方案；持久卷单独备份。恢复演练的要求见 runbook「恢复演练要求」。

## 持久卷

| 卷（stage / 生产） | 挂载点 | 内容 |
| --- | --- | --- |
| `app-{stage,prod}-data` | `/var/lib/app/data` | 需要跨部署持久的状态（这里换成你的：凭据文件、用户数据……） |

需要跨部署持久的路径必须指向持久卷：指向容器本地路径会让每次镜像替换都丢失数据，而这个后果往往要过很久才暴露。备份周期、恢复策略与删除语义不同的数据**分开成不同的卷**——合成一个卷会让「只恢复 A」或「只清 B」变成不可能。装有凭据的卷，其备份、快照与介质交接必须按凭据级别对待：文件权限会被备份介质抹平。

## 停止宽限期为什么不是默认 10 秒

Docker 默认 10 秒，往往**不满足**：`SIGKILL` 若落在「外部副作用已发生、尚未写回」的窗口里（例如已经向外部换过一次性凭据、尚未写回数据库），就会留下不可恢复的中间态。数值不能拍脑袋，按下面这张表算（这里换成你的数字）：

| 项 | 秒 | 依据 |
| --- | --- | --- |
| 出站请求超时 | ___ | 进程收到 `SIGTERM` 后仍要等完的那次外部调用 |
| 重试退避等待 | ___ | 落盘/写库重试的退避序列之和 |
| 数据库往返预算 | ___ | 次数 × 单次最坏（建连 + 语句 + 提交各按合法上界） |
| **最坏合计** | ___ | × 1.5 安全系数 → 取整写进 `stop_grace_period` |

三项**全部来自进程自己的配置**，不是拍脑袋。把这个不等式钉进门禁（改了超时常量而不改 compose 就变红），不要靠这段文字守。常驻服务必须**单副本**时，靠进程间文件锁互斥，多副本会互相阻塞——见 runbook「单实例纪律」。

## 健康检查：不开放端口，`docker exec` 语义

`healthcheck.test` 是 `python -m app.healthcheck`——**不监听任何端口**，与主进程共享同一个容器的文件系统与网络命名空间，不为健康检查扩大网络攻击面。两段独立判定，**都要过**：

1. **依赖可达**：用与业务代码同一个连接工厂尝试连接数据库、跑一条 `SELECT 1`；数据库不可用时——无论网络问题、凭据错误还是宕机——这一步必然如实失败。
2. **主循环仍在跳动**：读取主循环每轮 touch 的活性文件，年龄超过阈值即判不健康。这一段单独存在是因为只测依赖可达测不出「进程 PID 还在、数据库也连得上，但主循环因为一次未捕获异常或死锁已经停止消费」。

活性文件写在容器内 `/tmp`（tmpfs），随容器重启自然清空。健康检查不得只证明 PID 存活——这是门禁核对每个常驻服务都配了 healthcheck 的原因。

## 资源限制

每个服务都用 `deploy.resources.limits`（`cpus`/`memory`/`pids`）声明上限；没有限制时，一个服务失控（内存泄漏、fork 炸弹式的子进程）能饿死同一台机器上的其他服务而没有任何机制拦住。

- **语法选型**：`deploy.resources.limits`，不是顶层 `mem_limit`/`cpus`/`pids_limit`。两种写法在 `docker compose up`（非 swarm）下都真实生效（渲染后的 `HostConfig.Memory`/`NanoCpus`/`PidsLimit` 逐位相同）；选前者是因为三项归在同一个键下，覆盖文件整块替换不容易漏改某一项。
- **数值分环境**：`compose.yaml` 只给安全默认值，真正生效的数值来自覆盖文件，覆盖值来自 `--env-file`。**`pids` 尤其不能照抄别的服务**：会扇出子进程的服务压得太低，会在正常负载下杀掉本该完成的任务——这比限制偏松更严重。
- **加总核对**：`limits` 是上界不是预留，需要逐档核对的是 `memory`——同时在跑的常驻服务加总必须小于主机内存并留出宿主与守护进程余量；`:-` 有默认值的变量漏配不报错，只会静默退回默认，部署前用渲染回读确认：

  ```bash
  docker compose --env-file deploy/.env.prod -f deploy/compose.yaml -f deploy/compose.prod.yaml config app
  ```

- **门禁只核对结构**（每个服务三项键都在），不核对数值——数值是容量判断，不是机械可判定的对错。

## 本地验证

```bash
python3 scripts/ci/check_deploy_contract.py      # 文本级：不需要 docker，挂在 verify_repository.sh 上
scripts/ci/verify_compose_structure.sh           # 渲染级：stage ↔ 生产结构对照，需要 docker compose v2
```
