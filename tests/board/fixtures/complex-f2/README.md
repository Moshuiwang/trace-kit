# 夹具 complex-f2

复杂链故障 2：S-A2 已勾选但只有 worktree 记录、无 commit / PR / 评论 → 自述未证黄。

逐项人工核对（断言原文由 run_fixtures.py 直接比对，expected 被重生成也不会连带变绿）：

| 项 | 期望（expected 中必须出现的原文） | 视图 | 人工核对结论 |
| --- | --- | --- | --- |
| S-A2 自述未证黄 | `存疑      自述未证 1实（S-A2）` | simple | 已逐项人工核对，与接口约定一致 |
| 模块聚合为自述未证 | `Wave 1 实施 · 自述未证` | simple | 已逐项人工核对，与接口约定一致 |
| 无阻塞 | `阻塞      无` | simple | 已逐项人工核对，与接口约定一致 |

重生成：`python3 -B tests/board/make_fixtures.py --expected`（`trace1-replay` 的快照来自 `board.py --record`，只重画 expected）。
