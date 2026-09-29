# Changelog

本文件记录 trace-kit 套件的变化，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)；版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)（`0.x` = 尚未稳定，字段与目录可能变）。**每个资产条目都带出处**（形成它的采用项目 Issue / 复盘 / 事故链接）与验证口径；没有出处的资产不进套件。

## v0.8.0 — 2026-09-30

**方法 v25：方法正文从 lingxi 独立，由本仓持有**（产品负责人 2026-09-29「从 lingxi 中独立出来」，同日批准迁移方案全部推荐项）。以后改方法 = 在本仓提 PR，产品负责人以代码所有者审批合并即发布；不再「先改 lingxi #678、再逐字抄进本仓」——手工同步已漂移 ≥ 3 次（v21 从未同步、骨架入口停在 v22、`marketplace.json` 在 v0.4.0 漏升）。版本号照旧往下数（方法 v25 = 套件 v0.8.0，两套号并存）。证据等级：本机 `kit-selfcheck` 全项（项目中立守卫 / 版本一致性 / 链接 / 脚本语法与 ShellCheck / 行尾空白 / 看板单测与夹具 / 空项目冒烟）与 `claude plugin validate --strict` 绿，CI 见 PR；**未验证**：两条新规则与新修订流程尚未在下一个 Trace 实跑；私有名词检查只在本机跑（CI 无词表，输出明示「未加载」）；代码所有者审批对 `METHOD.md` 的技术强制要到本版合并后的下一个方法 PR 才生效（GitHub 按基准分支的 CODEOWNERS 判定）。

- `METHOD.md` → 方法 **v25**：文件头与版本头改为「唯一源、修订走本仓 PR」；§三 额度停派线改为「平时 98% 停派；重置前 3 小时内可到接近 100%，只派不中断、无需交接的工作」；§五 换人条件改为「上下文 > 60% 且当前工作单元已收口，两条同时满足才换」（工作单元 = 一个 Step 从派发到合并，含审核与修复，且手上没有在跑的子代理），接力点随之改为「工作单元收口点或失联判定」，复盘规则的时机同步拆开（每个批次收口写收口与复盘评论，换人时再接交接评论与释放租约；批中换人时收口评论写该工作单元的结果与在途）；落点改为只把「方法正文 / trace-kit 程序」两类候选归档到本仓修订 Issue、公开仓库只写方法层面结论，项目工作项与本机事实留原处；§七 方法行改指 trace-kit；§八 修订 Issue 建在本仓、已存在则复用、正文走 PR（修订 Issue 不再收「草案」，草案即 PR）；末行不再指向 lingxi 自己的验证与门禁。v24 及更早条目与 lingxi 出处链接原样保留（历史证据）。两条规则均为产品负责人 2026-09-29 裁定 — 出处 https://github.com/Moshuiwang/lingxi/issues/912#issuecomment-5895404261 。其余 lingxi #912 候选（方法正文 8 条、工具 8 条 + 1 条守卫改进）迁到 v26 修订 Issue https://github.com/Moshuiwang/trace-kit/issues/31 ；v24 新增条款的删除侧复核交给 v26（v24 下只实跑 1 批）。
- 插件同步两条新规则与修订 Issue 位置：kickoff（额度线、修订 Issue 在本仓查、有则复用）、guardian（换人条件两处）、takeover、handoff（触发描述、归档落点与公开仓库纪律）、合同模板（额度线、换人、修订 Issue 行）、tracking-issue 模板、插件 README；kickoff / takeover / handoff / guardian / 合同与派发卡模板里「`METHOD.md` v22 / v24 §…」过期版本标签统一改为 v25（节号逐一核对仍对应）；出处行里「现 / 现行 lingxi #678 v22」改为「迁移前在 …」（链接保留）；guardian 归档口径与 handoff 对齐（只归档两类、公开仓库纪律）。
- 新项目骨架 `template/docs/协作/执行方法.md`：入口从 trace-kit v0.3.0 / 方法 v22 改为 v0.8.0 / v25。
- `init.sh`：版本号解析兼容 v0.4.0 起的 `## vX.Y.Z — 日期` 标题（此前用 v0.7.0 新建项目会显示 0.3.0）。
- 守卫：`check_no_lingxi.sh` 改名 `check_project_neutral.sh`（项目中立守卫），扫描范围加 `METHOD.md`，出处链接放行扩到两个采用项目；**私有采用项目的名词表不进公开仓库**，从本机不入库文件读取（`TRACE_KIT_PRIVATE_TERMS_FILE`，缺省 `~/.config/trace-kit/private-terms.txt`；读不到只跑公开表并在输出里明示），命中范围为全仓含未跟踪文件与 `examples/`、不区分大小写、先剥掉采用项目 GitHub 链接再匹配（出处链接可留，链接旁正文不放行），词表正则无效时拒绝判绿且不回显词表；既有命中 1 处暂列豁免（`docs/traces/1-trace-kit-v0.1.0/自回灌报告-附录.txt`，是否清理公开仓库既有内容待产品负责人决定）；机器事实扫描加 `--untracked`；不在 git 仓库里运行时拒绝判绿（此前 `git grep` 失败被吞、会假绿）。
- 新增 `scripts/kit/check_versions.py`（挂进 `kit-selfcheck`）：方法版本五处（标题 / 版本头 / 状态行 / 版本史最新条目 / 骨架方法入口）一致、套件版本三处（`plugin.json` / `marketplace.json` / CHANGELOG 最新标题）一致、版本头引用的套件版本在 CHANGELOG 有条目；取代「与 #678 零差异」手工步骤。
- `.github/CODEOWNERS` 加 `/METHOD.md` 与 `/.github/CODEOWNERS`（现有 main 规则集要求代码所有者审批）。
- README：套件四件表、版本行、目录导览、第八节规则 3（项目中立）与规则 5（`METHOD.md` 是唯一源、在本仓修订）、第十一节出处。
- 体量：`plugin/skills` + `plugin/templates` 77,855 → 78,917 字节（+1.4%），理由 = 两条已裁定规则的同步、修订 Issue 位置与归档口径说明；`template/` +93 字节（入口版本）。
- 版本 0.7.0 → 0.8.0。

## v0.7.0 — 2026-09-29

两部分：① 另一项目（startimes-bi/dvb-sales-reporting）Trace #18（2026-09-21 → 09-29，9 任编排者、19 个版本、生产 20 家自动送达）复盘里**跨批次重复出现且已验证**的程序性条款；② 产品负责人 2026-09-29 点名的四项（角色与配置表、时间校准与预估、资源登记与自动清理、复盘「外部路径检查」），点名可先净增。只出现一次的、以及属于方法正文的候选留在该 Trace 复盘总结与 lingxi 修订 Issue [#912](https://github.com/Moshuiwang/lingxi/issues/912)。经两轮外部审查（Codex，只读）后已按意见收窄与补齐（第 2 轮：自动清理与 §2 删除授权对齐、资源登记表允许编排者维护、清理判据按对象类型分列、复盘第 7 项注明为套件增补）：撤回「额度重置前不留余量」（与 `METHOD.md` 2% 停派线冲突，待产品负责人定）、外部写执行者改为「按合同 §2 通路」、撤回「门禁与全量测试禁后台」（已由六条款第 3 条覆盖且与「实施卡不跑完整门禁」口径不一）、撤回未验证的「备份还原」做法。产品负责人 2026-09-29 另裁定：派发卡条款正文只留模板一处（skill 改为引用，体量压回）。同日另两项裁定——额度停派线「平时 98%，重置前 3 小时内可到接近 100%，只做不会中途断掉、无需交接的工作」、换人默认条件「上下文 > 60% 且当前工作单元已收口」——属方法正文，**本版 skill / 模板仍与现行 `METHOD.md` v24 一致（2% 停派、收口点 ≥ 50% 换人），待方法正文下一版同步**；候选已补档 lingxi #912 https://github.com/Moshuiwang/lingxi/issues/912#issuecomment-5895404261 。证据等级：`kit-selfcheck` 本机禁词 / 链接 / 行尾空白 / 看板单测通过；**未验证**：新增条款尚未在下一个 Trace 实跑。版本 0.6.0 → 0.7.0。

- 派发卡模板与 dispatch-card：**等待只认自己**（自己的 PID / 自己写出的产物标记 / 状态变化，三种都带硬超时；禁止按进程名或命令行模式；终态白名单含被拦 / 放弃与超时；被等命令中止时一并结束等待）— 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5779221457 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5806511829 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5816740223 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5844908690 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5888621563 ；超时按上次实测给并写出处 — 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5779997141 ；碰运行路径的卡写调用链（只读核对范围，需改动才能接线的文件列进归属）+ 至少一条经真实入口的用例 — 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5779997141 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5807711659 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5831198642 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5888591772 ；现状 / 前提标来源、摘要表程序生成 — 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5767848282 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5772615408 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5779997141 ；禁 `git checkout --` 之类整文件撤销、只用编辑逐处还原 — 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5807711659 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5816220364 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5855165302 ；真实外部写不在实施卡、按合同 §2 通路执行、单条命令与远端命令落脚本 — 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5770822176 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5807711659 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5831198642 ；「运行中改口径等收口再续派」并入原有「不依赖中途转达」条款 — 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5831198642 。新增「角色配置 / 时间预估 / 资源登记」三个现场字段（产品负责人点名）。
- guardian：判活加「空转等待」巡检（列全部等待 shell，核只认自己与硬超时，> 60 分钟单独标出）— 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5806501672 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5806819794 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5816740223 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5844908690 ；预测按时间校准表的实测单元 + 机器等待分项 — 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5888591772 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5888621563 ；换人条件同步 `METHOD.md` v24「最后一批收口即 Trace 关闭时不换人」，合同另约从合同；复盘项数改七项。
- handoff：复盘第 4 项加「预估 vs 实际」表并回写校准表；新增第 7 项「外部路径检查」（逐版本查自上次复盘以来 Claude Code 的 What's new / changelog、官方文档与博客，标本机未含版本）；新增「自动清理」节（只清资源登记过的、三条件满足才清、逐项回读、风险项请授权、分类器拦批量删除时生成带逐项复核的脚本由产品负责人一条命令执行）；接手 prompt 不写本评论号 — 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5767874675 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5780009339 ；在途工作列出等待循环 / 观察哨 / 定时提醒 — 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5806501672 。
- kickoff：外部系统事实清单 — 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5767848282 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5772615408 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5795284583 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5855165302 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5888591772 ；估时按实测单元与机器等待；填角色与配置表（子代理定义名取实有文件、外审模型写实测通过的正式标识）、时间预估引校准表、合同 §6 写「上次复盘建议采用的官方功能」、任务表保留资源登记。
- 合同模板：§2 新增「收口自动清理授权 □」（只限资源登记过且满足判据的对象；其余删除仍逐项请示）；§5 新增「角色与配置（待批）」表（取代原「外部审查配额」行）与「时间预估」行；§6 新增「上次复盘建议采用的官方功能」、收尾改为按资源登记自动清理 + 预估 vs 实际对账、同步末批不换人；「批准时需一并裁定」首项固定为角色与配置表。
- 任务表模板：S-Z-2 改为自动清理；S-Z-3 加预估 vs 实际；S-Z-4 七项复盘；末尾新增「资源登记」表。验收模板：批终链加「部署前真实数据预演并核指标取值」— 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5807711659 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5816203912 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5831198642 、https://github.com/startimes-bi/dvb-sales-reporting/issues/18#issuecomment-5855165302 。
- 新增 `templates/时间校准.md`（项目级校准表骨架，跨 Trace 累积；首版样本见该 Trace 复盘总结）。
- v0.5.0 删除候选复核：合同 §5「外部审查配额」（本版并入角色与配置表的外部审核者行）、§2「部署预发环境」、派发卡「一次性运维脚本」三项在该 Trace 均被使用 → 保留。
- 体量：`plugin/skills` + `plugin/templates` 合计 69,041 → 约 78,000 字节（约 +13%）；派发卡 skill 的条款正文已并入模板一处（skill 10,081 → 约 7,000 字节），各 skill 的新增出处改为指向本条目；净增主要来自产品负责人点名四项。

## v0.6.0 — 2026-09-29

- `METHOD.md` 同步方法 **v24**（源 lingxi #678，2026-09-29 发布）：结清 v23 删除侧欠账（删 8 并 5，角色 7 → 6），新增守望者独立拉起与压缩 / 日夜规则、PR 自动外审通过才合并、临时授权、生产手工修补当天补登记等；变更表 https://github.com/Moshuiwang/lingxi/issues/857#issuecomment-5881542037 。
- guardian：新增「规划者拉起独立守望者」一节（`--autocompact`、三类规则写死）；拉起姿势改为启动脚本 + `"$(cat 文件)"`、验活看界面状态行 — 出处 https://github.com/Moshuiwang/lingxi/issues/857#issuecomment-5754233068 、https://github.com/Moshuiwang/lingxi/issues/857#issuecomment-5748076981 ；自身被拒的动作不转手 — 出处 https://github.com/Moshuiwang/lingxi/issues/857#issuecomment-5770687973 。
- kickoff：触点预列规则强制批准、自动外审先实查、碰生产主机先读运维记录、合同 §6 写守望者形态 — 出处 https://github.com/Moshuiwang/lingxi/issues/857#issuecomment-5863078436 、https://github.com/Moshuiwang/lingxi/issues/857#issuecomment-5868571693 。
- 版本 0.5.0 → 0.6.0。证据等级：`kit-selfcheck`（见 PR）；**未验证**：守望者独立拉起形态首次在 lingxi 2.6.2 Trace 实跑。

## v0.5.0 — 2026-09-21

另一项目（startimes-bi/dvb-sales-reporting）首个 Trace 用 v0.4.0 跑完三批（9 h、3 路并行、审核 r1–r3 抓出 P0 1 / P1 7）后的程序性候选，守望者归档评论 https://github.com/Moshuiwang/lingxi/issues/857#issuecomment-5761705442；方法正文候选留 lingxi #857（v24），本版不动 `METHOD.md`。证据等级：`kit-selfcheck` 本机四项（禁词 / 链接 / 看板单测 / 插件校验）绿；**未验证**：新增条款尚未在第二个 Trace 上跑过，该项目的下一个 Trace 是第一个绑 v0.5.0 的。

- 派发卡模板与 dispatch-card：同批并行卡各建独立 `tests/support/fake_<模块>.py`（合并交错 55 例红）；命名类值唯一真源 = 登记文件、依赖卡等其首提交；「`gh` 读 Issue 不算联网」口令；验证以退出码判绿不以末行；集成卡正路径必须含真实数据形态行；文档抄源码用 `dataclasses.fields()` 实取；报告固定含「接口冻结需要的字段表」与「自报取舍」— 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/1#issuecomment-5761645157、https://github.com/startimes-bi/dvb-sales-reporting/issues/1#issuecomment-5756158342、https://github.com/startimes-bi/dvb-sales-reporting/issues/1#issuecomment-5757824625。
- dispatch-card 审查派发：审查卡固定结构（威胁模型逐项复攻 + 假证据六型 + 独立变异 ≥ N 半数与实施者不同 + 实施者自报取舍请定级）；修复卡把审核者探针复制进修复者 scratchpad、复核者用改写版再攻 — 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/1#issuecomment-5761645157、https://github.com/startimes-bi/dvb-sales-reporting/issues/1#issuecomment-5756158342。
- guardian：事件型观察哨只留窗口死亡 / 静止 ≥ 15 分钟 / 查询失败三类，去掉「新提交」事件（9 h 值守零误报零漏报）；定时汇报 30 分钟为默认、产品负责人可裁定降到 60 分钟；预测外推基准 = 已完成批次实测墙钟并留痕对账；额度从本机数据源自读；退场前建好下一个 Trace 的输入 Issue 并接入未验证清单 — 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/1#issuecomment-5755770442、https://github.com/startimes-bi/dvb-sales-reporting/issues/1#issuecomment-5755676104、https://github.com/startimes-bi/dvb-sales-reporting/issues/1#issuecomment-5755682445、https://github.com/startimes-bi/dvb-sales-reporting/issues/1#issuecomment-5761712608。
- kickoff：上一 Trace 未验证清单 + 输入 Issue 为首要输入逐条落 Step；整合 Step 独立成卡 + 整合前修复包；真实外部读 / 写 Step 单列授权级别与触点 — 出处 https://github.com/startimes-bi/dvb-sales-reporting/issues/1#issuecomment-5761645157。
- 验收模板头部：判据数值一律由程序写出，不认手填 passed（该项目 `验收.md` 头部条款，三批沿用）。
- 版本 0.4.0 → 0.5.0（`plugin/.claude-plugin/plugin.json`；`.claude-plugin/marketplace.json` 在 v0.4.0 漏升，本版一并对齐）；根 README 版本行补 v0.4.0 / v0.5.0。
- 体量：`plugin/` 净增约 30 行，理由 = 以上每条都在同一 Trace 的 ≥ 2 个批次复用或由事故实证（出处逐条附）。**下一版删除候选**（该 Trace 一次未用 / 未填）：合同模板 §5「外部审查配额与指定位置」、§2「部署预发环境 □」、派发卡「一次性运维脚本（命中才填）」——第二个 Trace 仍未命中则删。

## v0.4.0 — 2026-09-20

- `METHOD.md` 同步方法 v23（源 lingxi #678，2026-09-20 发布）：模板只供 Claude Code 使用（删执行者中立表述与两条外部执行者候选）；新增触点纪律、实施卡不跑完整门禁、批次链估法三条；变更表见 lingxi #842。
- 派发卡模板与 dispatch-card：留痕值由命令输出粘贴、修复包每处各自证红（lingxi #843 复盘）。
- kickoff：时间窗日期与星期由 `date -d` 实取（#843 合同笔误）。
- guardian：定时汇报每 30 分钟一条；观察哨只在变化时输出、无信号时段用长间隔观察哨（#843 w2 复盘）。

## 日落条款

- 每个资产必须可追溯到出处；采用本套件的项目在一个 Trace 里一次都没用到、没填写的机制，列为下一版删除候选（与 `METHOD.md` §八「修订规则」同构；v19 起正文无 §九）。
- 修订默认净减法：新增资产须同时提名删除候选；`template/` 与 `plugin/` 的体量不得超过上一版，除非 CHANGELOG 写明理由。
- `METHOD.md` 是方法唯一源，在本仓修订（v25 起；v18–v24 历史在 lingxi #678，v17 及更早在 #147）：每个方法版本一个修订 Issue（建在本仓，已存在则复用）；改动走 PR，产品负责人以代码所有者审批合并即发布；方法发版 = 套件次版本升级。

## [0.3.0] - 2026-09-18

随 lingxi #678 方法正文 **v22**（2026-09-18 发布，修订 Issue [#840](https://github.com/Moshuiwang/lingxi/issues/840)）的同步版。证据等级：`kit-selfcheck` 本机三项（禁词 / 链接 / 看板单测）绿，CI 待本 PR 回读；**未验证**：v22 新增的里程碑分诊、守望者汇报五项、复盘规则、并行纪律与改后的五个 skill 尚未在真实 Trace 上跑过，下一个 Trace 是第一个绑 v22 的。不动看板引擎、不加 CI 门禁。

### Changed

- `METHOD.md` 同步到 **v22**（源 lingxi #678，2026-09-18 发布；正文逐字搬运，版本头按实读值更新）：新增 §三「里程碑分诊」、§四「守望者汇报固定五项」与「并行纪律」、§五「复盘规则」（含规划者 / 守望者复盘职责）、§八「每个版本一个修订 Issue」；角色表改 4 行；额度停派线 2%、收口点上下文 ≥ 50% 换人、身份 / 数据形态类修法先做真实样本统计、每个入口规划期真机 dry、外审台账记输入载荷、门禁绿与变异红以 Ran N 为准 — 出处 [v22 变更表与 #812 候选归档](https://github.com/Moshuiwang/lingxi/issues/840#issuecomment-5724253737)、[发布记录](https://github.com/Moshuiwang/lingxi/issues/678#issuecomment-5724287367) — 验证：正文区与 #678 读回逐字一致（去末尾空行）；`check_links.py` / `check_no_lingxi.sh` 绿。
- `skills/guardian`：新增「汇报固定五项」（总体进度 / 预计完成时点 / 当前堵点 / 下次需要人类决策的时点 / 可提前给的裁定与收口预批）与「批次收口序列、换人与退场」（核收口评论 → 复盘评论 → 交接评论 → 释放租约；收口点上下文 ≥ 50% 换人；退场前写机制对账复盘并把方法候选归档到修订 Issue）；失联判定补「不因上下文余量拉继任」；有效性判据补第四种结局「观察哨自身被终止」；待裁项一节补「待办与讨论分开置顶、一次一条、先出就绪自检」— 出处 v22 §四 / §五、[#812 守望者排期对账](https://github.com/Moshuiwang/lingxi/issues/812#issuecomment-5714640738)。
- `skills/handoff`：新增「交接前：批次收口序列与复盘评论」（六项复盘内容、顺序不能反、复盘落地才算退场）；描述改为「批次收口序列 / 失联继任」触发，不再写「上下文接近上限」— 出处 v22 §五。
- `skills/takeover`：核实清单 +2（裁定附带动作是否有回执；在途系统链路终态先回读再登记）；接管登记写当任上下文起点 — 出处 [#812 812-w2 复盘](https://github.com/Moshuiwang/lingxi/issues/812#issuecomment-5713420401)。
- `skills/dispatch-card` 与 `templates/派发卡.md`：现场加「并行组 / 文件边界」；附加条款加禁令逐条写死、审核者工作树保留至批次合并、一次性运维脚本四要素、同批并行卡独立 worktree + 并行实施串行整合；审查派发加外审输入载荷、变异验红以 Ran N 为准；编排者侧加多路并行各挂兜底观察 — 出处 v22 §四、[#812 夜班复盘](https://github.com/Moshuiwang/lingxi/issues/812#issuecomment-5703645397)。
- `skills/kickoff` 与 `templates/合同.md` / `任务表.md` / `tracking-issue.md`：步骤 0「里程碑分诊与结清」（四项、反向扫描、分诊表进开工快照、建下一版修订 Issue）；Step 写并行组与文件边界、串行 / 并行两个估时、并行上限；合同 §5 加额度停派线 2%、触点次数与在线时段、并行段；§6 收口序列加复盘评论与 ≥ 50% 换人、「重检查默认串行」改指「并行纪律」；任务表加 S-Z-4 复盘评论与候选归档；tracking Issue 瘦指针加方法版本 / 下一版修订 Issue — 出处 v22 §三 / §四 / §五 / §七。
- 章节引用 v20 → v22：`plugin/README.md` 出处表、根 `README.md`、`template/docs/协作/执行方法.md` 入口（trace-kit v0.3.0 / 方法 v22）。
- 版本 0.2.2 → 0.3.0（`plugin/.claude-plugin/plugin.json` / `.claude-plugin/marketplace.json`）— 验证：`claude plugin validate --strict` 双绿；tag 随合 main 后打。
- `METHOD.md` 同步到 **v20 r1**（源 lingxi #678，2026-09-13；正文逐字搬运，版本头按实读值更新）：产品负责人追加「规划前核本机能力与额度、外审调用须实机测试、外审频率按额度定」条款（第三节预算段 + 第六节 Ready 门），第四节外审一句去掉具体工具名 — 出处 [v20 r1 发布评论](https://github.com/Moshuiwang/lingxi/issues/678#issuecomment-5653777117) — 验证：正文区与取源字节级一致；`check_links.py` 绿。插件版本号不动（`METHOD.md` 不在插件内）。

## [0.2.2] - 2026-09-13

随 lingxi #678 方法正文 **v20**（2026-09-13 发布）的同步版（[PR #23](https://github.com/Moshuiwang/trace-kit/pull/23) + 本发布 PR）。证据等级 4（`kit-selfcheck` 绿：禁词 / 链接 / 看板单测 209 ＋ 夹具 49 / 空项目冒烟）；**未验证**：v20 正文与改后的 `guardian` skill 尚未在真实 Trace 上跑过，lingxi 2.5.0 将是第一个绑 v20 的 Trace。不动引擎行为、不加 CI 门禁。

### Changed

- `METHOD.md` 同步到 **v20**（源 lingxi #678，2026-09-13 发布；正文逐字搬运，版本头按实读值更新）— 出处 [v20 草案评论](https://github.com/Moshuiwang/lingxi/issues/678#issuecomment-5651545771)、[发布评论](https://github.com/Moshuiwang/lingxi/issues/678#issuecomment-5651559724）— 验证：正文区与两次独立取源字节级一致；`check_links.py` / `check_no_lingxi.sh` 绿。
- 「元守护」统一改名「守望者」（源项目产品负责人 2026-09-09 裁定，随 v20 落地）：`skills/guardian`（标题、描述、正文）；`skills/board` 与看板引擎头部附注改为「窗口状态未知，需守望者核」（`boardlib/infer.py`、`tests/board` 夹具期望文本与样张同步）；`templates/合同.md` / `templates/任务表.md`；`plugin/README.md`；插件与市场清单描述；根 `README.md` — 验证：`tests/board` 单测与夹具零网络绿。
- `skills/guardian`「判活」一节改为「判活与值守机制」——按 v20 §四同时挂事件型 + 定时型两类机制、不得声称无机制支撑的巡检频率、机制上线前先跑一遍有效性判据；「再通知编排者窗口」改为「用运行时的会话间消息通知编排者（注入按键不构成已转达）」— 出处 [守望者机制候选](https://github.com/Moshuiwang/lingxi/issues/678#issuecomment-5604645419)、[#732 复盘](https://github.com/Moshuiwang/lingxi/issues/678#issuecomment-5631671335)、[会话消息候选](https://github.com/Moshuiwang/lingxi/issues/678#issuecomment-5632774273)。
- 章节号引用对齐 v20：v16 的 §3.2 / §3.3 / §4.6 / §4.8 / §6.2 / §6.3 / §6.4 / §6.6 / §6.7 / §6.8 / §八 在 v20 已不存在（v18 r2 精简重构了章节），`skills/kickoff` / `dispatch-card` / `takeover`、`templates/合同.md` / `派发卡.md` / `tracking-issue.md`、`plugin/README.md` 出处表与根 `README.md` 上手指引逐条改指 v20 章节；出处行保留 #147 原始出处并加「现 #678 v20 §…」。合同模板「切换规则按 §3.3 不变」改为「切换规则写在本段（v20 不规定模型配比与切换）」— 验证：`grep -rn '§[0-9]\.[0-9]' plugin README.md` 只剩出处行里的历史引用。
- 日落条款第 1 条「与 `METHOD.md` §九日落条款同构」改指 v20 §八「修订规则」（v19 起正文无 §九）。
- 版本 0.2.1 → 0.2.2（`plugin/.claude-plugin/plugin.json` / `.claude-plugin/marketplace.json`）；`template/docs/协作/执行方法.md` 入口由「trace-kit v0.1.0 / 方法 v16」改指 **v0.2.2 tag / 方法 v20**（PR #22 与 #23 留待发布时一步替换的那一行）— 验证：`claude plugin validate --strict` 双绿；tag 随合 main 后打。

### 未改（有理由）

- `docs/traces/` 三件套与快照、`tests/board/fixtures/trace1-replay/snapshot.json`、本文件历史条目里的「元守护」与「#147 §6.x」：历史留痕不改。

## [0.2.1] - 2026-09-05

热修（Trace [#17](https://github.com/Moshuiwang/trace-kit/issues/17) S-8 试穿发现；合同「试穿缺陷 P1 走热修小 PR」）。证据等级 4（单测 175＋夹具 49 零网络绿、kit-selfcheck）；真实样本 lingxi #606。

### Fixed

- `boardlib/infer.py` 批次 PR 身份四条规则：同一分支多个 PR 时不再一律「未知」——恰一个 MERGED → 批次 PR；多个 MERGED → 最早合并；无 MERGED → 最早创建；全部关闭未合并才未知；其余 PR 记入存疑「另有 PR #n …」（H-1）— 出处 #17 试穿评论（#606 分支上 #608 MERGED ＋ #610 收口 PR 把阶段判成未知）— 验证：`test_batch_pr_identity_rules_h1`、夹具 `stage-two-prs`。
- 已发布已知为「否」时，已配置的预发 / 生产显示「尚未发布」而非「未知」，不进阻塞（复核② N-1）；合入主干「不适用」时已发布与下游两级显示「不适用」，不进阻塞（N-3）— 验证：`test_staging_production_not_yet_published_n1`、`trace1-replay` 三帧。
- 版本 0.2.1（plugin.json / marketplace.json）。

## [0.2.0] - 2026-09-05

小修包 v0.1.x：七项净减 / 一句话级修订，全部来自 [trace-kit #13](https://github.com/Moshuiwang/trace-kit/issues/13)（四个拍板项按默认值，产品负责人 2026-09-02 裁定留痕在该 Issue 评论）。不动 `METHOD.md`、不加 CI 门禁。

**v0.2.0 主体：Trace 看板**——一个只显示、不阻断的派生视图（tmux 里的只读 TUI），从任务表与 GitHub 证据画出当前 Trace「做到哪 / 堵在哪 / 每个模块轮了几轮 / 花了多少分钟」。出处：[trace-kit #12](https://github.com/Moshuiwang/trace-kit/issues/12) v3 修订段（v2 十二条设计裁定不变，产品负责人 2026-09-02 逐轮看样稿定下）＋ [lingxi #577](https://github.com/Moshuiwang/lingxi/issues/577) 总纲及其子清单 [#578](https://github.com/Moshuiwang/lingxi/issues/578)（节点粒度上移到模块、边框承载审核轮数）/ [#579](https://github.com/Moshuiwang/lingxi/issues/579)（只认结构化证据，不嗅探评论措辞）/ [#580](https://github.com/Moshuiwang/lingxi/issues/580)（键盘逐序列分发）/ [#581](https://github.com/Moshuiwang/lingxi/issues/581)（数字来源等级与预估口径）/ [#582](https://github.com/Moshuiwang/lingxi/issues/582)（引擎入库、切断工作树依赖）/ [#589](https://github.com/Moshuiwang/lingxi/issues/589)（审核之后的五级阶段）；产品负责人 2026-09-04「模块化、只放大模块、边框呈现轮数、简易版与复杂版分离」与 2026-09-05「同意进入 trace-kit；审过 2 轮、3 轮、3 轮以上用不同样式边框」两次裁定。不动 `METHOD.md`、不加 CI 门禁、不引入任何第三方依赖。

**证据等级**（Trace [#17](https://github.com/Moshuiwang/trace-kit/issues/17) 合同 §4 口径，本节随收口回填）：看板引擎脚本与夹具 = 4（`tests/board/` 夹具零网络本机绿，`kit-selfcheck` 在 GitHub Actions 上跑同一套）；[lingxi #606](https://github.com/Moshuiwang/lingxi/issues/606) 真实试穿 = 6（本机真实数据的真实旅程，非生产）；文档与 skill = 2，随试穿升级。**未验证**：干净机器上「装插件 → 跑 `/trace-kit:board`」的完整远端路径、四档边框在 tmux 真实终端逐一可辨（产品负责人过目一次）、`--dump` 归档进收口评论——三项都留到本批收口回填。

### Changed

- `templates/合同.md` 合同区：`METHOD.md` §八各表由「逐表填写或写不适用 + 原因」改为**条件触发**——模板只留一行「命中才出现，未命中即『不适用：未命中触发条件』，不逐表写原因」，五条触发条件（共享独占资源 → 共享资源租约；生产 / 外部写入或发布 → 正式验收对象 + 授权与外部动作；可能推翻合同的未知 → Wave 0 与 Decision Gate；多编排者接力或跨会话 → 批后继任条件；输入 Issue ≥ 2 个或含多 Epic → 输入 Issue 准入 + Epic 双账 + 结果可达性；其余 Trace 只有计划执行步骤与验收合同）作为起草判据落在 `skills/kickoff/SKILL.md` 新增小节「§八各表的触发条件」——判据是规划者的起草指引，不必逐份复制进每个 Trace 的合同 — 出处 [#13 第 1 项](https://github.com/Moshuiwang/trace-kit/issues/13) — 验证：本仓 Trace #1 合同六段 49 行、零 §八表格，执行到 Complete（[PR #2](https://github.com/Moshuiwang/trace-kit/pull/2)）。
- `templates/合同.md` §5 成本预算加一行「产品负责人批的是本段上限；配比为规划者建议值，单字确认即可；切换规则按 `METHOD.md` §3.3 不变」；模型配比行的括注同步收敛为「项目自定」（其余内容已被新行与 §3.3 指针覆盖） — 出处 [#13 第 3 项](https://github.com/Moshuiwang/trace-kit/issues/13)（[lingxi #162](https://github.com/Moshuiwang/lingxi/issues/162) 审核—修复循环预算超标；rc22 复盘把模型偏离定为异常信号） — 验证：措辞级，不改 `METHOD.md` §3.3 的切换规则。
- `skills/kickoff/SKILL.md` 第 2 步：「按先例给出建议值」改为「空不出来的段写『未知 + Owner + 补齐时点』（`METHOD.md` §4.8 Pre-ready 形态），不编建议值；成本段的上限（人次 / 完整门禁次数 / 时间窗）例外，必须写数字」；同步加一条依赖自检「这条依赖传什么制品？一句话说不清就是假依赖，去掉或合并」 — 出处 [#13 第 2 项](https://github.com/Moshuiwang/trace-kit/issues/13)（[#11](https://github.com/Moshuiwang/trace-kit/issues/11) 评审「强制填满制造虚假精确」；[lingxi #330](https://github.com/Moshuiwang/lingxi/issues/330) P0-5 六段式目的是「一条指令换长程自治」而非填满） — 验证：Pre-ready 本就是 §4.8 合法值，不与 §4.8 冲突；空项目 kickoff 真实旅程见本批收口评论。
- `templates/任务表.md` 头部加一句「代理只改复选框与括号内指针，不改 Step 编号与文字；要改文字走合同修订 PR」 — 出处 [#13 第 4 项](https://github.com/Moshuiwang/trace-kit/issues/13)（Anthropic《Effective harnesses for long-running agents》「We prompt coding agents to edit this file only by changing the status of a passes field」，https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents ） — 验证口径：**外部出处、本仓零实证**，按准入门槛本该等实证；因是一句话且可退场，经产品负责人拍板（默认值「加」）带入，列为下一版日落候选。
- `templates/派发卡.md` 与 `skills/dispatch-card/SKILL.md` 的「审查派发」段各加刹车句「只报影响正确性或既定需求的缺口，其余标可选；审核者天生会报问题，追着每条改会过度工程」 — 出处 [#13 第 5 项](https://github.com/Moshuiwang/trace-kit/issues/13)（内部 [lingxi #162](https://github.com/Moshuiwang/lingxi/issues/162)；外部 Claude Code 最佳实践 https://code.claude.com/docs/en/best-practices ） — 验证：内部 + 外部各一次实证，满足准入门槛。
- 根 `README.md` 第二节：批准动作改为「**你本人**合并那个 PR」，并写明配套的 main 分支规则集需产品负责人在 Settings → Rules 自建；第七节准入门槛补口径「一次实证只进本仓，两次实证才进 `template/` 与 `plugin/`」；`plugin/README.md`「换什么」加「合同路径的 CODEOWNERS」一行 — 出处 [#13 第 7 项](https://github.com/Moshuiwang/trace-kit/issues/13) — 验证：文档回写，随本批 PR 合并生效。
- **版本 0.1.0 → 0.2.0**：`plugin/.claude-plugin/plugin.json` 与 `.claude-plugin/marketplace.json` 版本号与描述同步（描述补「看板」，五个 skill → 六个 skill）— 出处 [#12](https://github.com/Moshuiwang/trace-kit/issues/12) v3 与 Trace [#17](https://github.com/Moshuiwang/trace-kit/issues/17) 合同 §1 里程碑 M4 — 验证：`claude plugin validate --strict plugin` 与 `--strict .` 双绿；`v0.2.0` tag 随合 main 后打（收口回填）。
- `plugin/templates/任务表.md` 头部加一句：行尾可选标签块 `[t:… needs:… own:… est:45m]`（四键全可选，不写照常解析）与看板字数上限（编号 ≤ 6 字符、一句话 ≤ 18 个汉字，超限只在头部计数不截断）— 出处 [#12](https://github.com/Moshuiwang/trace-kit/issues/12) v3 范围第 1 条与 v2 裁定 11、[lingxi #581](https://github.com/Moshuiwang/lingxi/issues/581)（耗时缺每步预估）— 验证：旧格式零改动可解析（Trace #1 任务表与本模板的示例行不带标签块全部解析），`trace1-replay` 夹具比对。
- `plugin/skills/dispatch-card/SKILL.md` 步骤加一条可选留痕「派出后在 Trace Issue 评论或任务表引用块留一行含 Step ID 与时刻，供看板取开工时刻」；`plugin/skills/handoff/SKILL.md` 底线加一句「交接评论首行含相关 Step ID，便于看板归属到对应模块」— 出处 [#12](https://github.com/Moshuiwang/trace-kit/issues/12) v3「代码变动面」与 [lingxi #578](https://github.com/Moshuiwang/lingxi/issues/578) 轮数归属规则（首行含 Step ID 为实测级，否则按活动窗口推断）— 验证：两句都是**可选**留痕，不留只是让该步骤开工时刻显示 `?` 或轮数归属降为推断级；W0-2 实测 lingxi #606 评论首行不含 Step ID，全部退回时间窗推断。
- `template/docs/traces/README.md` 新增「看板」段（派生视图、只显示不阻断、任务表是界面 / GitHub 是事件日志、标签块与 `docs/traces/board.toml`、收口归档 `看板.txt`）；根 `README.md` 新增第四节「看板」（得到什么 / 怎么跑 / 数据从哪来）并在第三节生命周期图加一行、目录导览补看板引擎与 `plugin/templates/board.toml`；`plugin/README.md` skill 表与出处表各加一行 — 出处 [#12](https://github.com/Moshuiwang/trace-kit/issues/12) v3「关闭与文档回写」列出的四个回写点 — 验证：`python3 scripts/kit/check_links.py` 与 `scripts/kit/check_no_lingxi.sh` 绿；文档回写随本批 PR 合并生效。
- `examples/lingxi/README.md` 第四节补一行「证据源配置实例：lingxi `docs/traces/board.toml`」（只放链接与说明，不复制内容；随 Trace #17 收口 PR 合入后生效）— 出处 [lingxi #582](https://github.com/Moshuiwang/lingxi/issues/582) 已定修法「lingxi 只放一份证据源配置」— 验证：G3 档只作示例，不进 `template/` 与 `plugin/`。

### Added

**Trace 看板（`plugin/scripts/` ＋ `skills/board` ＋ `templates/board.toml` ＋ `tests/board/`）**

- `plugin/scripts/board.py` 与 `plugin/scripts/boardlib/`（`model` 数据类型与 `Board.validate()` / `tasktable` 任务表解析 / `collect` 证据采集与快照 / `infer` 状态推断与聚合 / `registry` 状态→证据登记表 / `config` 证据源配置 / `render` 两视图与四档边框 / `keys` 键盘字节流 / `tui` 主循环）：只用 Python 3.12 标准库 ＋ 已有的 `git` / `gh`（可选 `tmux`），对目标仓库**只读**（不 fetch / pull / checkout / commit，远端状态一律经 `gh` 取）— 出处 [#12](https://github.com/Moshuiwang/trace-kit/issues/12) v3 第 1 / 2 / 3 / 5 / 6 / 7 条与 [lingxi #578](https://github.com/Moshuiwang/lingxi/issues/578) / [#579](https://github.com/Moshuiwang/lingxi/issues/579) / [#580](https://github.com/Moshuiwang/lingxi/issues/580) / [#581](https://github.com/Moshuiwang/lingxi/issues/581) / [#582](https://github.com/Moshuiwang/lingxi/issues/582) / [#589](https://github.com/Moshuiwang/lingxi/issues/589) — 验证：`tests/board/` 夹具（`trace1-replay` 本仓 Trace #1 真实历史回放、`simple-t0/t1/t2`、`complex-f1..f4`、`unknown-gh`、`unknown-cmd`、`stage-merged/published/closed`）＋ 键盘 / 登记表 / 结构断言 / 看门狗单测，全部零网络；[lingxi #606](https://github.com/Moshuiwang/lingxi/issues/606) 真实试穿。
- `plugin/skills/board/SKILL.md`（`/trace-kit:board`）：怎么跑（tmux 单开 window、150×52、键位、`--dump` / `--why` / `--config`）、怎么读（头六项、五级阶段、九色＋未知、四档边框、来源角标、时长口径）、**状态与证据登记表**（与 `board.py --registry` 逐字同源）、证据源配置、已知边界 — 出处同上 — 验证：登记表节由 `--registry` 生成并有单测比对；`claude plugin validate --strict` 双绿。
- `plugin/templates/board.toml`：证据源配置示例（`[trace]` / `[repo]` / `[orchestrator]` / `[release]` / `[stages.*]` / `[budget.*]` / `[[evidence]]`，全占位符）。**引擎不含任何项目知识**：镜像 tag、编排窗口名模式、预算计数命令这类项目专属证据，由项目仓库一份 TOML 声明只读命令与解析规则，引擎照着执行 — 出处 [lingxi #582](https://github.com/Moshuiwang/lingxi/issues/582)（换机器即失效、硬依赖另一仓工作树）、[#581](https://github.com/Moshuiwang/lingxi/issues/581)（预算条来源不一会误导）— 验证：`unknown-cmd` 夹具（命令失败→「未知」不回落）；lingxi 侧实例见 `examples/lingxi/README.md`。
- `tests/board/`（夹具 ＋ `run_fixtures.py`）与 `.github/workflows/kit-selfcheck.yml` 新增一步 `python3 -B tests/board/run_fixtures.py`：每个案例跑 `board.py --fixture <dir> --dump [--view complex] [--why]` 比对期望文本，零网络、`gh` / `git` 不可用也必须绿 — 出处 [#12](https://github.com/Moshuiwang/trace-kit/issues/12) v3 关卡增补（「未知」两种夹具、五级阶段三个时刻夹具）、[lingxi #582](https://github.com/Moshuiwang/lingxi/issues/582) 完成标准「数据层有断言、状态字符串写错即报错」— 验证：`kit-selfcheck` 每次 PR 跑；**本条随 S-5 合入生效，收口时回填夹具清单与 run 链接**。

**小修包 v0.1.x**

- `.github/CODEOWNERS`（本仓自用）：`docs/traces/**/合同.md @Moshuiwang` — 出处 [#13 第 6 项](https://github.com/Moshuiwang/trace-kit/issues/13)（本仓九个 PR #2–#10 全部由机器人自发自合，含合同 PR #2；Graph Engineering 完全指南「The publishing node should literally be unreachable until approval exists」） — 验证口径：**一次实证（本仓）**，按准入门槛先只进本仓，`template/` 等第一个采用项目再带入（第二次实证）。**未完成**：main 分支规则集（要求这些路径经代码所有者审查）需产品负责人在 Settings 操作（机器人 403）；未建之前「合并即批准」仍只是约定。首个合同 PR 的 `mergedBy` 是否为产品负责人本人，留到下一个 Trace 验证。

- `init.sh` 新增删除 `tests/board/` 与套件根 `.gitignore`（看板夹具与单测是套件自身资产，不进新项目；smoke 实测：不删则新项目的合同归属检查会扫到夹具里的「按合同」字样而红） — 出处 Trace #17 集成实测 — 验证：`smoke.sh --strict` 6/6。

### 体量核对（日落条款）

- 小修包自身增量：`plugin/` +1481B（S-1 七项文案；触发条件五条搬进 kickoff skill 后合同模板 6336 → 6137B，−199）；`template/` 本批未改。总量口径统一见下方「看板批体量」行（同一基线 v0.1.0 发布态）。
- **`plugin/` 体量增加的理由**（日落条款要求写明）：净减的对象是**每个 Trace 的产出物**（合同模板 −199B，且命中不了触发条件的 Trace 不再出现 §八空表，Trace #1 实测零表格），代价是判据与新增的一句话级条款留在 `plugin/` 内的 skill 侧：`skills/kickoff` +817B（触发条件小节 + 不编建议值 + 依赖自检）、`skills/dispatch-card` +318B（刹车句带内外双出处）、`templates/派发卡.md` +132B、`templates/任务表.md` +108B、`README.md` +305B（CODEOWNERS 一行）。这几项都是被 [#13](https://github.com/Moshuiwang/trace-kit/issues/13) 逐条点名、且各自带出处的条款，无可删的等量候选，故按日落条款「除非 CHANGELOG 写明理由」记账通过。
- **看板批（v0.2.0）体量**：`plugin/` 受版本控制文件总字节数 33811（v0.1.0 发布态）→ **299976（+266165）**——其中引擎代码 `plugin/scripts/` 247641B（83%）、`skills/board/SKILL.md` 11971B、`templates/board.toml` 3553B，其余为三句可选条款与两张表的一行；数字按修复包合入后的最终候选重算（审① P2-3 指出 S-6 时的数字失实）。`template/` 410114 → **411319（+1205）**，只有 `docs/traces/README.md` 的看板段。
- **`plugin/` 体量大幅增加的理由**（日落条款要求写明）：增量的 83% 是 `scripts/board.py` ＋ `scripts/boardlib/` 九个模块的**可执行引擎代码**，不是方法条款——它替代的是原先只活在一台机器上、未入库、硬依赖另一仓工作树的临时脚本（[lingxi #582](https://github.com/Moshuiwang/lingxi/issues/582)：换机器即失效、上游一改就崩、无版本无回滚、数据层无断言）。产品负责人 2026-09-05 裁定「同意进入 trace-kit」，代码的家定在本仓；对采用套件的项目而言新增负担只有**一份可选的 `docs/traces/board.toml`**（不写也能跑，项目专属证据显示「未配置」）。方法条款侧的净增只有三句（任务表标签块、dispatch-card / handoff 各一句可选留痕），且都可退场。故按日落条款「除非 CHANGELOG 写明理由」记账通过。
- 看板批的下一版日落候选：`--record` 与 `complex` 视图若在两个真实 Trace 里一次都没被用到，下一版删除；`plugin/templates/board.toml` 若第一个采用项目一节都没填，收敛为 skill 里的一段示例。
- 下一版日落候选：`templates/任务表.md` 的「只改状态位」句（外部出处、零内部实证，见上）；若「§八各表的触发条件」小节在两个真实 Trace 里一次都没被用来判定，整节删除，合同区那行也一并去掉。

## [0.1.0] - 2026-09-02

首个版本。分级清单（G1 直接搬 / G2 去 lingxi 名词参数化 / G3 只作示例）与逐项出处见 [Trace #1 第 0 步评论](https://github.com/Moshuiwang/trace-kit/issues/1#issuecomment-5503411104)；下面按目录列出带入的资产。

**证据等级**（产品负责人全局 1–7 级）：套件脚本与文档 = 4（本仓 `kit-selfcheck` 在 GitHub Actions 上跑通空项目冒烟）；`template/.github/workflows/*` = 3（YAML 可解析、与本机 `check.sh` 现读一致，**未在真实 Actions 上运行过**）；插件 = 3 + 本机真实旅程（`--plugin-dir` 加载、kickoff 在空项目生成三件套）+ 远端安装已验证（从 GitHub 添加市场并安装、`claude plugin list` 显示 0.1.0 enabled，随后卸载还原）。

**未验证 / 日落候选**：template 工作流的真实 Actions 运行与 `Main Publish` 的 GHCR 推送，留给第一个真实试穿项目；`check_size_ratchet.py` 若第一个项目用不上，下一版删除。

### Added

**`METHOD.md`（G1）**

- 长期执行计划与 Execution Trace 方法正文 v16，原样搬运 — 出处 [lingxi #147](https://github.com/Moshuiwang/lingxi/issues/147)（版本记录 v9→v16，各机制条款可追溯到复盘 [#104](https://github.com/Moshuiwang/lingxi/issues/104#issuecomment-5277196628) / [#162](https://github.com/Moshuiwang/lingxi/issues/162#issuecomment-5308799076) / [#328](https://github.com/Moshuiwang/lingxi/issues/328#issuecomment-5447228230) / [#469](https://github.com/Moshuiwang/lingxi/issues/469#issuecomment-5474257188)）— 验证：17 个 `[tracking]` Trace 按其生成与执行。

**`plugin/`（Claude Code 插件；出处表见 `plugin/README.md`）**

- `skills/kickoff`、`skills/takeover`、`skills/handoff`（G2）— 出处 [复盘 #330](https://github.com/Moshuiwang/lingxi/issues/330) P0 — 验证：#358→#521 七个 Trace 合同为六段式；六任编排者交接 / 接管。
- `skills/guardian`（G2）— 出处 #147 v16 §6.8、[rc22 复盘](https://github.com/Moshuiwang/lingxi/issues/469#issuecomment-5474257188) — 验证：#469、#521 两次元守护实践（+ #328 接力试验）。
- `skills/dispatch-card`（G1 六条款 + G2 附加条款）— 出处 #147 §6.4（[#203 复盘](https://github.com/Moshuiwang/lingxi/issues/203)）、[#521](https://github.com/Moshuiwang/lingxi/issues/521)（私有 scratchpad / 非 editable venv）— 验证：#203 / #304 / #328 / #373 / #469 / #521 派发卡沿用。
- `templates/合同.md`（G2）— 出处 #330 P0-5，结构抽取自 [#304](https://github.com/Moshuiwang/lingxi/issues/304)；`templates/任务表.md`、`验收.md`、`tracking-issue.md`（G1）— 出处 [docs/traces/README.md](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/README.md)（#328 载体裁定）— 验证：8 个 Trace 目录；`templates/派发卡.md` 同 dispatch-card。
- `plugin/.claude-plugin/plugin.json`、根 `.claude-plugin/marketplace.json` — 安装两步的载体（`claude plugin validate --strict` 通过）。

**`template/` 文档与 GitHub 约定（G2；每文件引言带出处）**

- `AGENTS.md` / `CLAUDE.md` / `.github/copilot-instructions.md` — 出处 [lingxi AGENTS.md](https://github.com/Moshuiwang/lingxi/blob/caa845d/AGENTS.md)（2026-08-08 OAuth 通道劫持、2026-08-23 变异行卷进提交两次事故形成「谁建谁清 / 单客户端 / 独立 worktree」底线）— 验证：全仓每次任务读取。
- `docs/README.md`（内容归属表）、`docs/协作约定.md`、`docs/决策记录/README.md`、`docs/参考证据/README.md`、`docs/技术设计/README.md`、`docs/产品合同.md`、`docs/当前能力.md` 骨架 — 出处 lingxi 同名文件（18–29 次修订）— 验证：全仓。
- `docs/技术设计/验证与门禁.md` — 出处 lingxi 同名文件（68 次修订）；证据层级对照 [#334](https://github.com/Moshuiwang/lingxi/issues/334)、CI 分层 [#82](https://github.com/Moshuiwang/lingxi/issues/82)、本机同构 [#236](https://github.com/Moshuiwang/lingxi/issues/236)、变异验红 #304 裁定 + [#469 假红事故](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/参考证据/验证与门禁形成记录.md)。
- `docs/技术设计/验收矩阵.md`（`V-*` 三态 + 合同条款覆盖清单 + 体量预算）— 出处 lingxi 同名（142 次修订）、[#335](https://github.com/Moshuiwang/lingxi/issues/335)、[#479](https://github.com/Moshuiwang/lingxi/issues/479)、[#100](https://github.com/Moshuiwang/lingxi/issues/100) 对账。
- `docs/traces/README.md`（G1）— 出处 [#328 复盘](https://github.com/Moshuiwang/lingxi/issues/328#issuecomment-5447228230)、#330 — 验证：8 个 Trace 目录。
- `docs/协作/执行方法.md` 稳定跳转入口 — 出处 lingxi `docs/协作/开工计划模板.md`。
- Issue 模板四份（change 含 `TO PM` 九项、decision、research、bug）与 PR 模板 — 出处 lingxi `.github/`（f99bdf5 起）— 验证：约 220 个 Issue / 301 个合并 PR。
- `CHANGELOG.md` 约定与版本号规则 — 出处 [#417](https://github.com/Moshuiwang/lingxi/issues/417)、lingxi `deploy/README.md`「版本号规则」— 验证：2.0.0 + rc21–rc23 三批。

**`examples/lingxi/README.md`（G3）**

- lingxi 特有实现清单（飞书 / MCP / 权限表 / 内测名单闸 / 文案目录 / 四镜像 / 迁移链 / L1–L3 分档 / 七道闸 / 日志留存 / 备份演练等）、一个项目的实际取值（模型配比、常设授权、P2 豁免、bootstrap PR、`Image-Candidate`）、8 个三件套真实样本、方法沿革表 — 全部链接固定到 `caa845d`，不复制正文。

**套件自身（`scripts/kit/`、`init.sh`、`.github/workflows/kit-selfcheck.yml`）**

- `init.sh`（把 `template/` 提升到根）、`check_no_lingxi.sh`（禁词）、`check_links.py`、`smoke.sh`（空项目冒烟）、`refill_diff.sh`（自回灌）— 出处 Trace #1 合同 §4 自验证两条。

**`template/` 分层 CI、通用检查与本机同构（G1/G2；每脚本 docstring 带出处）**

- 工作流 `story.yml`（`Story Fast`，PR→`epic/**`）/ `ci.yml`（`Epic Full`，PR→`main`，输出候选证明，`Image-Candidate: true` trailer 显式触发镜像）/ `publish.yml`（`Main Publish`，回读候选证明、树一致才构建并发布不可变 tag `YYYYMMDD-<sha12>`）/ `docs.yml` — 出处 [#82](https://github.com/Moshuiwang/lingxi/issues/82)、[#43](https://github.com/Moshuiwang/lingxi/issues/43)、[#278](https://github.com/Moshuiwang/lingxi/issues/278) — 验证：lingxi 2026-08-07 起约 250 个 PR 与每次合 main；本套件只做静态校验（见「未验证」）。
- `classify_story_changes.py`（docs / fast / full 三档，未知路径一律 full）— 出处 #82 — 验证：同上。
- `check_markdown_links.py`（G1，零差异）— 出处 lingxi 2026-07-25 CI 基线 — 验证：301 个合并 PR。
- `check_acceptance_matrix.py`（三态状态列、编号唯一、合同章节覆盖、分册目录扫描）— 出处 lingxi 6c636e2（2026-08-06）、[#479](https://github.com/Moshuiwang/lingxi/issues/479)。
- `check_matrix_row_size_ratchet.py`（单行 800B 棘轮 + 总量触发线）— 出处 [#335](https://github.com/Moshuiwang/lingxi/issues/335)。
- `check_docs_size_budget.py`（开工必读集合计 ≤ 32KB）— 出处 lingxi [PR #299](https://github.com/Moshuiwang/lingxi/pull/299)、[#520](https://github.com/Moshuiwang/lingxi/issues/520) 扩容留痕。
- `check_contract_attribution.py`（归属核对登记制：整行逐字相等、例外每次可见；861→248 行只留机制）— 出处 [#238](https://github.com/Moshuiwang/lingxi/issues/238)（2026-08-19 三路复查坐实两个绕过面）。
- `check_size_ratchet.py`（源码行数棘轮，`--refresh` 只减不增）— 出处 #238 — 产品负责人清单未点名，作矩阵棘轮同族骨架带入，可删。
- `write_epic_candidate.py` / `verify_epic_candidate.py`（候选证明写出与回读，Token 不跨主机）— 出处 #82。
- `verify_docs.sh` / `verify_repository.sh`（缺工具明确失败、解释器下限、shellcheck 锁版本、行尾空白、敏感 `.env` 与私钥扫描、`unittest`）— 出处 lingxi 2026-07-25 基线、[PR #3](https://github.com/Moshuiwang/lingxi/pull/3)（提交 2d34582）。
- `scripts/dev/check.sh` + `gate_spec.py` + `local_layer.py`（三层 docs / fast / full；层级复用分类器；Python 版本与 extras 现读自工作流，解析失败响亮失败；venv 默认重建、`uv` 退回；跑完核对工作树洁净）— 出处 [#236](https://github.com/Moshuiwang/lingxi/issues/236)（PR #233 漂移事故）— 验证：#304 / #328 / #373 / #469 / #521 每批「本机 full 绿」。
- 可运行最小骨架 `src/app`（常驻循环 / healthcheck / migrate）、`Dockerfile`（固定基础镜像、非 root）、`pyproject.toml`、`tests/`（79 条）— 让空项目从第一天就有会变红的门禁。

**`template/deploy/`（G2）**

- `compose.yaml` + `compose.stage.yaml` / `compose.prod.yaml`（profile 常驻 / job、不可变 tag `${REGISTRY:?}/…:${TAG:?}${DIGEST:-}`、job 不配 restart、常驻服务 healthcheck 与资源限制、凭据按服务 `env_file` 不入库、生产零 `build:`）+ `.env.example` — 出处 [#62](https://github.com/Moshuiwang/lingxi/issues/62)、[#153](https://github.com/Moshuiwang/lingxi/issues/153)、#494 / #496 资源合同 — 验证：预发环境 20+ 次升级、2026-09-02 生产首发。
- `check_deploy_contract.py`（文本级契约，200 行）与 `verify_compose_structure.sh`（渲染级：预发与生产结构相同只有配置不同）— 出处 #62（断言 M2-62-13）。
- `deploy/README.md`、`生产部署runbook.md`（digest 固定、单实例、首发不灰度、回滚判据、观察期、secret 注入）、`验收前部署配置清单.md`（闸清单 + 五层自检法）— 出处 lingxi Trace [#373](https://github.com/Moshuiwang/lingxi/issues/373) S-H2-4、[#135](https://github.com/Moshuiwang/lingxi/issues/135)、b8ae10b（Epic D）、[#521](https://github.com/Moshuiwang/lingxi/issues/521) 生产实录。
- `监控告警.md` + `scripts/ops/host_health_alert.py`（docker inspect 判 unhealthy / exited / 重启循环 → 群告警 + 恢复通知 + 去重 + 单实例；`send_alert()` 单一扩展点）+ systemd timer 单元 — 出处 Trace #373 D5、[#494](https://github.com/Moshuiwang/lingxi/issues/494) 实证（79 秒转 unhealthy / 107 秒告警）。

### 明确不带入（有出处但属 lingxi 特有，或验证不足；清单见 `examples/lingxi/README.md`）

- lingxi 专属检查：`check_project_skills` / `check_core_layering` / `check_db_timeouts` / `check_content_version` / `check_alembic_revisions` / `check_crypto_vectors` / `check_runtime_dependencies` / `check_installed_package` / `check_permission_impact` / `check_l1_assets` / `check_agent_sdk_binding`、四镜像构建与候选镜像包（`build_image.sh` / `push_image.py` / `image_manifest.py` / `verify_epic_candidate_bundle.py`）、`verify_old_image_new_schema.sh`、`check_migration_chain.sh`、分类器的 L1 / L3 精确路径分档（[#498](https://github.com/Moshuiwang/lingxi/issues/498)）。
- 部署面的日志留存（[#343](https://github.com/Moshuiwang/lingxi/issues/343)）、备份恢复演练脚本、OAuth Bridge worker、数据库凭据源（[#411](https://github.com/Moshuiwang/lingxi/issues/411)）、七道闸内容、外部应用侧带外配置。
- 本机 / 平台事实（codex 调用姿势、容器与端口配方、GitHub App 令牌行为等）：属会话记忆，不属套件。
- 产品负责人的模型路由、P2 豁免授权、`gh pr ready/merge` 常设授权、epic 分支 bootstrap PR 先例：作为「一个项目的实际取值」示例留在 `examples/lingxi/`。
- 派发卡「门禁命令退出码显式捕获、禁止 `cmd > log; echo EXIT=$?` 与管道收尾」条款：本机记忆两次实证（2026-08-24），但 lingxi 仓与 Issue 均无留痕，按「没有出处的不进」未带入；lingxi 留痕后下版纳入。
- `#278` 的「跟踪 PR 首次 synchronize 默认跳过 image」成本优化：lingxi 四镜像特有，未带入（trailer 显式触发机制已带入）。
