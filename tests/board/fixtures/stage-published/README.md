# 夹具 stage-published

五级阶段第二刻：发布工作流 run success ＋ gh.tags 出 tag，预发 / 生产命令取到同一 tag → 阶段「已上生产」、下一步「观察与收口」（推断链的「已完成」表达）。

逐项人工核对（断言原文由 run_fixtures.py 直接比对，expected 被重生成也不会连带变绿）：

| 项 | 期望（expected 中必须出现的原文） | 视图 | 人工核对结论 |
| --- | --- | --- | --- |
| 阶段＝已上生产 | `阶段      已上生产 · 2/2实 勾选` | simple | 已逐项人工核对，与接口约定一致 |
| 下一步＝观察与收口（已完成表达） | `下一步    观察与收口` | simple | 已逐项人工核对，与接口约定一致 |
| 五级阶段 | `五级阶段  合入主干 是 · 已发布 是 · 预发已升级 是 · 已上生产 是 · 收口 否` | simple | 已逐项人工核对，与接口约定一致 |
| 发布 run ＋ tag 双证据 | `发布 run success` | why | 已逐项人工核对，与接口约定一致 |
| 预算条有上限画条 | `完整门禁 ▰▰▰▰▱▱ 3实/5` | simple | 已逐项人工核对，与接口约定一致 |

重生成：`python3 -B tests/board/make_fixtures.py --expected`（`trace1-replay` 的快照来自 `board.py --record`，只重画 expected）。
