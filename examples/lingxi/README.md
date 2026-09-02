# examples/lingxi：一个真实项目怎样把套件里的通用模式填成具体实现

> 出处：trace-kit 第 0 步 G1/G2/G3 分级清单（[trace-kit #1 评论](https://github.com/Moshuiwang/trace-kit/issues/1#issuecomment-5503411104)）中判为 **G3** 的资产。
> 全部链接固定到公开仓 [Moshuiwang/lingxi](https://github.com/Moshuiwang/lingxi) 的 commit `caa845d`；Issue / PR 号指向该仓当前状态。

## 一、是什么 / 怎么用 / 换什么

- **是什么**：本目录只是**一个项目的实际取值样本**，不是可复用资产——里面每一条都绑死在 lingxi 的业务链路、代码结构、迁移链和外部依赖上，**照抄到你的项目会直接错**。
- **怎么用**：对照 `template/` 里的同名骨架读——骨架给的是「这里要有一条什么」，本目录给的是「lingxi 在这一格里填了什么、为什么填这个」。骨架是要交付的，样本只是用来判断自己填得够不够具体。
- **换什么**：**一切产品名词**。服务名、职责名、门禁断言编号、环境固定名称、外部平台与机器人、数据表与配置文件名、模型配比数字、授权条目——全部换成你自己的；本目录留下的只有「这一格该被填成多具体」这个尺度。

## 二、G3 资产逐条

判定标准只有一条：**换个项目就得整条重写**的，进本目录；只有名词要换、结构照用的，进 `template/` 与 `plugin/`。

### 2.1 A11 模型路由与常设授权

- **解决什么**：把「谁用哪档模型、哪些动作不必逐次请示」写成合同条款，让编排者在产品负责人离场时仍能推进。
- **挡住过什么**：审核—修复循环反复导致预算超标（[#162 2026-08-14 授权评论](https://github.com/Moshuiwang/lingxi/issues/162#issuecomment-5291739097)）。
- **为什么是项目特有**：配比与授权范围是该项目产品负责人当次的裁定，随预算与风险偏好变化。**实际取值见下方第三节。**

### 2.2 B3 固定名称与环境职责表

- **解决什么**：一个项目里同时存在多台机器与多个机器人时，口头混称会让「这条命令在哪执行」成为事故来源。lingxi 的做法是在协作约定里立一张**六行固定名称表**（两台研发机、受控验收环境、生产环境、测试机器人、正式机器人），所有 Issue、PR、文档和交接一律只用固定名称，首次出现时才可同时写实际名称。
- **挡住过什么**：生产服务器与正式机器人**名称相近**导致的混称——这正是立表的直接起因（见表前说明）。
- **链接**：[`docs/协作约定.md#L5`](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/协作约定.md#L5)（表内主机路径与实际名称不在本目录转录）。
- **为什么是项目特有**：名称、台数与职责划分是这套部署形态的形状；`template/` 里进的是「立表」这条约定本身，不是表的内容。

### 2.3 C12 与代码结构绑定的 CI 门禁

这批脚本每一个都绑定 lingxi 的目录结构、迁移链、依赖清单或四镜像形态，**不复制进套件**；这里只列「它各挡住过什么」，供你判断自己的项目需不需要同一类门禁。每条「挡什么」摘自该脚本文件头注释。

| 脚本 | 它挡什么 |
| --- | --- |
| [`check_project_skills.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/check_project_skills.py) | 仓库内项目级 Skills 的基础结构（命名与 frontmatter 字段）失守——只用标准库检查，不引依赖。 |
| [`check_core_layering.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/check_core_layering.py) | 「核心层不 import 适配层、应用层与任何外部 SDK」此前只是散文约束，由测试与代码审查把守；在实测零违规那一刻加门禁最省成本——**等第一处违规出现再补，就得先处理一份存量豁免清单**（[#238](https://github.com/Moshuiwang/lingxi/issues/238)）。 |
| [`check_db_timeouts.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/check_db_timeouts.py) | 数据库连接绕过统一工厂、迁移连接没有有限边界；按 AST 识别连接入口，避免把注释或字符串里的历史文字误判成违规。 |
| [`check_content_version.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/check_content_version.py) | 用户可见文案改了、版本标识没跟着改，而**没有任何东西会红**——一个没人强制的版本号会逐渐变成看起来存在、实际不可信的追溯信号，排查线上文案问题时反而误导人（[#190](https://github.com/Moshuiwang/lingxi/issues/190)）。 |
| [`check_alembic_revisions.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/check_alembic_revisions.py) | 不连库就能判定的四类迁移缺陷：多 head 与**孤儿 revision**（安静地不被执行）、`down_revision` 指向不存在的 id、静默的空 downgrade（把版本号退回去而库结构没变）、文档里的 head id 与实现脱节（[#53](https://github.com/Moshuiwang/lingxi/issues/53)）。 |
| [`check_crypto_vectors.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/check_crypto_vectors.py) | 加解密互操作向量的用例带条件跳过，缺库时**跳过而不是失败**——整组断言一条没跑，测试输出却是绿的（[#156](https://github.com/Moshuiwang/lingxi/issues/156)）。要求执行数非零、跳过数为零。 |
| [`check_runtime_dependencies.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/check_runtime_dependencies.py) | 运行时依赖漏声明、安全边界组件写版本范围。因为源码**全是函数内延迟导入**，只扫模块级 import 等于没扫：漏声明要到生产镜像第一次走到那个分支才炸，而那时它表现为一次用户请求失败，不是一次构建失败。 |
| [`check_installed_package.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/check_installed_package.py) | 测试跑源码目录、部署跑安装出来的制品，两者因打包配置或包初始化文件遗漏而分叉，**分叉在部署时才暴露**；刻意不做条件跳过——一个看起来像通过的跳过比不检查更危险。 |
| [`check_permission_impact.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/check_permission_impact.py) | 权限事实配置改动看不见扩权面。只读两个 Git ref 的配置做集合差，产出新增授予面与收缩面两栏；**绝不拿角色数、配置行数或任何内部 ID 冒充受影响用户数**（[#498](https://github.com/Moshuiwang/lingxi/issues/498)；[#520](https://github.com/Moshuiwang/lingxi/issues/520) F3 把仓库外登记从必需降级为可选并如实标注未验证声明）。 |
| [`check_l1_assets.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/check_l1_assets.py) | 用户可见事实源的轻门禁：内容目录键集合与运行时登记表必须精确相等，别名表与管理员可见出口做 fail-closed 术语扫描——「轻」不等于「不校验」（#498、#520 F1）。 |
| [`check_agent_sdk_binding.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/check_agent_sdk_binding.py) | 单元测试用桩模块替换整个外部 SDK，锁得住自己这侧的形状，却抓不到三类问题：锁定的 SDK 版本装不上、构造签名变了、选项对象不再接受我们传的字段。用真实 SDK 构造一次对象，不调模型、不用凭据、不发网络请求。 |
| [`build_image.sh`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/build_image.sh) | 可变 tag。tag 两段各有职责——日期标识发布批次、提交 sha 标识源码；带上 sha 才不可变，「回滚 = 切回上一个 tag」这件事才有意义。只打 `latest` 或分支名的镜像**无法回滚**（[#62](https://github.com/Moshuiwang/lingxi/issues/62)）。 |
| [`push_image.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/push_image.py) | 推送失败被吞成绿色。降级必须是**显式分支**：权限类失败降级为留证产物并发警告，其余一律非零退出。用 `continue-on-error` 或 `\|\| true` 会让「推上去了」和「没推上去」在 CI 上长得一模一样（#62）。 |
| [`image_manifest.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/image_manifest.py) | 用 image ID 或 manifest digest 判定两次构建是否等价——镜像配置里的时间戳让**同一份内容每次构建的 digest 必然不同**，那样只会得到「永远不等价」这个无用结论。改为内容级清单逐行比对，并显式排除 mtime 与打包顺序。 |
| [`verify_epic_candidate_bundle.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/verify_epic_candidate_bundle.py) | 候选镜像包「产物写对了」只是假设。三层校验：完整性（清单结构、文件齐全、大小与摘要一致）、**来源绑定**（防「文件是对的，但对应的是另一个 PR 或另一次构建」）、导入一致（回读镜像 digest）（[#150](https://github.com/Moshuiwang/lingxi/issues/150)）。 |
| [`verify_old_image_new_schema.sh`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/verify_old_image_new_schema.sh) | 「切 tag 回滚」只有在**旧镜像能在新库结构上正常工作**时才成立。一旦某次破坏性迁移合并了，回滚就从「切 tag 重启」变成「恢复数据库备份」——那是完全不同量级的事故。 |
| [`check_migration_chain.sh`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/check_migration_chain.sh) | 过渡期两条血统只测其中一条。两条建出**结构相同但对象名字不同**的库时建库不报错，等某条按名字改约束的迁移落地才炸，而那时两边已经跑了几个月；因此每次门禁实际建两个库并要求转储逐字节相等（#53）。 |
| [`check_deploy_contract.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/check_deploy_contract.py)（完整版） | 部署编排里那些**改坏了不会有任何东西报错**的约束：停止宽限期、凭据路径是否落持久卷、生产编排里混进构建定义、镜像 tag 可变、非 root。刻意不依赖 docker 与 YAML 库，判定落在去掉整行注释之后的文本上——注释里就写着「本文件没有构建键」这样的句子，天真的 grep 会把说明文字当违规（#62）。**套件里进 `template/` 的是精简版（只保留上述通用断言）**。 |
| [`classify_story_changes.py`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ci/classify_story_changes.py) 的 L1/L3 精确路径分档 | 「按扩展名或提交者自称的类型」分档。分层依据是**这批改动能改变什么**：L1 只允许用户可见文案与其追溯/术语事实源，L3 只允许权限事实配置并**额外生成影响面**。清单故意用完整精确路径、不接受通配符，避免新增、重命名或路径转义变体意外落进轻门禁（#498）。#520 F2 起 L1 轻量档**停用**、路由回完整门禁（内容资产随镜像发布，走轻量档会让合入后找不到候选证明），判定代码原样保留待重启。**三档路由与「未知路径一律升级」是 G2，已进 `template/`。** |

### 2.4 D8 运维与外部依赖

只写「它是什么、为什么是项目特有」；具体坐标、主机、凭据一律不在本目录出现。

- **容器日志留存**（[`deploy/日志留存.md`](https://github.com/Moshuiwang/lingxi/blob/caa845d/deploy/日志留存.md)，[#343](https://github.com/Moshuiwang/lingxi/issues/343)）：重部署把旧容器换成新容器，日志跟着旧容器消失——**不是「日志被清理」，而是「新容器从来没有旧容器的日志」**。一次真实会话调查因此只能靠数据库字段等效还原，而那条等效来源在内测轮结束后就没有了。裁定不引入重型日志栈，改为「日志驱动上限 + 宿主增量收集 + 轮转」两层。项目特有：取证窗口时长是产品裁定，收集脚本绑定这套容器命名与宿主目录布局。
- **备份恢复演练**（[`scripts/ops/backup_restore_drill.sh`](https://github.com/Moshuiwang/lingxi/blob/caa845d/scripts/ops/backup_restore_drill.sh)）：从运行库**只读**导出一次 → 恢复进一个全新建立、不发布任何宿主端口的隔离实例 → 只向隔离实例注入合成过期行 → 用镜像里**真实的清理代码路径**（不是手写 SQL）补跑一次 → 核对「按原始写入时间计算到期，恢复不重置保留起点」→ 销毁隔离实例与全部临时产物。项目特有：断言编号、保留天数与清理代码入口都是本项目的；可复用的是「演练脚本必须自己写清破坏半径」这条纪律。
- **OAuth Bridge worker**（[`workers/oauth-bridge/README.md`](https://github.com/Moshuiwang/lingxi/blob/caa845d/workers/oauth-bridge/README.md)）：受控验收期用的一段边缘转发器，把浏览器授权回调的一次性结果即时转发给已认证的受控验收环境；身份换取、校验、建档与加密续期凭据保存**全部留在自己的机器上**，回调页默认只等两种无身份结果，不显示也不保存身份资料。项目特有：绑定该产品的外部身份平台与一个自有回跳域名，且**只服务受控验收，不属于正式用户路径**。
- **数据库凭据源**（[`deploy/README.md#L88`](https://github.com/Moshuiwang/lingxi/blob/caa845d/deploy/README.md#L88)，[#411](https://github.com/Moshuiwang/lingxi/issues/411)）：连接串的**唯一事实源**是目标机器上、仓库工作副本之外的私有凭据文件（属主与权限位受控），各服务环境文件里的连接行由同步脚本派生；凭据不复制到研发机、不进日志、Git、Issue 或 PR。项目特有：托管数据库选型是一条产品决策（[#40](https://github.com/Moshuiwang/lingxi/issues/40)），而「凭据只在目标机器上」是上面那张环境职责表的推论。
- **七道闸**（[`deploy/验收前部署配置清单.md#L11`](https://github.com/Moshuiwang/lingxi/blob/caa845d/deploy/验收前部署配置清单.md#L11)）：把「**进程正常运行、但某条职责悄悄不注册**」这一类失败逐道拆开——每道闸独有哪些配置、缺哪一项会让哪条职责不注册、用户会看到什么。它挡住过两件真事：① 三个配置项曾被并列成「独立可选」，实际捆在同一道注册前置后面，照旧版本部署会得到「七道闸看起来全开、实际谁也开不了」（[#275](https://github.com/Moshuiwang/lingxi/issues/275) 更正）；② 某道闸「存在于代码但从未被真实调用验证」，真实第三方返回形状与默认解析器认的形状不同，后果是**每个用户必然**走满同步超时、永远拿不到完成态，而全部单元测试在假传输层上全绿。项目特有：闸的数量与内容就是这条业务链路的形状；`template/` 里进的是**五层自检法骨架**，不是七道闸。
- **外部应用侧带外配置**（[同上文件 `#L145`](https://github.com/Moshuiwang/lingxi/blob/caa845d/deploy/验收前部署配置清单.md#L145)）：正式机器人在第三方应用平台侧的九项外部依赖（权限与版本发布、事件订阅、重定向地址、管理群成员、可用范围、两处数据表的读写、专用授权主体凭据、上面那段 Bridge），每项配一条只读核对方式。登记理由写在文件里：**这九项没有任何一条会让 CI 变红**，写下来就是为了未来迁移或重建应用时能逐项核对（#520 F12）。项目特有：条目完全由所选外部平台决定；可复用的只有「带外交付项要单独成节、只登记名字与来源形态，值不入库」这条纪律。

## 三、一个项目的实际取值（合同 §2 / §5 示例）

以下全部引自公开仓内容，只作**范例尺度**参考——不是推荐值。

- **模型配比与代理预算**（[`521 合同 §5`](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/521-rc24正式上线/合同.md)）：编排者 opus / max；实施与复修 opus / high；**唯一独立审核者** fable / xhigh（批终一次 + 复核一次 + 上线前 runbook 走查一次，不参与实现、不直接修复）；规划者与元守护 fable；外部 codex 审核可选 ≤1 次。配套硬上限：Epic Full ≤4；实施/复修 ≤10 人次；审核 ≤3 轮；**每次派发编排者自挂兜底观察，不裸等；子代理不得再派子代理**。
- **常设授权「以后不要再问」**（同一份合同 §2「常设授权引用」）：`gh pr ready` / `gh pr merge`（产品负责人 2026-08-06 明示「以后不要再问」）、推送用的专用机器身份、epic 分支 bootstrap PR 先例、P2 豁免、受控验收环境全权限（生产仍除外）。**登记过的才不必逐次请示**——合同里没写的授权不存在。
- **P2 豁免授权**（[#162 2026-08-14 评论](https://github.com/Moshuiwang/lingxi/issues/162#issuecomment-5291739097)）：不重要的 P2 经编排者确认后可以不修直接合并，以防审核—修复循环反复导致预算超标；**红线与 P1 不豁免，且须留痕**。
- **epic 分支 bootstrap PR 先例**（[#106](https://github.com/Moshuiwang/lingxi/issues/106) / [#164](https://github.com/Moshuiwang/lingxi/issues/164)）：epic 分支挂了「仅 Story Fast 通过后合并」的规则集，机器身份不能直接推空提交上去；新建 epic 分支前先开一个**空 diff 的 Story PR** 走完既有路径取得检查。空 diff 会被分类器判成完整门禁（「没有改动路径」和「高风险改动」共用同一个兜底分支），这是空 diff 场景下唯一可选的路径，不能绕开。
- **`Image-Candidate: true` trailer**（[#278](https://github.com/Moshuiwang/lingxi/issues/278)，[`deploy/README.md#L168`](https://github.com/Moshuiwang/lingxi/blob/caa845d/deploy/README.md#L168)）：epic 分支每次合入都自动构建镜像，实测一轮 5 次只用到 1 次，遂改为**编排者冻结前显式触发**。落地细节值得抄的是纪律而不是数值：trailer 必须独占一行、精确文本、前后无多余字符；squash 合并要**显式指定提交信息**，因为默认 squash 消息不保证带上这一行。

## 四、三件套真实样本

每个目录都是一次完整的 Trace 载体：`合同.md`（六段式）/ `任务表.md` / `验收.md`。目标句摘自各目录 `合同.md` 第一节。

| Trace 目录 | 这次 Trace 要拿到什么 |
| --- | --- |
| [`328-权限层三角与内测遗留收尾`](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/328-权限层三角与内测遗留收尾/合同.md) | 权限来源补成完整三角，内测遗留的已裁定项全部清空，硬切推进到「可执行或明确不执行」。 |
| [`358-修复与拆分`](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/358-修复与拆分/合同.md) | 内测用户三条已知坑路径全部填平，同时调度循环独立、巨石文件拆分归零、方法文档版本一致。 |
| [`373-清仓冲刺`](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/373-清仓冲刺/合同.md) | 24 小时内清空全部开放 Issue（15 个中关闭 13 个），在功能、卫生、部署就绪三面同时收口。 |
| [`418-2.0发布就绪清仓`](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/418-2.0发布就绪清仓/合同.md) | 关闭九张卡并收口上一 Trace，达到「除生产动作外 2.0 发布全部就绪」，备齐次日切换材料。 |
| [`445-rc21清卡冲刺`](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/445-rc21清卡冲刺/合同.md) | 单批关闭八张卡并连带收口上一 Trace，逐卡按其 Issue 内「自证闭环条款」关卡。 |
| [`469-rc22打磨与体验批`](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/469-rc22打磨与体验批/合同.md) | 管理员与用户在下一个受控验收版本上得到三条可见改善：管理链全程零内部 ID、并发不再被长任务饿死、任何消息必有可见响应。 |
| [`502-rc23清仓批`](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/502-rc23清仓批/合同.md) | 清仓现存全部可做卡，使生产放行的技术前置只剩硬切与放行动作本身。 |
| [`521-rc24正式上线`](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/521-rc24正式上线/合同.md) | 完成 2.0 真实业务上线——生产环境跑冻结制品、正式权限表独占写入、正式机器人成为唯一入口，首批真实用户走到「开通完成」。 |

载体规范本身（三件套怎么写、放哪里、何时更新）是 G1，见 [`docs/traces/README.md`](https://github.com/Moshuiwang/lingxi/blob/caa845d/docs/traces/README.md) 与套件 `template/docs/traces/README.md`。

## 五、lingxi 方法沿革（[#147](https://github.com/Moshuiwang/lingxi/issues/147) v9 → v16）

套件的 `METHOD.md` 就是 v16 原文。这张表说明它是**怎么长出来的**：每一版新增条款都能追到一次复盘或事故，且 v13 起有日落条款——新增须同时提名删除候选，正文体量不得超过上一版。

| 版本 | 日期 | 主要新增 |
| --- | --- | --- |
| v16 | 2026-08-31 | §6.8 常驻 session ＋ 批次 window ＋ 元守护；§6.7 临时授权失效时点；§6.6 变异验红硬姿势。 |
| v15 | 2026-08-30 | 规划 / 编排分会话、供应商中立适配、单一独立审核、批后接力；删除成本命令与全局模型默认。 |
| v14 | 2026-08-28 | 三件套载体、会话接力、编排者模型字段并入。 |
| v13 | 2026-08-24 | 派发、攒批、审查、主线、收口核账与验证金字塔频率并入；删除未维护的动态表。 |
| v12 | 历史 | 首触冒烟、双通道、夹具合同、静态排除对账。 |
| v11 | 历史 | 可达性审计、Wave 0、Step ID、终点分账、共享资源租约。 |
| v10 | 历史 | 四层工作、两层合同、分层 CI、固定候选、统一缺陷账本（[#83](https://github.com/Moshuiwang/lingxi/issues/83)）。 |
| v9 | 历史 | 最早的开工计划模板（[#59](https://github.com/Moshuiwang/lingxi/issues/59)）。 |

**复盘出处**：[#104](https://github.com/Moshuiwang/lingxi/issues/104#issuecomment-5277196628)（→ v11）、[#162](https://github.com/Moshuiwang/lingxi/issues/162#issuecomment-5308799076)（→ v12）、[#203](https://github.com/Moshuiwang/lingxi/issues/203)（→ v13）、[#328](https://github.com/Moshuiwang/lingxi/issues/328#issuecomment-5447228230)（→ v14）、[#330](https://github.com/Moshuiwang/lingxi/issues/330)（两周编排复盘：摩擦榜与 P0/P1/P2 改进清单）、[#469](https://github.com/Moshuiwang/lingxi/issues/469#issuecomment-5474257188)（→ v16）。
