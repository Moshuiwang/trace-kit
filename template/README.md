# <项目名>

> 出处：各文件引言各自标注来源仓库文件（固定提交）与分档；本 README 按套件「是什么 / 怎么用 / 换什么」约定编写，无 lingxi 对应物。骨架版本：[trace-kit v0.1.0](https://github.com/Moshuiwang/trace-kit/tree/v0.1.0)。

## 是什么

一个新项目开工第一天就能用的仓库骨架：代理工作约定（`AGENTS.md`）、产品文档骨架（`docs/`）、GitHub Issue / PR 模板、分层 CI 与本机门禁（`scripts/`）、部署骨架（`deploy/`）。它把「文档是唯一正文、证据分层、门禁会变红、Trace 三件套」这套工作方法装进空仓库，不带任何产品正文。

## 怎么用

1. 从套件取得本骨架（安装两步见套件根 README）后，本目录内容已位于你的仓库根。
2. 按下表逐项替换占位；每处占位都写着「这里换成你的」，用 `grep -rn '这里换成你的'` 可以列出全部。
3. 安装套件插件，用 `kickoff` skill 起第一个 Execution Trace（三件套落到 `docs/traces/<issue号>-<短名>/`）；方法正文入口是 [docs/协作/执行方法.md](docs/协作/执行方法.md)。
4. 每次提交前跑本机门禁（见下文「CI 与本机门禁」）；纯文档改动只跑 `docs` 层。

## 换什么

| 位置 | 换成什么 |
| --- | --- |
| `AGENTS.md`、`CLAUDE.md`、`.github/copilot-instructions.md`、本文件、`CHANGELOG.md` | `<项目名>`；`deploy/` 与 CI 里的 `app` 服务名换成你的服务名 |
| [docs/产品合同.md](docs/产品合同.md) | 产品是什么、用户与入口、不提供、动态工作的去向——每个 `##` 章节都要在验收矩阵覆盖清单里登记 |
| [docs/当前能力.md](docs/当前能力.md) | 头部事实域表与「当前状态 / 尚待实现」清单；只有 L4a / L4b 才能把尚待实现改为当前能力 |
| [docs/协作约定.md](docs/协作约定.md) | 「固定名称与环境职责」三行环境表、提交身份 |
| [docs/技术设计/验收矩阵.md](docs/技术设计/验收矩阵.md) | 用你的第一条可判定断言替换 `V-示例-01`，同步第二节覆盖清单 |
| [docs/技术设计/README.md](docs/技术设计/README.md) | 架构 / 接口 / 数据库设计三份文档按需新建并登记 |
| `CHANGELOG.md` | 起始版本、版本事实源文件；发布批次条目 |
| `.github/ISSUE_TEMPLATE/*.yml` | 表单里的标签名（`labels`）换成你仓库实际存在的标签 |
| CI 与部署 | 见各自 README（下文两节） |

## CI 与本机门禁

见 `scripts/dev/README.md`（本机三层 `docs` / `fast` / `full` 与 CI 的同构关系）与 `.github/workflows/`。

## 部署

见 `deploy/README.md`（compose profile、不可变镜像 tag、runbook 与预检清单）。
