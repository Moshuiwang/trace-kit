# 夹具 stage-merged

五级阶段第一刻：批次 PR 已合入主干、尚未发布。

逐项人工核对（断言原文由 run_fixtures.py 直接比对，expected 被重生成也不会连带变绿）：

| 项 | 期望（expected 中必须出现的原文） | 视图 | 人工核对结论 |
| --- | --- | --- | --- |
| 阶段＝已合入主干 | `阶段      已合入主干 · 2/2实 勾选` | simple | 已逐项人工核对，与接口约定一致 |
| 五级阶段 | `五级阶段  合入主干 是 · 已发布 否 · 预发已升级 未配置 · 已上生产 未配置 · 收口 否` | simple | 已逐项人工核对，与接口约定一致 |

重生成：`python3 -B tests/board/make_fixtures.py --expected`（`trace1-replay` 的快照来自 `board.py --record`，只重画 expected）。
