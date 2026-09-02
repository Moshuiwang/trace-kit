# trace-kit

把 lingxi 两个月（2026-07-24 → 09-02，17 个 Execution Trace、约 300 个合并 PR）实证有效的「工作方法资产」打包成可复用套件：方法正文、Claude Code 插件、新项目骨架、真实项目示例。

## 安装两步

前提：本仓库已开启 GitHub「Template repository」开关（Settings → General）；未开启时第一步改为：`git clone` 本仓 → 删掉 `.git` → `git init && git add -A && git commit -m init` → 再 `./init.sh`（脚本要求工作树洁净，实测未提交直接跑会被拒）。

```bash
# 1. 用套件做模板新建仓库，再把骨架提升到根目录
gh repo create <你的仓库> --public --template Moshuiwang/trace-kit --clone && cd <你的仓库> && ./init.sh

# 2. 安装 Claude Code 插件（kickoff / takeover / handoff / guardian / dispatch-card）
claude plugin marketplace add Moshuiwang/trace-kit && claude plugin install trace-kit@trace-kit
```

之后按 `template/README.md`（init 后即仓库根 `README.md`）的「换什么」清单替换项目名 `app` 与产品文档；本机跑 `scripts/dev/check.sh` 得到与 CI 同构的结论。

## 自验证

- `scripts/kit/smoke.sh`：在临时目录把套件当模板起一个空项目，跑 `init.sh` 与全部本机门禁（本仓 CI `kit-selfcheck` 每次 PR 执行）。
- `scripts/kit/refill_diff.sh <lingxi 仓路径>`：自回灌——template 与 lingxi 对应文件逐对 diff，lingxi 侧差异行必须是 G3 或改写（报告见 `docs/traces/1-trace-kit-v0.1.0/自回灌报告.md`）。
- `scripts/kit/check_no_lingxi.sh`：`template/` 与 `plugin/` 禁词扫描，外加全仓本机路径 / 主机名 / 凭据形态扫描。

## 版本与证据

当前 `v0.1.0`（`0.x` = 尚未稳定）。每个资产的出处链接、验证口径与**未验证层级**在 `CHANGELOG.md` 逐条列出；`template/.github/workflows/*` 尚未在真实 GitHub Actions 上运行过（本仓 `kit-selfcheck` 只验证脚本与 YAML 可解析）；插件远端安装已验证（`claude plugin marketplace add Moshuiwang/trace-kit` → `claude plugin install trace-kit@trace-kit`，2026-09-02）。

## 目录

| 目录 / 文件 | 是什么 | 怎么用 |
| --- | --- | --- |
| `METHOD.md` | 执行方法正文（= lingxi #147 v16 原样，带版本头） | 规划者读它生成 `[tracking]` Trace；编排者只执行获批 Trace |
| `plugin/` | Claude Code 插件：五个 skill + 三件套与派发卡模板 | 见 `plugin/README.md` |
| `template/` | 新项目骨架：AGENTS.md、docs 五件、分层 CI 与风险分级器、通用检查、本机=CI 同构的 `check.sh`、deploy 骨架 | `init.sh` 之后按 `template/README.md`「换什么」清单替换 |
| `examples/lingxi/` | G3 档：lingxi 特有实现只作示例 | 对照骨架看一个真实项目怎么填 |
| `scripts/kit/` | 套件自检：禁词扫描、链接检查、空项目冒烟、自回灌 diff | `scripts/kit/smoke.sh` |
| `docs/traces/` | 本套件自己的 Execution Trace 三件套（dogfood） | — |

## 分档口径

- **G1** 通用，直接搬。
- **G2** 通用模式，参数化：去 lingxi 名词，扩展点只写一句「这里换成你的」；不写抽象层、不写配置 DSL。
- **G3** lingxi 特有，只进 `examples/lingxi/`。

只打包验证 ≥2 次且有出处的资产；出处与验证口径在 `CHANGELOG.md` 逐条列出。
