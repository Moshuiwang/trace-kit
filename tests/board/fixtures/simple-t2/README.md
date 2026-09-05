# 夹具 simple-t2

T2：S-2 被勾选但始终没有 commit / PR / 评论 → 自述未证黄，头部存疑「自述未证 1」，整体阶段仍是「执行中」不判完成。

逐项人工核对（断言原文由 run_fixtures.py 直接比对，expected 被重生成也不会连带变绿）：

| 项 | 期望（expected 中必须出现的原文） | 视图 | 人工核对结论 |
| --- | --- | --- | --- |
| S-2 勾了零 commit → 黄 | `Wave 2 实施 · 自述未证` | simple | 已逐项人工核对，与接口约定一致 |
| 头部自述未证 1 | `存疑      自述未证 1实（S-2）` | simple | 已逐项人工核对，与接口约定一致 |
| 整体不判完成 | `阶段      执行中 · Wave 3 审核（3/4实 勾选）` | simple | 已逐项人工核对，与接口约定一致 |
| 五级阶段未合入主干 | `合入主干 否` | simple | 已逐项人工核对，与接口约定一致 |

重生成：`python3 -B tests/board/make_fixtures.py --expected`（`trace1-replay` 的快照来自 `board.py --record`，只重画 expected）。
