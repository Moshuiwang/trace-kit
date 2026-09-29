---
name: dispatch-card
description: 从模板生成实施 / 审查子代理的派发卡（六条款 + 实测附加条款 + 编排者侧兜底观察 + 审查派发小节）。在编排者要派发实施、修复或审查子代理时使用。
---

> 出处：lingxi https://github.com/Moshuiwang/lingxi/issues/147（v16 §6.4；迁移前在 https://github.com/Moshuiwang/lingxi/issues/678 v22 §四「派发、审核与验证」与「并行纪律」；源自 #203 复盘 https://github.com/Moshuiwang/lingxi/issues/203；留痕值粘贴与逐处证红出自 #843 复盘 https://github.com/Moshuiwang/lingxi/issues/843）；验证：#203 / #304 / #328 / #373 / #469 / #521 派发卡沿用，否决裁定 6 例 6 对；三批实证条款出自另一项目 Trace 的复盘 采用方项目 A #1 评论 5761645157、采用方项目 A #1 评论 5756158342、采用方项目 A #1 评论 5757824625（归档 https://github.com/Moshuiwang/lingxi/issues/857#issuecomment-5761705442）；另一项目 Trace #18 复盘与产品负责人 2026-09-29 点名的条款，逐条出处见 `CHANGELOG.md` v0.7.0；v0.7.0 起条款正文只留模板，原本 skill 里逐条附的出处合并于此：https://github.com/Moshuiwang/lingxi/issues/330 、https://github.com/Moshuiwang/lingxi/issues/469#issuecomment-5474257188 、https://github.com/Moshuiwang/lingxi/issues/521 、https://github.com/Moshuiwang/lingxi/issues/812#issuecomment-5703195634 、https://github.com/Moshuiwang/lingxi/issues/812#issuecomment-5703645397 、https://github.com/Moshuiwang/lingxi/issues/812#issuecomment-5708280359 、https://github.com/Moshuiwang/lingxi/issues/812#issuecomment-5714640738 、https://github.com/Moshuiwang/lingxi/issues/162

# 派发卡生成

你是编排者。派发任何子代理前，用 `${CLAUDE_PLUGIN_ROOT}/templates/派发卡.md` 生成一张派发卡：条款不得删减，只填具体值；派出后立即自挂兜底观察。

## 步骤

1. 读模板 `${CLAUDE_PLUGIN_ROOT}/templates/派发卡.md`（模板头部出处注释不进卡面）。
2. 填「现场」：worktree 绝对路径与分支、私有 scratchpad 子目录、文件归属范围（只许改哪些）、碰运行路径时从真实入口到改动点的调用链（只读核对范围；需改动才能接线的文件列进归属）、并行组与文件边界（同批并行卡边界不重叠，越界即停）、角色配置（引合同 §5「角色与配置」表的行，表外配置不得使用）、时间预估（工作时间引时间校准表行号 + 机器等待，给北京时间预计交回时点）；派出时把本卡将创建的 worktree / 分支 / 临时目录登记进任务表「资源登记」。
3. 填「必做项」：按 Step 的动作与可观察产物写，细到能直接开工，不细到逐条命令；写明验证命令、超时口径（按上次实测耗时并写出处，不抄旧值）与完成标准（以退出码判绿）；卡面「现状 / 前提」逐条标来源（实取 / 记忆 / 推断）；写明命名类值的唯一真源文件与依赖卡的等待点；同批并行卡各自独立的测试支撑文件名。
4. 六条款与附加条款原样保留；审查卡另填「审查派发」小节。
5. 派出后按下节自挂兜底观察，记下预计时长与到点要查的外部证据。
6. 可选留痕：派出后在 Trace Issue 评论或任务表引用块留一行含 Step ID 与时刻，供看板取开工时刻（不留则该步骤的开工时刻显示 `?`）。

## 条款正文（唯一权威 = 模板）

六条款（源自 `METHOD.md` v16 §6.4，现 §四「派发、审核与验证」）、实测附加条款与审查派发条款的正文**只在** `${CLAUDE_PLUGIN_ROOT}/templates/派发卡.md` 维护，本 skill 不再复写；每条的事故出处见模板头部出处注释、本 skill 出处行与 `CHANGELOG.md` 对应版本条目。改条款只改模板。

## 编排者侧

- 每次派发自挂兜底观察：预计时长 + 到点查外部证据（worktree HEAD、进程表、CI API），不信代理的沉默。
- 收到「在等 X」当场给 X 挂自己的观察（后台 `until <目标达成> || 超时`，判活条件同模板「等待只认自己」），到点无动静主动介入；绝不裸等。
- 子代理因传输错误中断时，用原任务续跑可零返工恢复（https://github.com/Moshuiwang/lingxi/issues/304）。
- 多路并行时每路各挂兜底观察；本机完整门禁独占期间不派任何测试类任务；编排者只派发与回收、不亲自实施；并行实施、串行整合（`METHOD.md` §四「并行纪律」）。
- 子代理运行中不发改口径消息（长回合读不到队列消息），要改口径等其收口再续派（https://github.com/Moshuiwang/lingxi/issues/812#issuecomment-5702976511 ；采用方项目 A #18 评论 5831198642）。
- 真实外部写按合同 §2 的执行通路执行、不交实施卡；执行者在会话里敲命令时单独成条、绝对路径，不串联 `cd` / `&&` / 管道 / 变量前缀（复合命令绕过权限白名单被拦）；远端命令落脚本文件执行，参数不带 shell 元字符（采用方项目 A #18 评论 5770822176 、采用方项目 A #18 评论 5831198642 、采用方项目 A #18 评论 5807711659）。

## 审查派发（编排者侧；审查卡条款见模板「审查派发」节）

- 编排者先用 grep / git diff 自己坐实机械性与文档类发现（通常占一半以上），只把行为面 / 合同面的发现派对抗验证（https://github.com/Moshuiwang/lingxi/issues/203 期实测省约 85%）。
- 给外部审查收敛线：按威胁模型裁——会真的废掉产品负责人窗口的必修；需要刻意环境操纵才能触发的明确接受，写进代码或文档「已知边界」并说明为什么接受。
- 修复卡把审核者探针复制进修复者 scratchpad；定向复核由同一审核者用改写版再攻（采用方项目 A #1 评论 5756158342）。
