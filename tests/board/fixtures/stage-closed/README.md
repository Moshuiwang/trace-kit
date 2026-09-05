# 夹具 stage-closed

五级阶段第三刻：Trace Issue 关闭 → 阶段「已收口」、下一步「无（Trace 已关闭）」。

逐项人工核对（断言原文由 run_fixtures.py 直接比对，expected 被重生成也不会连带变绿）：

| 项 | 期望（expected 中必须出现的原文） | 视图 | 人工核对结论 |
| --- | --- | --- | --- |
| 阶段＝已收口 | `阶段      已收口（Issue 关闭 13:50）· 2/2实 勾选` | simple | 已逐项人工核对，与接口约定一致 |
| 下一步＝无 | `下一步    无（Trace 已关闭）` | simple | 已逐项人工核对，与接口约定一致 |
| 五级阶段全是 | `收口 是` | simple | 已逐项人工核对，与接口约定一致 |

重生成：`python3 -B tests/board/make_fixtures.py --expected`（`trace1-replay` 的快照来自 `board.py --record`，只重画 expected）。
