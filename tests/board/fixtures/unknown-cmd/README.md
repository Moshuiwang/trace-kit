# 夹具 unknown-cmd

证据源配置声明的 `config.production` 命令超时：该级阶段显示「未知」并进头部阻塞，其余四级照常判定（不沿用旧结论）；证据链只写键与失败类别，不带 stderr。

逐项人工核对（断言原文由 run_fixtures.py 直接比对，expected 被重生成也不会连带变绿）：

| 项 | 期望（expected 中必须出现的原文） | 视图 | 人工核对结论 |
| --- | --- | --- | --- |
| 该级阶段未知 | `五级阶段  合入主干 是 · 已发布 是 · 预发已升级 是 · 已上生产 未知 · 收口 否` | simple | 已逐项人工核对，与接口约定一致 |
| 阶段未知进阻塞 | `阻塞      阶段未知：已上生产` | simple | 已逐项人工核对，与接口约定一致 |
| 失败类别写进证据链（A-1：只写键与类别） | `阶段·已上生产 | 未知 | image_tag | config.production | config.production：超时` | why | 已逐项人工核对，与接口约定一致 |
| 上一级仍按自身证据判定 | `阶段·预发已升级 | 是 |` | why | 已逐项人工核对，与接口约定一致 |

重生成：`python3 -B tests/board/make_fixtures.py --expected`（`trace1-replay` 的快照来自 `board.py --record`，只重画 expected）。
