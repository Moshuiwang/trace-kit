# trace-kit

把 lingxi 项目两个月（2026-07-24 → 09-02，17 个 Execution Trace、约 300 个合并 PR）实证有效的**工作方法资产**打包成可复用套件。它回答一个问题：一个由产品负责人（PM）+ 多个 AI 代理协作的仓库，怎样从第一天起就有**合同、门禁、证据与交接**，而不是靠口头约定。

套件四件东西：

| 件 | 是什么 | 谁用 |
| --- | --- | --- |
| `METHOD.md` | 执行方法正文（= lingxi Issue #147 v16 原样搬运，带版本头） | 规划者读它生成 Trace；编排者只执行获批 Trace |
| `plugin/` | Claude Code 插件：`kickoff` / `takeover` / `handoff` / `guardian` / `dispatch-card` 五个 skill + 三件套与派发卡模板 | 每个 Trace 都要重复做的五件事 |
| `template/` | 新项目骨架：代理约定、产品文档骨架、Issue / PR 模板、分层 CI 与风险分级器、通用检查、本机=CI 同构的 `check.sh`、部署骨架、可运行的最小 `app` | 新仓库开工第一天 |
| `examples/lingxi/` | G3 档：lingxi 特有实现只作示例（只链接、不复制） | 对照骨架看一个真实项目怎么填 |

当前版本 **v0.1.0**（`0.x` = 尚未稳定）。每个资产的出处链接、验证口径与**未验证层级**在 [`CHANGELOG.md`](CHANGELOG.md) 逐条列出。

---

## 一、三分钟上手（新项目）

**前提**：本仓库需开启 GitHub「Template repository」开关（Settings → General）。未开启时第一步改为：`git clone` 本仓 → 删掉 `.git` → `git init && git add -A && git commit -m init` → 再 `./init.sh`（脚本要求工作树洁净，未提交直接跑会被拒）。

```bash
# 1. 用套件做模板新建仓库，再把 template/ 提升到仓库根（init.sh 会删掉套件自身文件并自删）
gh repo create <你的仓库> --public --template Moshuiwang/trace-kit --clone && cd <你的仓库> && ./init.sh
git add -A && git commit -m "chore: 从 trace-kit 0.1.0 初始化"

# 2. 安装 Claude Code 插件（用户级，一次即可）
claude plugin marketplace add Moshuiwang/trace-kit && claude plugin install trace-kit@trace-kit
```

init 之后你的仓库根就是原 `template/` 的内容。开工第一天按顺序做：

1. `grep -rn '这里换成你的'` 列出全部占位，按仓库根 `README.md`「换什么」表逐项替换（项目名、`app` 服务名、产品合同章节、环境表、Issue 标签名）。
2. 跑一次本机门禁确认骨架自身全绿：`scripts/dev/check.sh full`（首次会建虚拟环境，机器上没有 pip 时自动退回 `uv`）。
3. 在 Claude Code 里用 `/trace-kit:kickoff` 起第一个 Execution Trace：产出 `docs/traces/<issue号>-<短名>/` 三件套 + `[tracking]` Issue 瘦指针，走 PR，**合并即产品负责人批准**。
4. 之后的每个批次：编排者按获批合同派发（`/trace-kit:dispatch-card`）、攒批、批次终点一次完整门禁 + 一次独立审查、收口评论、`/trace-kit:handoff` 交接；新会话用 `/trace-kit:takeover` 接手。

安装第二步的远端路径已实测（2026-09-02：市场添加 → 安装 → `claude plugin list` 显示 0.1.0 enabled）。

---

## 二、你是哪种读者

### 产品负责人

- 你批准的永远是**某一版具体的 Trace 合同**（`docs/traces/<issue号>-<短名>/合同.md`），不是笼统的方法；批准动作 = **你本人合并那个 PR**（本仓 `.github/CODEOWNERS` 已把 `docs/traces/**/合同.md` 指给你；配套的 main 分支规则集需你在 Settings → Rules 建，未建时「合并即批准」只是约定，机器人技术上仍能自合）。
- 中途只在两处参与：实施最前（合同末尾「批准时需一并裁定」清单，一次给齐、可单字回复）与 Trace 最后（收口验收）。中途不需要你试错。
- 看进度只看两处：任务表（`任务表.md`，状态即文件当前值）与 `[tracking]` Issue 的最新收口 / 交接评论。
- 授权原则：未写进合同的授权不存在；临时授权带失效时点；提交 / 推送 / 合并 / 发布 / 生产 / 删除各自单独授权。

### 规划者代理

1. 读 `METHOD.md` §一（五分钟使用法）、§四（合同要求）、§五（Ready 门）、§八（合同区字段）。
2. 用 `/trace-kit:kickoff` 起草六段式合同（目标 / 授权终点 / 不做清单 / 验收标准 / 成本预算 / 主线声明）+ 任务表 + 验收 + 瘦指针；每段不许留空，授权只写产品负责人**说过**的。
3. 三件套走 PR；合并前不派发任何实施；批准后把 Trace 交给一个**独立**的编排者会话，自己停止或转元守护（`/trace-kit:guardian`）。

### 编排者代理

- 接手第一步 `/trace-kit:takeover`：读三件套 + Issue 最新交接评论，逐项核实现场（main SHA、分支、未合并 PR、在途任务、部署面），在 Issue 登记「接管编排与唯一合并权」。
- 只派发 Ready 的 Step；每次派发用 `/trace-kit:dispatch-card` 出卡（六条款 + 实测附加条款），派发后自挂兜底观察（预计时长 + 到点查外部证据：worktree HEAD、进程表、CI），收到「在等 X」不裸等。
- 单一写入者：编排者持主工作树与合并权；实施子代理各用独立 worktree，改完先 commit 再汇报；审核子代理只读固定候选、不修。
- 攒批：批内小 PR 只跑快检，批次终点一次完整门禁 + 一次批量审查（唯一独立审核者）+ 统一修复包 + 同一审核者定向复核 + 唯一合并人合并。
- 收口固定序列：收口评论（UTC + 北京双标注、绑定候选 / 制品、各 Step 状态、证据等级、未验证清单、成员 Issue 回写、预算）→ `/trace-kit:handoff` 交接评论 → 继任窗口 → 接管登记 → 退场。临时 worktree / 容器 / 远端分支谁建谁清，收尾做残留盘点。
- 主线灯塔：任何派发前先问「不做它，当前里程碑能不能达成？」不能才做；新发现默认只登记不立项。

### 实施 / 审核子代理

- 按派发卡做，一路做到底，不逐步确认；只在需要产品取舍、扩大范围或不同意裁定时停下（不同意可以，给证据）。
- 不派子代理；长命令显式传超时；启动的验证等到结束再收口；报告逐条「已改 / 未改 + 原因」。
- 审核者：一个固定候选只有一名独立审核者，只读、不直接修复；变异实测全程 `python -B`（或逐次清 `__pycache__`），先确认被测模块的 `__file__` 在源码树。

### 元守护

`/trace-kit:guardian`：只以外部证据判活（窗口存活 + Issue / 任务表留痕新鲜度，30–60 分钟一查）；失联判定 = 窗口死亡且 >90 分钟无留痕 → 先取证留痕再按最新交接拉继任；不实施、不持合并权；承接产品负责人裁定并转发。

---

## 三、一个 Trace 的生命周期（术语速查）

```
输入 Issue ──► 规划者 /kickoff ──► 三件套 PR（合并=批准）──► 编排者 /takeover
   ──► 派发（/dispatch-card，独立 worktree）──► 攒批 ──► 批终：完整门禁 + 独立审查 + 修复包 + 复核
   ──► 合 main / 发布 / 部署（各自单独授权）──► 收口评论 ──► /handoff ──► 继任 或 Closed
```

- **三件套**（`docs/traces/<issue号>-<短名>/`）：`合同.md`（修订走 PR，合并即批准）、`任务表.md`（`- [x] S-X-N 一句话（关键指针）`，随执行 commit 更新，第一恢复点）、`验收.md`（逐 Epic 可观察完成标准 + 证据等级目标 / 现值）。
- **`[tracking]` Issue**：只留「给产品负责人」段 + 瘦指针；动态事实只在评论流（收口评论、交接评论、裁定留痕）。
- **证据等级**：产品负责人全局 1–7（1 已分析 / 2 已改代码 / 3 本地测试通过 / 4 CI 通过 / 5 已部署 / 6 真实旅程验证 / 7 回源确认）；仓库内 L0–L6 与之的对照表在 `docs/技术设计/验证与门禁.md`。禁止用低一级证据宣称高一级完成。
- **交付终点**（`METHOD.md` §3.2）：PR 合并、组件存在、CI 通过都不自动升级实际终点；合入 main、发布镜像、运行时装配、部署、用户收到结果是不同结论，逐项声明。

---

## 四、目录导览

| 路径 | 是什么 | 何时读 / 能改什么 |
| --- | --- | --- |
| `METHOD.md` | 方法正文 v16（源 lingxi #147） | 规划新 Trace 时读；**本仓不单独修订**，只随源 Issue 版本升级同步 |
| `plugin/README.md` | 五个 skill 何时用、怎么装、换什么、出处表 | 用插件前 |
| `plugin/skills/*/SKILL.md` | 各 skill 正文 | 改 skill 行为时；每文件头带出处 |
| `plugin/templates/` | `合同.md` / `任务表.md` / `验收.md` / `派发卡.md` / `tracking-issue.md` 空白模板 | skill 通过 `${CLAUDE_PLUGIN_ROOT}/templates/` 读取 |
| `template/README.md` | 骨架的「是什么 / 怎么用 / 换什么」表 | init 后即新仓库根 README |
| `template/AGENTS.md`、`CLAUDE.md` | 代理工作约定：按需读取路由表 + 工作底线 + Code Review Rules | 每次任务开头 |
| `template/docs/` | `README.md`（内容归属表）、`产品合同.md`、`当前能力.md`、`协作约定.md`、`协作/执行方法.md`（方法入口，pin 套件版本）、`决策记录/`、`参考证据/`、`技术设计/验证与门禁.md`、`技术设计/验收矩阵.md`、`traces/README.md` | 按 `AGENTS.md` 路由表按需读 |
| `template/.github/` | `Story Fast` / `Epic Full` / `Main Publish` / `Docs` 四份工作流；Issue 模板四份（change 含 `TO PM`、decision、research、bug）；PR 模板 | 建 Issue / PR 时；改 CI 时 |
| `template/scripts/ci/` | 分级器与通用检查：链接、验收矩阵三态与覆盖清单、单行棘轮、体量预算、归属核对、源码棘轮、候选证明、部署契约、compose 结构、`verify_docs.sh` / `verify_repository.sh` | 门禁红了看对应脚本头注释（都写了「挡什么」） |
| `template/scripts/dev/check.sh` | 本机三层 `docs` / `fast` / `full`，版本与 extras 现读自工作流 | 每次提交前 |
| `template/deploy/` | compose（常驻 `app` + job `migrate`）、stage / prod 覆盖、`.env.example`、README、生产 runbook、验收前配置清单、监控告警、systemd 单元 | 有部署面时 |
| `template/src/app/`、`tests/` | 可运行的最小进程（常驻 / healthcheck / migrate）与 79 条测试 | 换成你的服务后保留测试形状 |
| `examples/lingxi/README.md` | lingxi 特有实现清单、一个项目的实际取值、三件套真实样本、方法沿革 | 不知道某处「怎么填」时 |
| `scripts/kit/`、`init.sh`、`.github/workflows/kit-selfcheck.yml` | 套件自检与安装脚本 | 改套件时（见第七节） |
| `docs/traces/1-trace-kit-v0.1.0/` | 本套件自己的 Trace 三件套 + 自回灌报告（dogfood） | 想看一个完整 Trace 长什么样 |
| `.claude-plugin/marketplace.json` | 让本仓可作为 Claude Code 插件市场 | 改插件版本时同步 `plugin/.claude-plugin/plugin.json` |

---

## 五、本机门禁与 CI（新项目里）

- **本机**：`scripts/dev/check.sh`（无参数按改动自动分层；`docs` / `fast` / `full` 可强制；`--print-mode` 只看分层结论；`--reuse-venv` 跳过默认重建）。`docs` = 只跑 `verify_docs.sh`；`fast` = 干净虚拟环境跑 `verify_repository.sh`；`full` = 按 `ci.yml` gate 作业配方重建后跑同一套。骨架没有数据库，「这里加你的真库容器配方」在脚本内标出。
- **CI 三层**（required check 名字固定）：`Story Fast`（PR → `epic/**`：纯文档只跑文档门禁，代码跑无真库快检，高风险路径自动升级完整门禁）；`Epic Full`（PR → `main`：完整门禁 + 镜像构建 + 输出候选证明）；`Main Publish`（合入 main 后回读候选证明，树一致才构建并发布不可变 tag `YYYYMMDD-<sha12>`）；`Docs`（纯文档合入 main 的轻回读）。
- **分级器**：`scripts/ci/classify_story_changes.py` 按路径路由 docs / fast / full，**未知路径一律 full**（新增目录不会静默绕过）。
- **频率纪律**：本机 `docs` / `fast` 每次提交；本机 `full` 每批收口前一次；`Epic Full` 只在冻结候选与合 main 前；真实链路只在验收窗口。批次收口评论报告「完整门禁次数 / 合入 commit 数」。
- **冻结候选显式构建镜像**：见 `deploy/README.md`「编排者冻结前显式触发镜像构建」（`Image-Candidate: true` trailer）。

---

## 六、部署骨架怎么用

`deploy/README.md` 起步：两服务示例（`app` 常驻带 healthcheck 与资源限制、`migrate` 一次性作业不配 restart），镜像引用 `${APP_IMAGE_REGISTRY:?}/app:${APP_IMAGE_TAG:?}${APP_IMAGE_DIGEST:-}`（不可变 tag + 可选 digest 固定），凭据按服务分 `.env.*` 文件且不入库，stage / prod 覆盖文件**结构相同只有配置不同**（`verify_compose_structure.sh` 渲染后比对；`check_deploy_contract.py` 文本级契约）。生产步骤看 `生产部署runbook.md`（digest 固定、单实例、首发不灰度、回滚判据、观察期）；上线前看 `验收前部署配置清单.md`（闸清单 + 五层自检法）；告警看 `监控告警.md`（`scripts/ops/host_health_alert.py` 只有 `send_alert()` 一个扩展点）。

---

## 七、修改本套件（给以后的代理）

用套件自己的方法改套件：开 `[tracking]` Issue，三件套放 `docs/traces/`，PR 留痕，收口评论。硬规则：

1. **准入门槛**：只收验证 ≥2 次且有出处链接（lingxi 或采用本套件的项目的 Issue / 复盘 / 事故）的资产；没有出处的不进。**一次实证只进本仓**（本仓自用，先攒第二次），**两次实证才进 `template/` 与 `plugin/`**。文件头一行 `出处：<链接>；验证：<口径>`，`CHANGELOG.md` 逐条登记。
2. **分档**：G1 通用直接搬；G2 通用模式参数化——去产品名词，扩展点只写一句「这里换成你的 ×××」，**不写抽象层、不写配置 DSL**；G3 项目特有只进 `examples/`。宁少勿多。
3. **禁词**：`template/` 与 `plugin/` 不得出现 lingxi 产品名词（只允许「出处」行里的 lingxi 链接与 `examples/lingxi/` 路径引用）；全仓不得出现本机路径、主机名、用户名、凭据形态。`scripts/kit/check_no_lingxi.sh` 兜底，CI 必跑。
4. **日落条款**：采用本套件的项目在一个 Trace 里一次都没用到的机制，列为下一版删除候选；修订默认净减法，新增须同时提名删除候选。
5. **`METHOD.md` 不在本仓修订**：只随 lingxi #147 的版本升级原样同步（版本头写清源版本与搬运时间），`diff` 必须零差异。
6. **改 `template/` 后必跑**：`scripts/kit/smoke.sh --strict <临时目录>`（把套件当模板起空项目 → `init.sh` → 全部本机门禁）、`scripts/kit/check_no_lingxi.sh`、`python3 scripts/kit/check_links.py`、`claude plugin validate --strict plugin` 与 `claude plugin validate --strict .`；`kit-selfcheck` 工作流在每次 PR 上跑前三项。
7. **版本**：SemVer；发布打 `v<版本>` tag，同步 `plugin/.claude-plugin/plugin.json` 与 `.claude-plugin/marketplace.json` 的版本号，CHANGELOG 按发布批次维护并写明证据等级与未验证层级。
8. **自回灌**：`scripts/kit/refill_diff.sh <lingxi 仓路径> [提交]` 生成 template ⟷ lingxi 的 diff 报告，lingxi 侧差异行必须是 G3 或改写；关键词分类只是导航，结论要人工复核（报告样本见 `docs/traces/1-trace-kit-v0.1.0/`）。

---

## 八、已知边界与未验证

- `template/.github/workflows/*` 从未在真实 GitHub Actions 上运行过（本仓 `kit-selfcheck` 只验证脚本、YAML 可解析与本机同构），`Main Publish` 的 GHCR 推送同样未真跑——留给第一个真实试穿项目，跑通后回写 CHANGELOG。
- 仓库「Template repository」开关由产品负责人在 Settings 勾选（机器人身份无仓库管理权限）；未勾选时用第一节的 `git clone` 兜底法。
- 下版候选：派发卡「门禁命令退出码显式捕获、禁止管道收尾」条款（本机两次实证但 lingxi 无留痕，按准入门槛未带入）；`refill_diff.sh` 去弱关键词重跑。

## 九、常见坑

- `init.sh` 要求工作树洁净：先提交再跑；它会删掉 `plugin/`、`examples/`、`METHOD.md`、本 README 等套件文件并自删，这是设计。
- `gh repo create --template` 必须带 `--public` / `--private`，否则非交互报错。
- 机器上 `python3 -m venv` 没带 pip 时，`check.sh` 自动退回 `uv venv` + `uv pip`；两者都没有会响亮失败，不会假绿。
- 链接检查会扫**所有** `.md` 里的相对链接，示例里的占位链接（方括号文字紧跟圆括号目标的写法）也会被当成真实链接判断链；占位用 `______`，不要写成链接语法。
- 归属核对会扫「合同要求」「产品合同明令」这类短语：要么登记到 `check_contract_attribution.py` 的登记表，要么换措辞。
- 并行子代理共用一个 scratchpad 会互相覆盖同名临时文件；派发卡固定要求各用私有子目录。

## 十、出处

方法与全部资产来自公开仓库 [Moshuiwang/lingxi](https://github.com/Moshuiwang/lingxi)（方法正文 [Issue #147](https://github.com/Moshuiwang/lingxi/issues/147)）；分级清单与逐项出处见 [Trace #1](https://github.com/Moshuiwang/trace-kit/issues/1) 与 `CHANGELOG.md`。
