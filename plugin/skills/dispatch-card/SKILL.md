---
name: dispatch-card
description: 从模板生成实施 / 审查子代理的派发卡（六条款 + 实测附加条款 + 编排者侧兜底观察 + 审查派发小节）。在编排者要派发实施、修复或审查子代理时使用。
---

> 出处：lingxi https://github.com/Moshuiwang/lingxi/issues/147（§6.4，源自 #203 复盘 https://github.com/Moshuiwang/lingxi/issues/203）；验证：#203 / #304 / #328 / #373 / #469 / #521 派发卡沿用，否决裁定 6 例 6 对

# 派发卡生成

你是编排者。派发任何子代理前，用 `${CLAUDE_PLUGIN_ROOT}/templates/派发卡.md` 生成一张派发卡：条款不得删减，只填具体值；派出后立即自挂兜底观察。

## 步骤

1. 读模板 `${CLAUDE_PLUGIN_ROOT}/templates/派发卡.md`（模板头部出处注释不进卡面）。
2. 填「现场」：worktree 绝对路径与分支、私有 scratchpad 子目录、文件归属范围（只许改哪些）、模型 / 档位（合同 §5）。
3. 填「必做项」：按 Step 的动作与可观察产物写，细到能直接开工，不细到逐条命令；写明验证命令、超时口径与完成标准。
4. 六条款与附加条款原样保留；审查卡另填「审查派发」小节。
5. 派出后按下节自挂兜底观察，记下预计时长与到点要查的外部证据。

## 六条款（`METHOD.md` §6.4；第 3 条的项目门禁耗时括注已参数化）

1. **一路做到底**：按自己列的顺序做完再报，不逐步向编排者确认；只有需要产品取舍、扩大范围、或不同意编排者裁定时才停下。
2. **不得派发任何子代理。**
3. **长命令显式传足够长的超时参数**，不让命令转入后台再裸等通知。
4. **启动的验证必须等到结束并消化结果后才许收口**，不得「已启动」即停。
5. **报告格式含逐条处理状态**：已改 / 未改 + 原因——不同意编排者的裁定是允许的，但要给证据（实测 6 例否决 6 例都对）。
6. 公开可见内容标注与最小披露复核按《协作约定》。

## 实测附加条款（每条一句，带出处）

- 长命令显式传超时（Bash 工具 `timeout` 毫秒，上限 600000）——命令被转入后台后代理裸等通知、改动留在工作区不提交（`METHOD.md` §6.4 第 3 条，源自 https://github.com/Moshuiwang/lingxi/issues/203 复盘）。
- 预计 >2 分钟的命令一律后台或显式超时；等待用 until 循环，禁 sleep 串联（https://github.com/Moshuiwang/lingxi/issues/330）。
- 每个代理独立 worktree（Agent 工具 `isolation: worktree`），同一工作树同一时刻只允许一个写入者（https://github.com/Moshuiwang/lingxi/issues/203 事故实证）。
- 临时文件只放私有 scratchpad 子目录，不与其他代理共用文件名——共用目录使一批变异静默跑空（https://github.com/Moshuiwang/lingxi/issues/521）。
- Python 项目变异实测全程 `python -B` 或逐次清 `__pycache__`，不以 mtime / size 判断源码已还原（https://github.com/Moshuiwang/lingxi/issues/469#issuecomment-5474257188）。
- 先确认被测模块的 `__file__` 在源码树——非 editable 安装的 venv 改源码不生效，全绿是假绿（https://github.com/Moshuiwang/lingxi/issues/521）。
- 改完先 commit 再汇报，工作树上不留未提交改动；进等待必须上报（https://github.com/Moshuiwang/lingxi/issues/330）。
- 报告逐条「已改 / 未改 + 原因」，与卡面裁定不一致处给证据（https://github.com/Moshuiwang/lingxi/issues/203）。

## 编排者侧

- 每次派发自挂兜底观察：预计时长 + 到点查外部证据（worktree HEAD、进程表、CI API），不信代理的沉默。
- 收到「在等 X」当场给 X 挂自己的观察（后台 `until <目标达成> || 超时`），到点无动静主动介入；绝不裸等。
- 子代理因传输错误中断时，用原任务续跑可零返工恢复（https://github.com/Moshuiwang/lingxi/issues/304）。

## 审查派发

- 一个固定候选只允许一名独立审核者；只读、不修、不参与实现；候选 SHA 改变后旧结论失效（`METHOD.md` §6.6）。
- 编排者先用 grep / git diff 自己坐实机械性与文档类发现（通常占一半以上），只把行为面 / 合同面的发现派对抗验证（https://github.com/Moshuiwang/lingxi/issues/203 期实测省约 85%）。
- 给外部审查收敛线：按威胁模型裁——会真的废掉产品负责人窗口的必修；需要刻意环境操纵才能触发的明确接受，写进代码或文档「已知边界」并说明为什么接受。
- 批量审查从关键测试抽 3–5 个独立复做变异实测，在审核者自己的 worktree 内做（https://github.com/Moshuiwang/lingxi/issues/521）。
