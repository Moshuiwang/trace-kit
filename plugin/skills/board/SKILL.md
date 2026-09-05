---
name: board
description: Trace 看板——在 tmux 里跑一个只读 TUI，从任务表与 GitHub 证据画出当前 Trace 的进度图：做到哪、堵在哪、每个模块轮了几轮、花了多少分钟。在产品负责人或编排者说「看板 / 看进度 / 现在做到哪」、或收口要归档一帧文本快照时使用。
---

> 出处：trace-kit https://github.com/Moshuiwang/trace-kit/issues/12 v3 修订段（v2 十二条设计裁定不变）＋ https://github.com/Moshuiwang/lingxi/issues/577 子清单（#578 节点粒度与边框轮数 / #579 只认结构化证据 / #580 键盘逐序列 / #581 数字来源等级 / #582 引擎入库 / #589 五级阶段）；验证：`tests/board/` 夹具（Trace #1 真实历史回放 ＋ 简单 / 复杂 / 未知 / 五级阶段）在 `kit-selfcheck` 上绿，https://github.com/Moshuiwang/lingxi/issues/606 真实试穿

# Trace 看板

一个**只显示、不阻断**的派生视图：任务表提供结构（Step、章节、可选标签），GitHub 提供全部时间与事实（commit、PR、CI run、Issue 评论）。**任务表是界面，GitHub 是事件日志，看板是派生视图**——看板不是真源，任何一格都能回 `git log` / `gh` 核。

引擎对目标仓库**只读**：不 fetch、不 pull、不 checkout、不 commit，也不在目标仓库建文件；远端状态一律经 `gh` 取。只用 Python 3 标准库 ＋ 已有的 `git` / `gh`（可选 `tmux`），无新增依赖、无常驻服务——TUI 进程只在你看的时候跑。

## 怎么跑

在 tmux 里**单开一个 window**（不要占用编排窗口），执行：

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board.py --repo-root . [--config docs/traces/board.toml]
```

- `--repo-root` 指向含 `docs/traces/` 的项目仓库根；`--trace N` 缺省取 `docs/traces/` 下编号最大的目录；`--branch` 缺省按证据源配置 → 含该编号的 PR 分支推断。
- **尺寸建议 150×52**（简易版六个模块不滚动）；75 列窄窗自动退回每行 3 张卡片，高度靠滚动。
- **键位**：`v` 简易 / 复杂视图切换 · `r` 立即刷新 · `a` 动效开关 · `q` 退出 · `↑↓` 逐行 · `PgUp` / `PgDn` 翻页 · `Home` / `End` 顶 / 底。无鼠标、无筛选、无折叠。
- 默认每 300 秒后台拉一次 git / gh（`--interval` 可调），只重写有差异的格子——不整屏重画，其他 pane 的光标不会跳。整轮采集上限 `--timeout`（默认 60 秒），超时或异常保留上一帧并在头部告警。
- `--dump` 打印一帧纯文本后退出（默认 150×52，`--width` / `--height` 覆盖）。**收口归档**：`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board.py --repo-root . --dump > docs/traces/<n>/看板.txt`。
- `--dump --why` 在帧后追加证据链表：每行「对象 | 状态 | 证据类型 | 证据键 | 取值 | 取值时间（UTC+8）| 可得」。**只打印证据键，不打印命令原文**，可以直接贴进公开 Issue；命令原文只留在 `--record` 写出的 `snapshot.json` 里，含项目专属命令的快照不要提交。
- `--registry` 打印下面那张登记表；`--fixture <dir>` 零网络回放夹具，`--record <dir>` 真实采集一次写快照（供做夹具），`--now <ISO8601>` 固定报告时刻。

## 怎么读

**头部六项**（阶段占两行）：

- **阶段**：执行到第几个章节、勾选进度；**五级阶段**：合入主干 · 已发布 · 预发已升级 · 已上生产 · 收口，取值 是 / 否 / 未知（未在证据源配置里声明的那一级显示「未配置」，不是「未知」）。
- **阻塞**（红）：卡住的步骤 / 暂停区间 / 最大空档。**下一步**（蓝）：第一个未勾选的 Step ＋ 编排窗口 / worktree 数。
- **预算**：证据源配置声明的计数条（有上限画 `▰▱` 条）；没有配置只列 PR 数与 CI 次数、不画上限、不编数。
- **存疑**（黄）：自述未证条数、合同 PR 自合 / 零批准、共用 PR。**最后外部证据**：最近一条 GitHub / git 留痕与它的时刻。
- 头部固定附注「窗口状态未知，需元守护核」——除非证据源配置声明了窗口模式且取到值。**看板不判活**。

**颜色即状态**（不写状态文字、不用虚框、不加感叹号）：完成 绿 · 自述未证 黄 · 运行中 蓝（边框流动） · 下一步 亮蓝 · 观察 橙（边框流动） · 卡住 红 · 待人类 紫 · 待做 灰 · 失效 灰暗 · 未知 灰。图例固定在最后一行。

**边框即审核轮数**（模块内审核结论 / 定向复核结论评论的计数）：未审 `┌─┐` · 1 轮 `╔═╗` · 2 轮 `┏━┓` · 3 轮 `┏╍┓` · 3 轮以上 `┏╍┓` ＋ 标题 `⟲N` ＋ 醒目色。

**简易版**（默认）＝每个 `##` 章节一个大模块，三行：①干什么（章节名 ＋ `完成/总数`）；②轮了几轮（`审 N · 外 N · 修 N · CI 红N 绿N`）；③证据在哪（`PR #n 状态 · 评论 N · 最新 HH:MM`）。标题行右侧是时长「已跑或实际 / 预估」，纯分钟：`41/45` 完成、`38/60` 运行中、`/─` 没有 `est:` 标签（不编数）、`?` 开工时刻不可知。**复杂版**（`v` 切换）＝任务表每个 Step 一张卡片 ＋ 它的证据小节点，可滚动；两个视图是同一份数据。

**来源角标**：每个数字后面紧跟一个暗色小字——`实` 实测（外部证据直接读到）、`报` 自报（代理或评论里的自述，**不参与超支判断**）、`推` 推断（按时间窗或链路推出来的）。

**「未知」**：判定所需的证据键取不到（命令不存在、超时、解析失败、`gh` 未登录）时如实显示「未知」，**不回落到「待做」、也不沿用上一次结论**。无法解析的任务表行进灰色「自由文本」卡片并计入头部告警，不报错退出；编号 / 一句话超字数上限的行只在头部计数，卡片里不出现省略号。

`--dump` 是纯文本没有颜色，所以模块 / 步骤标题行会追加 ` · <状态词>`（如 `Wave 2 · 运行中`）；TUI 帧里不加。

## 状态与证据登记表

每个状态位注明**判定用的结构化证据类型**——状态只认这些证据，不嗅探评论措辞。本节由 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board.py --registry` 生成，**逐字同源**（改引擎必须同步本节，单测会比对）。

| 状态 | 判定 | 判定用证据类型 |
| --- | --- | --- |
| 待做 `todo` | 未勾选、无证据、依赖未全部勾选 | checkbox |
| 下一步 `ready` | 未勾选、无证据、依赖全部勾选 | checkbox |
| 运行中 `running` | 未勾选、60 分钟内有归属证据 | commit_time / worktree / pr_state / ci_conclusion / comment_title |
| 观察 `watch` | 未勾选、最近证据 60–90 分钟前 | commit_time / worktree / pr_state / ci_conclusion / comment_title |
| 卡住 `stalled` | 未勾选、最近证据 > 90 分钟前 | commit_time / worktree / pr_state / ci_conclusion / comment_title |
| 待人类 `human` | `t:human` 且未勾选 | tasktable_tag / checkbox |
| 完成 `done` | 已勾选且有独立制品（PR MERGED / 提交存在 / 评论存在） | checkbox / pr_state / commit_time / comment_title |
| 自述未证 `doneq` | 已勾选但无独立制品 | checkbox / pr_state / commit_time / comment_title |
| 失效 `stale` | `t:review` 未勾选且指针 SHA ≠ 分支 HEAD | sha_equal / tasktable_tag |
| 未知 `unknown` | 判定所需证据键 ok=False（不回落） | config_command / commit_time / pr_state / comment_title / ci_conclusion / worktree |

| 阶段 | 证据类型 |
| --- | --- |
| 合入主干 `merged` | pr_state |
| 已发布 `published` | workflow_run / tag_ref |
| 预发已升级 `staging` | image_tag / config_command |
| 已上生产 `production` | image_tag / config_command |
| 收口 `closed` | issue_state |

| 头部项 | 证据类型 |
| --- | --- |
| 阻塞（卡住步骤 / 暂停区间 / 最大空档） `block` | commit_time / pr_state / comment_title / tasktable_tag |
| 下一步（首个未勾选 Step ＋ 编排窗口 / worktree 数） `next` | checkbox / tmux_window / worktree |
| 预算（配置计数条；无配置只列 PR 数与 CI 次数） `budget` | config_command / pr_state / workflow_run |
| 存疑（自述未证 / 合同 PR 自合零批准 / 共用 PR / PR 自合计数） `doubt` | checkbox / pr_merged_by / pr_state |
| 轮数（审 / 外 / 修＝评论首行匹配；CI 红绿＝活动窗口内 run 结论） `rounds` | comment_title / ci_conclusion |
| 最后外部证据 `evidence` | commit_time / pr_state / comment_title / ci_conclusion / worktree |

## 证据源配置（项目专属证据）

引擎不含任何项目知识。镜像 tag、编排窗口名模式、预算计数命令这类**项目专属证据**由项目仓库的一份 TOML 声明「跑什么只读命令、怎么解析」，引擎照着执行：模板见 `${CLAUDE_PLUGIN_ROOT}/templates/board.toml`，复制到项目仓库（建议 `docs/traces/board.toml`）后按项目改，用 `--config` 指过去。

- 可声明：`[trace]` 编号与分支 · `[repo]` 仓库 · `[orchestrator]` 编排窗口存活 · `[release]` 发布工作流名 · `[stages.staging]` / `[stages.production]` 预发与生产镜像 tag · `[budget.<key>]` 预算计数条 · `[[evidence]]` 附加证据行。每一节都可省略，省略＝不显示或「未配置」。
- 命令**只读、单条扁平、显式 `timeout`**；引擎用 `bash -o pipefail -c` 执行、断开 stdin、超时杀整个进程组；解析规则 `text` / `int` / `regex:<pat>` / `lines` / `json:<点路径>` / `count:<pat>`；失败一律记「未知」，不给默认值。
- **配置里不写任何凭据**；能用配置表达的改动不需要动引擎。

## 已知边界

- **不判活**：窗口是否还活着、代理是否失联，是元守护的事（`/trace-kit:guardian`）；看板头部固定提示「需元守护核」。
- **只显示、不阻断**：不挡合并、不做门禁、不产生结论；看板红了只是让人去看，不改变任何流程。
- 无鼠标、无筛选、无折叠；不做跨 Trace 汇总，不统计 token 与费用。
- 需要 `gh` 已登录（未登录 / 不可用时降级为只用 git，并在头部注明；取不到的项显示「未知」）。
- 时间全部按 UTC 内部计算、显示时显式换算 UTC+8；代理自述时刻不参与判断。
