# Changelog

> 出处：lingxi [CHANGELOG.md](https://github.com/Moshuiwang/lingxi/blob/caa845d77fbd2d6381de304dc6047498aa84c782/CHANGELOG.md) 头部约定、[deploy/README.md「版本号规则」](https://github.com/Moshuiwang/lingxi/blob/caa845d77fbd2d6381de304dc6047498aa84c782/deploy/README.md) 与 [Issue #417](https://github.com/Moshuiwang/lingxi/issues/417)；验证：2.0.0 一次实发 + rc21–rc23 三批合并条目；分档 G2（约定与版本号规则，条目留空）。

本文件记录 <项目名> 对用户可见与外部边界有影响的变化，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 约定；版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。版本规则、发布 tag 与镜像 tag 的关系见下文[「版本号规则」](#版本号规则)。

条目按发布批次维护，不逐 PR 记录；每条引用对应 Issue 便于追溯。当前能力的完整事实、证据层级与已知边界以 [docs/当前能力.md](docs/当前能力.md) 为准，本文件不重复其细节。

## [Unreleased]

### Added

- 这里换成你的：一条用户可见变化 + 对应 Issue 号。

## 版本号规则

- **规则**：[SemVer 2.0.0](https://semver.org/lang/zh-CN/)（`主.次.补丁`）。破坏用户承诺或外部边界升主版本，新增能力升次版本，修复升补丁版本。起始版本这里换成你的（无历史版本号的项目首版可直接定 `1.0.0`）。
- **粒度**：整仓单一版本，不分服务。全部服务镜像永远同一 commit 同批构建、同批部署（单实例纪律、整体切换回滚），分服务版本只会制造组合矩阵而无独立发布收益；服务级追溯由镜像 tag 的 `日期-sha` 承担。
- **载体**：版本号的唯一事实源这里换成你的（例如 `pyproject.toml` 的 `[project] version` 或 `package.json` 的 `version`）。发布时打 git tag `v<版本号>`（例：`v1.0.0`），不可变；与其他用途的 git tag（如验收标签）不混用。
- **镜像 tag**：`<仓库前缀>/<app>:<YYYYMMDD>-<commit sha 前 12 位>`，由 `Main Publish` 在合入 `main` 后发布。日期段标识发布批次，sha 段标识源码提交；带 sha 才是不可变的，**禁止 `latest` 或分支名**。版本号与镜像的对应关系由 `v<版本号>` tag 指向的提交承载——该提交 sha 的前 12 位就是这一版镜像 tag 的 sha 段，不重造镜像命名。
- **升版时机**：随发布批次由发布 PR 统一升版并打 tag，不逐 PR 升版，避免版本噪音。
- **CHANGELOG**：按 Keep a Changelog 约定随发布批次维护，条目引用 Issue / PR；镜像 tag 语义与发布链路的完整说明见 `deploy/README.md`。
