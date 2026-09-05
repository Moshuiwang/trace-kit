# 夹具 stage-two-prs

热修 H-1：同一批次分支上两个 PR（#31 已 MERGED ＋ #32 OPEN 的 docs 收口）→ 批次 PR 取 #31，合入主干「是」，存疑记「另有 PR #32 开放」；尚未发布时预发 / 生产按 N-1 显示「未配置」（本例未配置）。

逐项人工核对（断言原文由 run_fixtures.py 直接比对，expected 被重生成也不会连带变绿）：

| 项 | 期望（expected 中必须出现的原文） | 视图 | 人工核对结论 |
| --- | --- | --- | --- |
| 合入主干按唯一 MERGED 的 PR 判定（规则①） | `五级阶段  合入主干 是 · 已发布 否 · 预发已升级 未配置 · 已上生产 未配置 · 收口 否` | simple | 已逐项人工核对，与接口约定一致 |
| 存疑记另有 PR 开放 | `另有 PR #32 开放` | simple | 已逐项人工核对，与接口约定一致 |
| Why 写明批次 PR 与规则 | `批次 PR #31 MERGED → 合并提交 f1f1f1f；规则①：恰一个 MERGED 到 base；另有 #32 开放` | why | 已逐项人工核对，与接口约定一致 |

重生成：`python3 -B tests/board/make_fixtures.py --expected`（`trace1-replay` 的快照来自 `board.py --record`，只重画 expected）。
