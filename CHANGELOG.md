# Changelog

本文件记录 trace-kit 套件的变化，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)；版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)（`0.x` = 尚未稳定，字段与目录可能变）。**每个资产条目都带出处**（形成它的 lingxi Issue / 复盘 / 事故链接）与验证口径；没有出处的资产不进套件。

## 日落条款

- 每个资产必须可追溯到出处；采用本套件的项目在一个 Trace 里一次都没用到、没填写的机制，列为下一版删除候选（与 `METHOD.md` §九日落条款同构）。
- 修订默认净减法：新增资产须同时提名删除候选；`template/` 与 `plugin/` 的体量不得超过上一版，除非 CHANGELOG 写明理由。
- `METHOD.md` 正文只随 lingxi #147 的版本升级同步，不在本仓单独修订。

## [Unreleased]

## [0.1.0] - 2026-09-02

首个版本。分级清单（G1 直接搬 / G2 去 lingxi 名词参数化 / G3 只作示例）与逐项出处见 [Trace #1 第 0 步评论](https://github.com/Moshuiwang/trace-kit/issues/1#issuecomment-5503411104)；下面按目录列出带入的资产。

### Added

**`METHOD.md`（G1）**

- 长期执行计划与 Execution Trace 方法正文 v16，原样搬运 — 出处 [lingxi #147](https://github.com/Moshuiwang/lingxi/issues/147)（版本记录 v9→v16，各机制条款可追溯到复盘 [#104](https://github.com/Moshuiwang/lingxi/issues/104#issuecomment-5277196628) / [#162](https://github.com/Moshuiwang/lingxi/issues/162#issuecomment-5308799076) / [#328](https://github.com/Moshuiwang/lingxi/issues/328#issuecomment-5447228230) / [#469](https://github.com/Moshuiwang/lingxi/issues/469#issuecomment-5474257188)）— 验证：17 个 `[tracking]` Trace 按其生成与执行。

**`plugin/`（Claude Code 插件；出处表见 `plugin/README.md`）**

- `skills/kickoff`、`skills/takeover`、`skills/handoff`（G2）— 出处 [复盘 #330](https://github.com/Moshuiwang/lingxi/issues/330) P0 — 验证：#358→#521 七个 Trace 合同为六段式；六任编排者交接 / 接管。
- `skills/guardian`（G2）— 出处 #147 v16 §6.8、[rc22 复盘](https://github.com/Moshuiwang/lingxi/issues/469#issuecomment-5474257188) — 验证：#469、#521 两次元守护实践（+ #328 接力试验）。
- `skills/dispatch-card`（G1 六条款 + G2 附加条款）— 出处 #147 §6.4（[#203 复盘](https://github.com/Moshuiwang/lingxi/issues/203)）、[PR #299](https://github.com/Moshuiwang/lingxi/pull/299)（退出码）、[#521](https://github.com/Moshuiwang/lingxi/issues/521)（私有 scratchpad / 非 editable venv）— 验证：#203 / #304 / #328 / #373 / #469 / #521 派发卡沿用。
- `templates/合同.md`（G2）— 出处 #330 P0-5，结构抽取自 [#304](https://github.com/Moshuiwang/lingxi/issues/304)；`templates/任务表.md`、`验收.md`、`tracking-issue.md`（G1）— 出处 [docs/traces/README.md](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/README.md)（#328 载体裁定）— 验证：8 个 Trace 目录；`templates/派发卡.md` 同 dispatch-card。
- `plugin/.claude-plugin/plugin.json`、根 `.claude-plugin/marketplace.json` — 安装两步的载体（`claude plugin validate --strict` 通过）。

**`template/` 文档与 GitHub 约定（G2；每文件引言带出处）**

- `AGENTS.md` / `CLAUDE.md` / `.github/copilot-instructions.md` — 出处 [lingxi AGENTS.md](https://github.com/Moshuiwang/lingxi/blob/caa845d/AGENTS.md)（2026-08-08 OAuth 通道劫持、2026-08-23 变异行卷进提交两次事故形成「谁建谁清 / 单客户端 / 独立 worktree」底线）— 验证：全仓每次任务读取。
- `docs/README.md`（内容归属表）、`docs/协作约定.md`、`docs/决策记录/README.md`、`docs/参考证据/README.md`、`docs/技术设计/README.md`、`docs/产品合同.md`、`docs/当前能力.md` 骨架 — 出处 lingxi 同名文件（18–29 次修订）— 验证：全仓。
- `docs/技术设计/验证与门禁.md` — 出处 lingxi 同名文件（68 次修订）；证据层级对照 [#334](https://github.com/Moshuiwang/lingxi/issues/334)、CI 分层 [#82](https://github.com/Moshuiwang/lingxi/issues/82)、本机同构 [#236](https://github.com/Moshuiwang/lingxi/issues/236)、变异验红 #304 裁定 + [#469 假红事故](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/参考证据/验证与门禁形成记录.md)。
- `docs/技术设计/验收矩阵.md`（`V-*` 三态 + 合同条款覆盖清单 + 体量预算）— 出处 lingxi 同名（142 次修订）、[#335](https://github.com/Moshuiwang/lingxi/issues/335)、[#479](https://github.com/Moshuiwang/lingxi/issues/479)、[#100](https://github.com/Moshuiwang/lingxi/issues/100) 对账。
- `docs/traces/README.md`（G1）— 出处 [#328 复盘](https://github.com/Moshuiwang/lingxi/issues/328#issuecomment-5447228230)、#330 — 验证：8 个 Trace 目录。
- `docs/协作/执行方法.md` 稳定跳转入口 — 出处 lingxi `docs/协作/开工计划模板.md`。
- Issue 模板四份（change 含 `TO PM` 九项、decision、research、bug）与 PR 模板 — 出处 lingxi `.github/`（f99bdf5 起）— 验证：500+ Issue / 298 PR。
- `CHANGELOG.md` 约定与版本号规则 — 出处 [#417](https://github.com/Moshuiwang/lingxi/issues/417)、lingxi `deploy/README.md`「版本号规则」— 验证：2.0.0 + rc21–rc23 三批。

**`examples/lingxi/README.md`（G3）**

- lingxi 特有实现清单（飞书 / MCP / 权限表 / 内测名单闸 / 文案目录 / 四镜像 / 迁移链 / L1–L3 分档 / 七道闸 / 日志留存 / 备份演练等）、一个项目的实际取值（模型配比、常设授权、P2 豁免、bootstrap PR、`Image-Candidate`）、8 个三件套真实样本、方法沿革表 — 全部链接固定到 `caa845d`，不复制正文。

**套件自身（`scripts/kit/`、`init.sh`、`.github/workflows/kit-selfcheck.yml`）**

- `init.sh`（把 `template/` 提升到根）、`check_no_lingxi.sh`（禁词）、`check_links.py`、`smoke.sh`（空项目冒烟）、`refill_diff.sh`（自回灌）— 出处 Trace #1 合同 §4 自验证两条。

### 明确不带入（有出处但属 lingxi 特有，或验证不足）

<!-- 由编排者在 S-6a 填写 -->
