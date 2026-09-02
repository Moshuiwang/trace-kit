---
name: kickoff
description: 开新 Execution Trace 时起草六段式开工合同与三件套（合同 / 任务表 / 验收）并生成 [tracking] Issue 瘦指针。在规划新 [tracking] Trace、或产品负责人说「开工 / 立项 / 下一个 Trace」时使用。
---

> 出处：lingxi https://github.com/Moshuiwang/lingxi/issues/330（复盘 P0）；验证：#358 / #373 / #418 / #445 / #469 / #502 / #521 七个 Trace 的合同均按此起草为六段式

# 六段式开工合同起草

你现在是规划者，为一个新的 Execution Trace 起草开工合同与三件套。方法正文是项目 pin 的 `METHOD.md`（规划者使用法见 §一，合同区字段见 §八）。

## 步骤

1. 读模板：`${CLAUDE_PLUGIN_ROOT}/templates/合同.md`（六段结构与每段的既定条款）、`${CLAUDE_PLUGIN_ROOT}/templates/任务表.md`、`${CLAUDE_PLUGIN_ROOT}/templates/验收.md`、`${CLAUDE_PLUGIN_ROOT}/templates/tracking-issue.md`。模板头部的出处注释与「用法」段不进产出物。
2. 从当前对话与相关 Issue 收集素材，逐段填实——**每段都不允许留空**：
   - 空不出来的段（如成本预算）按项目既有先例给出建议值并标注「建议值，批准时可改」；
   - 授权终点只写产品负责人**已经说过**的授权；没说过的写进「显式除外」。
3. 产出物：三件套（合同.md / 任务表.md / 验收.md）落 `docs/traces/<issue号>-<短名>/`，走 PR，**合并即批准**；`[tracking]` Issue 正文只留「给产品负责人」段与瘦指针（按 `tracking-issue.md`；`METHOD.md` §二、§八）。
4. 合同末尾附「批准时需一并裁定」编号清单（把所有开放决策点收拢成可单字回复的编号项，每项带默认值）。
5. **合同未获产品负责人批准前，不派发任何实施工作。**

## 底线

- 未写进合同的授权不存在；执行中不得自行扩权。
- 成本段必须含：完整门禁次数上限与时间窗、模型配比、外部审查配额。模型配比项目自定，写进合同 §5（一个真实项目的取值见套件 `examples/lingxi/`）。
- 合同只认产品负责人裁定与卡面完成标准；上一任执行者自设的约束不继承。证据只认 GitHub / 仓库留痕。
- 主线声明必须能回答「任何新发现是否立项」的默认答案（默认登记不立项，`METHOD.md` §6.2）。
