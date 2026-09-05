# 夹具 complex-f4

复杂链故障 4：合同 PR 由发起人自合且零批准，且合同步骤没有指针 → 根节点（块 A）自述未证黄 ＋ 头部存疑行。

逐项人工核对（断言原文由 run_fixtures.py 直接比对，expected 被重生成也不会连带变绿）：

| 项 | 期望（expected 中必须出现的原文） | 视图 | 人工核对结论 |
| --- | --- | --- | --- |
| 根节点黄 | `块 A 合同 · 自述未证` | simple | 已逐项人工核对，与接口约定一致 |
| 存疑行含合同 PR 自合零批准 | `存疑      自述未证 1实（S-0） · 合同 PR #20 自合 / 零批准` | simple | 已逐项人工核对，与接口约定一致 |
| 合同 PR 判定写进证据链 | `合同 PR #20 | 存疑 |` | why | 已逐项人工核对，与接口约定一致 |

重生成：`python3 -B tests/board/make_fixtures.py --expected`（`trace1-replay` 的快照来自 `board.py --record`，只重画 expected）。
