# Trace 执行载体（docs/traces/）

> 出处：lingxi [docs/traces/README.md](https://github.com/Moshuiwang/lingxi/blob/caa845d77fbd2d6381de304dc6047498aa84c782/docs/traces/README.md)（[#328](https://github.com/Moshuiwang/lingxi/issues/328) 载体裁定、[#330](https://github.com/Moshuiwang/lingxi/issues/330) 复盘结论）；验证：8 个 Trace 目录；分档 G1（方法入口改为本仓库 `docs/协作/执行方法.md`）。

长期执行计划（Execution Trace）的**合同与执行状态**以本目录下受版本控制的文件为唯一正文；对应的 GitHub `[tracking]` Issue 降级为瘦指针与产品负责人裁定界面。方法论正文见[长期执行方法入口](../协作/执行方法.md)所指的套件 `METHOD.md`；本目录只承载按该方法生成的具体 Trace。三件套的空白模板与 kickoff / takeover / handoff skill 由 [trace-kit 插件](https://github.com/Moshuiwang/trace-kit/tree/v0.1.0/plugin)提供。

## 准入

满足任一条件的工作需要建 Trace 目录：多 Epic / 多批次 / 顺序依赖 / 多编排者接力 / 高风险（部署、权限、数据）。单 Issue 可完成的工作不建 Trace，照常走 Issue。启用本载体之前的历史 Plan 不迁移，其留痕仍在原 Issue。

## 结构（每 Trace 一个子目录：`<issue号>-<中文短名>/`）

| 文件 | 内容 | 谁改、怎么改 |
| --- | --- | --- |
| `合同.md` | 六段式开工合同（目标 / 授权终点 / 不做清单 / 验收标准 / 成本预算 / 主线声明）+ Epic 与批次结构 + 完成定义 | 建立与修订一律走 PR；**PR 合并即产品负责人批准**。未写进合同的授权不存在 |
| `任务表.md` | 全部 Step 的复选框状态表，**状态即文件当前值** | 编排者随执行直接 commit 更新（无需 PR）；行格式 `- [x] S-X-N 一句话（关键指针）` |
| `验收.md` | 逐 Epic 可观察完成标准 + 证据等级目标/现值 + 关联[验收矩阵](../技术设计/验收矩阵.md) `V-*` 行 | 编排者随收口 commit 更新；证据等级口径见[验证与门禁](../技术设计/验证与门禁.md) |

## 看板（派生视图，只显示不阻断）

装了 trace-kit 插件后，在 tmux 里跑 `/trace-kit:board` 可随时看到当前 Trace 的进度图：按任务表 `##` 章节画大模块，颜色即状态，边框即审核轮数，标题行右侧是「已跑或实际 / 预估」分钟，头部给出阶段（含合入主干 / 已发布 / 预发 / 生产 / 收口五级）、阻塞、下一步、预算、存疑、最后外部证据。

- **任务表是界面，GitHub 是事件日志，看板是派生视图**：看板不是真源、不产生结论，任何一格都能回 `git log` / `gh` 核。
- **只显示、不阻断**：不挡合并、不做门禁、不判活（判活是元守护的事）；证据拿不到就显示「未知」，不回落、不猜。
- Step 行尾可写可选标签块 `[t:impl needs:S-1,S-2 own:x est:45m]`（四键全可选，不写照常解析）；项目专属证据（镜像 tag、编排窗口名模式、预算计数命令）写在 `docs/traces/board.toml`（模板见插件 `templates/board.toml`）。
- 收口时把一帧纯文本快照归档到 `docs/traces/<issue号>-<短名>/看板.txt`（`/trace-kit:board` 的 `--dump`），随收口评论一并留痕。

## 与 Issue / 评论的分工（现行做法不变）

- `[tracking]` Issue 正文 = 瘦指针：目标一句话 + 三件套链接 + 当前阶段一行 + 原正文折叠留档。
- 产品负责人裁定评论、编排者交接评论、批次收口评论**仍发在该 Issue**；收口评论附任务表更新 commit 链接。
- 缺陷、工作项、决策留痕照常走各自 Issue；产品事实照常写 `docs/` 正文。
