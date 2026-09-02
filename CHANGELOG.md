# Changelog

本文件记录 trace-kit 套件的变化，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)；版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)（`0.x` = 尚未稳定，字段与目录可能变）。**每个资产条目都带出处**（形成它的 lingxi Issue / 复盘 / 事故链接）与验证口径；没有出处的资产不进套件。

## 日落条款

- 每个资产必须可追溯到出处；采用本套件的项目在一个 Trace 里一次都没用到、没填写的机制，列为下一版删除候选（与 `METHOD.md` §九日落条款同构）。
- 修订默认净减法：新增资产须同时提名删除候选；`template/` 与 `plugin/` 的体量不得超过上一版，除非 CHANGELOG 写明理由。
- `METHOD.md` 正文只随 lingxi #147 的版本升级同步，不在本仓单独修订。

## [Unreleased]

## [0.1.0] - 2026-09-02

首个版本。分级清单（G1 直接搬 / G2 去 lingxi 名词参数化 / G3 只作示例）与逐项出处见 [Trace #1 第 0 步评论](https://github.com/Moshuiwang/trace-kit/issues/1#issuecomment-5503411104)；下面按目录列出带入的资产。

**证据等级**（产品负责人全局 1–7 级）：套件脚本与文档 = 4（本仓 `kit-selfcheck` 在 GitHub Actions 上跑通空项目冒烟）；`template/.github/workflows/*` = 3（YAML 可解析、与本机 `check.sh` 现读一致，**未在真实 Actions 上运行过**）；插件 = 3 + 本机真实旅程（`--plugin-dir` 加载、kickoff 在空项目生成三件套）；远端 `claude plugin install` 未验证。

**未验证 / 日落候选**：template 工作流的真实 Actions 运行与 `Main Publish` 的 GHCR 推送、插件远端安装，留给第一个真实试穿项目；`check_size_ratchet.py` 若第一个项目用不上，下一版删除。

### Added

**`METHOD.md`（G1）**

- 长期执行计划与 Execution Trace 方法正文 v16，原样搬运 — 出处 [lingxi #147](https://github.com/Moshuiwang/lingxi/issues/147)（版本记录 v9→v16，各机制条款可追溯到复盘 [#104](https://github.com/Moshuiwang/lingxi/issues/104#issuecomment-5277196628) / [#162](https://github.com/Moshuiwang/lingxi/issues/162#issuecomment-5308799076) / [#328](https://github.com/Moshuiwang/lingxi/issues/328#issuecomment-5447228230) / [#469](https://github.com/Moshuiwang/lingxi/issues/469#issuecomment-5474257188)）— 验证：17 个 `[tracking]` Trace 按其生成与执行。

**`plugin/`（Claude Code 插件；出处表见 `plugin/README.md`）**

- `skills/kickoff`、`skills/takeover`、`skills/handoff`（G2）— 出处 [复盘 #330](https://github.com/Moshuiwang/lingxi/issues/330) P0 — 验证：#358→#521 七个 Trace 合同为六段式；六任编排者交接 / 接管。
- `skills/guardian`（G2）— 出处 #147 v16 §6.8、[rc22 复盘](https://github.com/Moshuiwang/lingxi/issues/469#issuecomment-5474257188) — 验证：#469、#521 两次元守护实践（+ #328 接力试验）。
- `skills/dispatch-card`（G1 六条款 + G2 附加条款）— 出处 #147 §6.4（[#203 复盘](https://github.com/Moshuiwang/lingxi/issues/203)）、[#521](https://github.com/Moshuiwang/lingxi/issues/521)（私有 scratchpad / 非 editable venv）— 验证：#203 / #304 / #328 / #373 / #469 / #521 派发卡沿用。
- `templates/合同.md`（G2）— 出处 #330 P0-5，结构抽取自 [#304](https://github.com/Moshuiwang/lingxi/issues/304)；`templates/任务表.md`、`验收.md`、`tracking-issue.md`（G1）— 出处 [docs/traces/README.md](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/README.md)（#328 载体裁定）— 验证：8 个 Trace 目录；`templates/派发卡.md` 同 dispatch-card。
- `plugin/.claude-plugin/plugin.json`、根 `.claude-plugin/marketplace.json` — 安装两步的载体（`claude plugin validate --strict` 通过）。

**`template/` 文档与 GitHub 约定（G2；每文件引言带出处）**

- `AGENTS.md` / `CLAUDE.md` / `.github/copilot-instructions.md` — 出处 [lingxi AGENTS.md](https://github.com/Moshuiwang/lingxi/blob/caa845d/AGENTS.md)（2026-08-08 OAuth 通道劫持、2026-08-23 变异行卷进提交两次事故形成「谁建谁清 / 单客户端 / 独立 worktree」底线）— 验证：全仓每次任务读取。
- `docs/README.md`（内容归属表）、`docs/协作约定.md`、`docs/决策记录/README.md`、`docs/参考证据/README.md`、`docs/技术设计/README.md`、`docs/产品合同.md`、`docs/当前能力.md` 骨架 — 出处 lingxi 同名文件（18–29 次修订）— 验证：全仓。
- `docs/技术设计/验证与门禁.md` — 出处 lingxi 同名文件（68 次修订）；证据层级对照 [#334](https://github.com/Moshuiwang/lingxi/issues/334)、CI 分层 [#82](https://github.com/Moshuiwang/lingxi/issues/82)、本机同构 [#236](https://github.com/Moshuiwang/lingxi/issues/236)、变异验红 #304 裁定 + [#469 假红事故](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/参考证据/验证与门禁形成记录.md)。
- `docs/技术设计/验收矩阵.md`（`V-*` 三态 + 合同条款覆盖清单 + 体量预算）— 出处 lingxi 同名（142 次修订）、[#335](https://github.com/Moshuiwang/lingxi/issues/335)、[#479](https://github.com/Moshuiwang/lingxi/issues/479)、[#100](https://github.com/Moshuiwang/lingxi/issues/100) 对账。
- `docs/traces/README.md`（G1）— 出处 [#328 复盘](https://github.com/Moshuiwang/lingxi/issues/328#issuecomment-5447228230)、#330 — 验证：8 个 Trace 目录。
- `docs/协作/执行方法.md` 稳定跳转入口 — 出处 lingxi `docs/协作/开工计划模板.md`。
- Issue 模板四份（change 含 `TO PM` 九项、decision、research、bug）与 PR 模板 — 出处 lingxi `.github/`（f99bdf5 起）— 验证：约 220 个 Issue / 301 个合并 PR。
- `CHANGELOG.md` 约定与版本号规则 — 出处 [#417](https://github.com/Moshuiwang/lingxi/issues/417)、lingxi `deploy/README.md`「版本号规则」— 验证：2.0.0 + rc21–rc23 三批。

**`examples/lingxi/README.md`（G3）**

- lingxi 特有实现清单（飞书 / MCP / 权限表 / 内测名单闸 / 文案目录 / 四镜像 / 迁移链 / L1–L3 分档 / 七道闸 / 日志留存 / 备份演练等）、一个项目的实际取值（模型配比、常设授权、P2 豁免、bootstrap PR、`Image-Candidate`）、8 个三件套真实样本、方法沿革表 — 全部链接固定到 `caa845d`，不复制正文。

**套件自身（`scripts/kit/`、`init.sh`、`.github/workflows/kit-selfcheck.yml`）**

- `init.sh`（把 `template/` 提升到根）、`check_no_lingxi.sh`（禁词）、`check_links.py`、`smoke.sh`（空项目冒烟）、`refill_diff.sh`（自回灌）— 出处 Trace #1 合同 §4 自验证两条。

**`template/` 分层 CI、通用检查与本机同构（G1/G2；每脚本 docstring 带出处）**

- 工作流 `story.yml`（`Story Fast`，PR→`epic/**`）/ `ci.yml`（`Epic Full`，PR→`main`，输出候选证明，`Image-Candidate: true` trailer 显式触发镜像）/ `publish.yml`（`Main Publish`，回读候选证明、树一致才构建并发布不可变 tag `YYYYMMDD-<sha12>`）/ `docs.yml` — 出处 [#82](https://github.com/Moshuiwang/lingxi/issues/82)、[#43](https://github.com/Moshuiwang/lingxi/issues/43)、[#278](https://github.com/Moshuiwang/lingxi/issues/278) — 验证：lingxi 2026-08-07 起约 250 个 PR 与每次合 main；本套件只做静态校验（见「未验证」）。
- `classify_story_changes.py`（docs / fast / full 三档，未知路径一律 full）— 出处 #82 — 验证：同上。
- `check_markdown_links.py`（G1，零差异）— 出处 lingxi 2026-07-25 CI 基线 — 验证：301 个合并 PR。
- `check_acceptance_matrix.py`（三态状态列、编号唯一、合同章节覆盖、分册目录扫描）— 出处 lingxi 6c636e2（2026-08-06）、[#479](https://github.com/Moshuiwang/lingxi/issues/479)。
- `check_matrix_row_size_ratchet.py`（单行 800B 棘轮 + 总量触发线）— 出处 [#335](https://github.com/Moshuiwang/lingxi/issues/335)。
- `check_docs_size_budget.py`（开工必读集合计 ≤ 32KB）— 出处 lingxi [PR #299](https://github.com/Moshuiwang/lingxi/pull/299)、[#520](https://github.com/Moshuiwang/lingxi/issues/520) 扩容留痕。
- `check_contract_attribution.py`（归属核对登记制：整行逐字相等、例外每次可见；861→248 行只留机制）— 出处 [#238](https://github.com/Moshuiwang/lingxi/issues/238)（2026-08-19 三路复查坐实两个绕过面）。
- `check_size_ratchet.py`（源码行数棘轮，`--refresh` 只减不增）— 出处 #238 — 产品负责人清单未点名，作矩阵棘轮同族骨架带入，可删。
- `write_epic_candidate.py` / `verify_epic_candidate.py`（候选证明写出与回读，Token 不跨主机）— 出处 #82。
- `verify_docs.sh` / `verify_repository.sh`（缺工具明确失败、解释器下限、shellcheck 锁版本、行尾空白、敏感 `.env` 与私钥扫描、`unittest`）— 出处 lingxi 2026-07-25 基线、[PR #3](https://github.com/Moshuiwang/lingxi/pull/3)（提交 2d34582）。
- `scripts/dev/check.sh` + `gate_spec.py` + `local_layer.py`（三层 docs / fast / full；层级复用分类器；Python 版本与 extras 现读自工作流，解析失败响亮失败；venv 默认重建、`uv` 退回；跑完核对工作树洁净）— 出处 [#236](https://github.com/Moshuiwang/lingxi/issues/236)（PR #233 漂移事故）— 验证：#304 / #328 / #373 / #469 / #521 每批「本机 full 绿」。
- 可运行最小骨架 `src/app`（常驻循环 / healthcheck / migrate）、`Dockerfile`（固定基础镜像、非 root）、`pyproject.toml`、`tests/`（79 条）— 让空项目从第一天就有会变红的门禁。

**`template/deploy/`（G2）**

- `compose.yaml` + `compose.stage.yaml` / `compose.prod.yaml`（profile 常驻 / job、不可变 tag `${REGISTRY:?}/…:${TAG:?}${DIGEST:-}`、job 不配 restart、常驻服务 healthcheck 与资源限制、凭据按服务 `env_file` 不入库、生产零 `build:`）+ `.env.example` — 出处 [#62](https://github.com/Moshuiwang/lingxi/issues/62)、[#153](https://github.com/Moshuiwang/lingxi/issues/153)、#494 / #496 资源合同 — 验证：预发环境 20+ 次升级、2026-09-02 生产首发。
- `check_deploy_contract.py`（文本级契约，200 行）与 `verify_compose_structure.sh`（渲染级：预发与生产结构相同只有配置不同）— 出处 #62（断言 M2-62-13）。
- `deploy/README.md`、`生产部署runbook.md`（digest 固定、单实例、首发不灰度、回滚判据、观察期、secret 注入）、`验收前部署配置清单.md`（闸清单 + 五层自检法）— 出处 lingxi Trace [#373](https://github.com/Moshuiwang/lingxi/issues/373) S-H2-4、[#135](https://github.com/Moshuiwang/lingxi/issues/135)、b8ae10b（Epic D）、[#521](https://github.com/Moshuiwang/lingxi/issues/521) 生产实录。
- `监控告警.md` + `scripts/ops/host_health_alert.py`（docker inspect 判 unhealthy / exited / 重启循环 → 群告警 + 恢复通知 + 去重 + 单实例；`send_alert()` 单一扩展点）+ systemd timer 单元 — 出处 Trace #373 D5、[#494](https://github.com/Moshuiwang/lingxi/issues/494) 实证（79 秒转 unhealthy / 107 秒告警）。

### 明确不带入（有出处但属 lingxi 特有，或验证不足；清单见 `examples/lingxi/README.md`）

- lingxi 专属检查：`check_project_skills` / `check_core_layering` / `check_db_timeouts` / `check_content_version` / `check_alembic_revisions` / `check_crypto_vectors` / `check_runtime_dependencies` / `check_installed_package` / `check_permission_impact` / `check_l1_assets` / `check_agent_sdk_binding`、四镜像构建与候选镜像包（`build_image.sh` / `push_image.py` / `image_manifest.py` / `verify_epic_candidate_bundle.py`）、`verify_old_image_new_schema.sh`、`check_migration_chain.sh`、分类器的 L1 / L3 精确路径分档（[#498](https://github.com/Moshuiwang/lingxi/issues/498)）。
- 部署面的日志留存（[#343](https://github.com/Moshuiwang/lingxi/issues/343)）、备份恢复演练脚本、OAuth Bridge worker、数据库凭据源（[#411](https://github.com/Moshuiwang/lingxi/issues/411)）、七道闸内容、外部应用侧带外配置。
- 本机 / 平台事实（codex 调用姿势、容器与端口配方、GitHub App 令牌行为等）：属会话记忆，不属套件。
- 产品负责人的模型路由、P2 豁免授权、`gh pr ready/merge` 常设授权、epic 分支 bootstrap PR 先例：作为「一个项目的实际取值」示例留在 `examples/lingxi/`。
- 派发卡「门禁命令退出码显式捕获、禁止 `cmd > log; echo EXIT=$?` 与管道收尾」条款：本机记忆两次实证（2026-08-24），但 lingxi 仓与 Issue 均无留痕，按「没有出处的不进」未带入；lingxi 留痕后下版纳入。
- `#278` 的「跟踪 PR 首次 synchronize 默认跳过 image」成本优化：lingxi 四镜像特有，未带入（trailer 显式触发机制已带入）。
