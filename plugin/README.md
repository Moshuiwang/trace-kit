# trace-kit 插件（`plugin/`）

## 是什么

把 Execution Trace 工作方法（正文见仓库根 `METHOD.md`）里「每个 Trace 都要重复做」的六件事做成 Claude Code skill，并附三件套与派发卡的空白模板：

| skill | 何时用 | 产出 |
| --- | --- | --- |
| `/kickoff` | 规划新 `[tracking]` Trace、产品负责人说「开工 / 立项 / 下一个 Trace」 | `docs/traces/<issue号>-<短名>/` 三件套（走 PR，合并即批准）+ `[tracking]` Issue 瘦指针 |
| `/takeover` | 新会话接手一个进行中的 Trace（接手 prompt 的第一步） | 现场核实结论 + 接管登记评论 |
| `/handoff` | 上下文接近上限、编排者换班、产品负责人说「交接」 | 七节交接评论（含一句话接手 prompt） |
| `/guardian` | 合同指定本会话转任元守护、产品负责人说「你转元守护 / 守着」 | 判活记录、失联取证评论、继任窗口 |
| `/dispatch-card` | 编排者要派发实施、修复或审查子代理 | 一张派发卡（六条款 + 实测附加条款 + 审查小节） |
| `/board` | 产品负责人或编排者要看当前 Trace 做到哪 / 堵在哪 / 轮了几轮 / 花了多少分钟；收口要归档一帧快照 | tmux 里的只读 TUI（简易 / 复杂两视图），或 `--dump` 一帧纯文本 |

模板在 `templates/`：`合同.md`（六段式）、`任务表.md`、`验收.md`、`派发卡.md`、`tracking-issue.md`、`board.toml`（看板证据源配置示例）。skill 通过 `${CLAUDE_PLUGIN_ROOT}/templates/...` 读取它们。

## 怎么装

```
claude plugin marketplace add Moshuiwang/trace-kit
claude plugin install trace-kit@trace-kit
```

本地开发或试用（不安装，仅本会话生效）：在仓库根执行 `claude --plugin-dir ./plugin`。
校验：`claude plugin validate --strict plugin`（插件）与 `claude plugin validate --strict .`（市场清单）。

## 换什么

- **模型配比**：写进每个 Trace 合同 §5（编排 / 实施 / 唯一审核 / 元守护各一档），Trace 成形时经产品负责人确认。套件不预设；一个真实项目的取值见 `examples/lingxi/`。
- **tmux session 名与批次代号**：合同 §6 与任务表头部填写；`guardian` skill 的拉起命令只用占位符 `<session>` / `<批次代号>` / `<仓库目录>`。
- **Trace 目录短名规则**：`docs/traces/<issue号>-<短名>/`，短名一词概括目标（如 `rc24正式上线`），不含空格与斜杠；目录名一旦建立不改（交接与收口评论都用它定位）。
- **派发卡「六条款」第 3 条的门禁耗时**、报告格式的行数上限：按你的仓库填。
- **证据等级口径**：验收模板引用项目《验证与门禁》文档；骨架见套件 `template/docs/`。
- **合同路径的 CODEOWNERS**：在你的仓库建 `.github/CODEOWNERS`，把 `docs/traces/**/合同.md` 指给产品负责人，并在 main 分支规则集要求代码所有者审查——否则「合并即批准」只是约定，代理仍能自发自合（本仓 `.github/CODEOWNERS` 是样例）。

## 记录归属（三件套之外的内容放哪）

本机事实（路径、主机、容器、凭据坐标）→ 本机记忆，不进仓库；批次方法与踩坑 → 当前 Trace 的收口 / 复盘评论；方法修订 → `METHOD.md` 的源 Issue 候选；底线 → 仓库 `AGENTS.md`，且须重复验证后才固化。

## 出处表

每个文件头部各带一行「出处 + 验证口径」；汇总如下。

| 资产 | 出处 | 验证口径 |
| --- | --- | --- |
| `skills/kickoff` | [复盘 #330](https://github.com/Moshuiwang/lingxi/issues/330) P0 | #358 / #373 / #418 / #445 / #469 / #502 / #521 七个 Trace 合同均按此起草 |
| `skills/takeover` | 复盘 #330 P0；[#147](https://github.com/Moshuiwang/lingxi/issues/147) v14/v16 §6.8 接管登记 | #203（3 任）/ #304（4 批）/ #373（4 批接力）/ #469 / #521 继任接管 |
| `skills/handoff` | 复盘 #330 P0 | 同上，六任编排者交接 |
| `skills/guardian` | #147 v16 §6.8；[rc22 复盘](https://github.com/Moshuiwang/lingxi/issues/469#issuecomment-5474257188) | #469、#521 两次（+ #328 接力试验） |
| `skills/dispatch-card` | #147 §6.4（[#203 复盘](https://github.com/Moshuiwang/lingxi/issues/203)）；[#521](https://github.com/Moshuiwang/lingxi/issues/521)（scratchpad / 非 editable venv） | #203 / #304 / #328 / #373 / #469 / #521 派发卡沿用；否决裁定 6 例 6 对 |
| `skills/board`、`scripts/board.py` 与 `scripts/boardlib/`、`templates/board.toml` | [trace-kit #12](https://github.com/Moshuiwang/trace-kit/issues/12) v3 修订段；[lingxi #577](https://github.com/Moshuiwang/lingxi/issues/577) 子清单（#578 / #579 / #580 / #581 / #582 / #589） | `tests/board/` 夹具在 `kit-selfcheck` 上绿（含 Trace #1 真实历史回放）；[lingxi #606](https://github.com/Moshuiwang/lingxi/issues/606) 真实试穿 |
| `templates/合同.md` | 复盘 #330 P0-5；结构抽取自 [#304](https://github.com/Moshuiwang/lingxi/issues/304) | 七个 Trace 合同均为六段式 |
| `templates/任务表.md`、`templates/验收.md` | [docs/traces/README.md@caa845d](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/README.md)（[#328 复盘](https://github.com/Moshuiwang/lingxi/issues/328#issuecomment-5447228230) 载体裁定、#330） | #328 / #358 / #373 / #418 / #445 / #469 / #502 / #521 八个 Trace 目录 |
| `templates/派发卡.md` | 同 `skills/dispatch-card` | 同上 |
| `templates/tracking-issue.md` | #147 §八「给产品负责人」段 + docs/traces/README.md 瘦指针 | #328 起 8 个 Trace 的 `[tracking]` Issue |
| 「记录归属」一节 | 源项目 `docs/README.md` 归属表（[#328 复盘](https://github.com/Moshuiwang/lingxi/issues/328#issuecomment-5447228230)） | 两次纠正后固化 |
