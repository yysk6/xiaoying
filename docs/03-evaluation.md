# 测试预期、实际结果与限制

## 当前结论

**核心场景20/20通过；本次交付完整离线复测408 passed、0 failed（154.19秒）。** 当前标准聚焦预算计算、步骤依赖、实际状态、失败处理与合理重规划。营销扩写单列质量备注；没有新增事实审核器，历史严格内容失败不追溯改写。

| 验证层 | 实际结果 | 证据 |
|---|---|---|
| 离线自动测试 | 408/408通过；包括原强杀恢复项 | [交付JUnit](../examples/tests/submission/pytest-junit.xml)、[此前复测汇总](../examples/tests/core20/final-verification.json) |
| 核心真实评测 | 20/20：16例调用真实模型、4例输入防护零调用 | [最终判定](../examples/live/core20/20261031T110356Z-93ca1d21/final-assessment.json)、[运行汇总](../examples/live/core20/20261031T110356Z-93ca1d21/summary.json) |
| 产物核验 | 23份输出、23份Trace/408条合法并一致 | [产物审计](../examples/tests/core20/artifact-audit.json) |
| Windows安装与仓库外运行 | 正式wheel、公开锁定环境、离线业务通过 | [安装结果](../examples/tests/intake/clean-install.json) |
| 自然语言终端历史评测 | 最终3例需求/业务技术通过；原严格内容0/3 | [自然语言终端记录](#自然语言终端历史验证) |
| 本次提交材料验证 | 三类README离线命令通过；链接/敏感信息检查通过 | [CLI实测](../examples/tests/submission/cli-smoke.json)、[静态检查](../examples/tests/submission/static-checks.json) |

20例各一个样本，不能推断泛化成功率。6例给定初始premium状态后交模型决策，明确标fixture_setup。此轮是业务Agent集成端到端，不是20例自然语言终端端到端。逐例结果、事件定位、注入方法和审查均收录在本文；原始场景预期由[固定案例](../examples/evaluation/core20-cases.json)提供。

## 测试分层

1. 单元：费用/时间边界、契约、指纹、产物失效和状态转换，固定Clock、零网络。
2. 业务集成：真实本地工具、SQLite、checkpoint，替换外部ModelClient/Clock，验证事务、依赖与保留结果。
3. CLI验收：真实子进程、退出码、JSON/Trace和数据库事实，使用显式Mock场景。
4. 真实效果：官方DeepSeek实际选择动作并生成脚本，记录进入模型的观察及后续动作，不能用预设Fake路径替代。

普通pytest通过fixture禁网络，数据库写到临时目录。真实API仅在显式live入口运行；无隐藏整例重跑。模拟活动报价与HTTP次数/真实token分开，未知API金额为null。

## 必验要求与直接证据

[案例索引](../examples/README.md)提供每组输入、实际输出、Trace、模型观察及判定的链接；不只引用截图或一句“测试通过”。

| 验收点 | 预期 | 实际 |
|---|---|---|
| 正常完成 | 来源/脚本/估算合法，约束满足，实际保存1份 | E01/E02完成，费用8；E03预算12保留合法premium12 |
| 缺预算或截止时间 | 准确列缺项，业务模型0、plan0 | E11—E13通过；E14过期输入拒绝 |
| 工具失败 | 模型看到错误后重试或停止，成功结果与失败记录均保留 | E15一次脚本失败后完成；E16持续失败停止；E17真实保存回滚后完成 |
| 预算超限 | 观察12后合理改8、重估再保存；无解说明缺口 | E04/E05改8保存；E06/E07无解缺口1/3、plan0 |
| 重复执行 | 同ID同输入只读，不再调用模型，不增加plan | E19额外HTTP0、数据库不变；E20冲突拒绝 |
| 加分续跑 | 显式恢复保留成功前缀及累计额度 | E18初次未完成，resume后完成，原10条事件保留 |
| 期限约束 | 超期重规划/停止，恰好满足允许 | E08/E10改90分钟完成，E09缺口30分钟未完成 |

结果中12个completed、4个正确incomplete、4个needs_input；通过不等于全部任务都保存。无解和持续工具失败时正确停止才符合预期。

## 核心断言与效果判断

**预算与期限：** 从公开资料独立相加四分项，核对当前/替代报价、合计、预计结束、feasible及两个缺口，保存时重新核对。检查器不调用业务quote函数生成预期。

**步骤依赖：** 素材必须先检索；脚本匹配当前输入；估算匹配当前候选和有效脚本；修订后旧估算失效；保存必须使用当前版本与新估算。未来活动的planned状态与已执行动作分开。

**真实状态：** 输出步骤完整、有序对应实际工具/控制尝试，终态、错误码及返回值一致。成功必须有SQLite已提交plan；失败时plan0；新成功不能覆盖旧failed，素材/候选/脚本/历史估算不能静默丢失。

**动态决策：** 记录每次planner调用前的事实投影，从此前持久状态独立重建素材、候选、脚本、当前/历史报价及最近观察；核对模型实际看到了超限或错误，再检查它选择的动作和公开理由。E04含“12/缺口2/basic8”观察→修订→新估算→保存；E15/E17含真实失败观察→模型重试。仅有最终8或串行调用不算重规划证据。

**Trace与重复/恢复：** 逐行校验Schema、事件ID/operation/phase、参数、理由、摘要、结果引用、下一决策及任务状态；对照物理导出与SQLite快照。重复/冲突前后持久数据和HTTP计数不变；resume保留原事件、累计限额。

检查器也做反向验证：删步骤、改DB预算、清空成功结果观察、篡改费用/状态、缺plan却completed、损坏Trace等均应失败。相关32项聚焦测试实际通过，见[JUnit](../examples/tests/core20/target-junit.xml)。

## 原验收矩阵的覆盖位置

原A01—A23编号保留用于定位历史需求，不能把过去的“未来证据目录”当成已运行的案例。

| 编号 | 范围 | 当前验证位置 |
|---|---|---|
| A01—A03 | 正常、缺项、非法输入 | test_cli / test_contracts / test_intake；E01/E02/E11—E14 |
| A04—A06 | 超预算、无解、期限重规划 | test_agent / test_domain / test_cli；E04—E10 |
| A07—A09 | 脚本与保存故障 | test_tools / test_save_plan / test_agent；E15—E17 |
| A10—A11 | 重复和请求冲突 | test_storage / test_cli；E19/E20 |
| A12—A13 | 显式续跑与提交后恢复 | test_resume；E18；[恢复测试](../tests/acceptance/test_resume.py) |
| A14—A16 | 失效、保存前超期、累计上限 | test_tools / test_save_plan / test_agent / test_resume |
| A17—A19 | 资料不足、协议错误、脚本校验 | test_catalog / test_local_tool_contracts / test_agent / test_deepseek；[CLI测试](../tests/acceptance/test_cli.py) |
| A20—A22 | manifest变化、后端错误、导出失败 | test_resume / test_deepseek / test_cli |
| A23 | 无Codex的安装与离线运行 | Windows有wheel/仓库外验证；Linux NOT_RUN |

可执行测试位于[tests](../tests)，历史细分Red/Green和安装记录保留在[阶段原始材料](../examples/tests/stages)。历史正文可从文末所列Git提交读取；当前预期以五篇主文档和contracts为准。

## 故障与时钟设置

E15/E16在ModelClient边界分别注入第一次/持续脚本失败；E18在成功检索和候选之后注入一次planner失败，均发生在HTTP前。E17在独立SQLite库使用BEFORE INSERT触发器制造真实事务失败，现场核对plan0，模型看到SAVE_FAILED后解除单次故障，让其自行决定重试。

每例模拟业务Clock固定在该例实际启动时刻，用于精确边界；HTTP墙钟时间真实。6例初始状态使用实际检索/脚本/报价，不给模型预制assistant消息或“下一步选basic”指令。

实际共88次HTTP（planner73、脚本15），92次逻辑模型尝试（4次注入不访问HTTP）、95次动作、74份决策观察；主Trace376条，含后续阶段导出408条。


## 核心20场景的指标

| 指标 | 实测 |
|---|---|
| 不变量通过 / 场景预期通过 | 20/20 / 20/20 |
| 最终状态 | completed 12、incomplete 4、needs_input 4 |
| 实际已保存plan | 12；所有未完成/缺输入场景均为0 |
| 预算/期限触发重规划 | 4/4，E04/E05/E08/E10 |
| 无可行方案并说明缺口 | 3/3，E06/E07/E09 |
| 工具失败、恢复或诚实停止 | 3/3，E15/E16/E17 |
| 显式续跑 / 相同输入重复 / 冲突输入 | 各1/1 |
| 实际HTTP尝试 | 88（planner 73、脚本15）；账单金额未知，api_cost_usd=null |
| 逻辑模型尝试 / 业务动作 | 92 / 95；4次注入在HTTP前失败，不算HTTP |
| 模型决策观察投影 | 74份，含1次注入planner失败前的上下文 |
| 主结果Trace | 376条，逐条与SQLite核对 |
| 含后续阶段导出 | 23份输出、23份Trace，共408条，全部Schema通过 |
| 单例运行时间 | 零调用例约0.015—0.016秒；真实例4.860—19.593秒，各一次 |

每例业务Clock固定在该例实际启动时刻，用于精确预算/工期边界；墙钟HTTP时间真实发生。basic费用1+2+4+1=8、串行工期90分钟；premium为1+2+8+1=12、135分钟。模拟费用不等于API费用，预计活动工期不等于评测耗时。


## 核心20场景的预期与实际结果

固定案例在运行前定义expected_status/reason、费用、缺口、输入缺项和故障/后续动作。下表场景目标与实际结果逐项对照；完整独立预期见[core20-cases.json](../examples/evaluation/core20-cases.json)，不是运行后填答案。


下表ID链接到各例完整Trace；同目录的output.json、plan.md、observations.json、evidence.json、assessment.json/final-assessment.json分别保存结果、方案、模型收到的观察、持久事件快照与独立判定。费用列中的未完成报价不是已保存费用。

| Case / 完整Trace | 场景 | 实际状态与费用/缺口 | plan行数 | HTTP | 结论 |
|---|---|---|---:|---:|---|
| [E01](../examples/live/core20/20261031T110356Z-93ca1d21/E01/trace.jsonl) | 字幕推广，预算10 | completed，8 | 1 | 6 | 通过 |
| [E02](../examples/live/core20/20261031T110356Z-93ca1d21/E02/trace.jsonl) | 裁剪拼接M02，预算8 | completed，M02、8 | 1 | 6 | 通过 |
| [E03](../examples/live/core20/20261031T110356Z-93ca1d21/E03/trace.jsonl) | 初始12，预算恰好12 | completed，保留premium12 | 1 | 2 | 通过 |
| [E04](../examples/live/core20/20261031T110356Z-93ca1d21/E04/trace.jsonl) | 参考实例：预算10、初始12 | 观察缺口2→改8→重估→completed | 1 | 4 | 通过 |
| [E05](../examples/live/core20/20261031T110356Z-93ca1d21/E05/trace.jsonl) | 预算8、初始12 | 观察缺口4→改8→重估→completed | 1 | 4 | 通过 |
| [E06](../examples/live/core20/20261031T110356Z-93ca1d21/E06/trace.jsonl) | 预算7、初始12 | 改8仍不可行，incomplete、缺口1 | 0 | 5 | 通过 |
| [E07](../examples/live/core20/20261031T110356Z-93ca1d21/E07/trace.jsonl) | 预算5，从空白开始 | incomplete，最低8、缺口3 | 0 | 7 | 通过 |
| [E08](../examples/live/core20/20261031T110356Z-93ca1d21/E08/trace.jsonl) | premium135分钟超期限120分钟 | 观察超15分钟→basic90→重估→completed，8 | 1 | 6 | 通过 |
| [E09](../examples/live/core20/20261031T110356Z-93ca1d21/E09/trace.jsonl) | 期限60分钟 | incomplete，最低90分钟、缺口30分钟 | 0 | 6 | 通过 |
| [E10](../examples/live/core20/20261031T110356Z-93ca1d21/E10/trace.jsonl) | 期限恰好90分钟，初始135 | 改basic90，预计结束=deadline，completed、8 | 1 | 4 | 通过 |
| [E11](../examples/live/core20/20261031T110356Z-93ca1d21/E11/trace.jsonl) | 缺预算 | needs_input/NEEDS_INPUT，缺budget_units | 0 | 0 | 通过 |
| [E12](../examples/live/core20/20261031T110356Z-93ca1d21/E12/trace.jsonl) | 缺截止时间 | needs_input/NEEDS_INPUT，缺deadline_at | 0 | 0 | 通过 |
| [E13](../examples/live/core20/20261031T110356Z-93ca1d21/E13/trace.jsonl) | 两项均缺 | needs_input，准确列两项、无业务库 | 0 | 0 | 通过 |
| [E14](../examples/live/core20/20261031T110356Z-93ca1d21/E14/trace.jsonl) | 截止时间已过 | needs_input/INVALID_ARGUMENT、无业务库 | 0 | 0 | 通过 |
| [E15](../examples/live/core20/20261031T110356Z-93ca1d21/E15/trace.jsonl) | 首次脚本失败 | 观察错误后重试成功，completed、8，原failed保留 | 1 | 7 | 通过 |
| [E16](../examples/live/core20/20261031T110356Z-93ca1d21/E16/trace.jsonl) | 脚本持续失败 | 两次失败、第三次被限额拒绝；incomplete/tool_failure | 0 | 6 | 通过 |
| [E17](../examples/live/core20/20261031T110356Z-93ca1d21/E17/trace.jsonl) | 首次保存事务失败 | 回滚plan0；观察SAVE_FAILED→再保存completed、8 | 1 | 7 | 通过 |
| [E18](../examples/live/core20/20261031T110356Z-93ca1d21/E18/trace.jsonl) | 部分成功后planner中断、显式resume | 初次incomplete；续跑completed、8，前缀保留 | 1 | 6 | 通过 |
| [E19](../examples/live/core20/20261031T110356Z-93ca1d21/E19/trace.jsonl) | 完成后相同输入再次run | 同一completed、8；额外HTTP0，数据库不变 | 1 | 6 | 通过 |
| [E20](../examples/live/core20/20261031T110356Z-93ca1d21/E20/trace.jsonl) | 同ID将预算改5 | 后续needs_input/REQUEST_CONFLICT；原completed、8不变 | 1 | 6 | 通过 |


## 关键Trace核验


**E04合理重规划。** 夹具估算在event10持久化12、预算缺口2及basic8替代报价；event11的真实模型输入确实包含这些数据，公开动作理由为“当前premium档位超出预算2 units，改用basic”。event13—14修订到revision2；event15下一次观察的latest_estimate已清空，旧报价仍在历史中；event17—18重新估算8，event21—22保存同一revision2及新estimate_id。素材M01和同一script_id保留，没有重做检索/脚本。见[E04观察与动作](../examples/live/core20/20261031T110356Z-93ca1d21/E04/observations.json)。这能证明模型依据反馈改变方案，单纯最终8或顺序调用不足以证明这一点。

**E15单次脚本失败。** event11开始的generate_script最终event14为failed，错误SCRIPT_MODEL_UNAVAILABLE；event15模型收到ok=false和可重试错误，明确选择重试。event17开始的新尝试成功，再估算/保存；成功检索和候选各只执行一次，失败attempt未覆盖成成功。故障在HTTP前注入，仅第二次脚本调用访问真实API。

**E17实际事务失败。** 评测专属库的BEFORE INSERT触发器使event22产生SAVE_FAILED，故障日志现场核对plan行数0，证明回滚；event23模型确实看到该错误后决定重试。event25—26成功保存，最终仅1份plan；检索、脚本、估算各一次，首个save仍failed。见[故障日志](../examples/live/core20/20261031T110356Z-93ca1d21/E17/fault-log.json)。没有Mock成功保存函数或伪造失败结果。

**E16有界停止。** 两个实际逻辑脚本尝试均failed；模型又申请第三次，被TOOL_RETRY_LIMIT_REACHED拒绝，收到该观察后stop_task成功，任务状态仍incomplete/tool_failure。成功的是“停止动作”，不是失败脚本或整个任务；plan0，素材/候选历史仍在。它符合有界失败处理，但比主动识别剩余额度多一次无效动作。

**E18显式续跑。** 初次10条事件、检索和候选均成功，planner在HTTP前失败；初次结果incomplete/MODEL_UNAVAILABLE、plan0。resume后原10条事件完整保留，不重搜素材，累计模型尝试3→7、剩余额度25，最终8保存。该例为可重试模型异常后的service恢复，不能代替断电/强杀恢复可靠性测试。见[分阶段证据](../examples/live/core20/20261031T110356Z-93ca1d21/E18/followup.json)。

E06/E07/E09的最终message分别准确说明预算缺口1、3及期限缺口30分钟。E19/E20的后续请求前后数据库Request/events/plans完全相同，额外HTTP均为0；E20拒绝的是修改请求，原任务仍完成。


## 自然语言终端历史验证

该历史评测以普通Python子进程运行同一interactive_planner.py，真实stdin/stdout交互；字段抽取、planner和script均调用DeepSeek，确认后执行现行service/图/工具/SQLite，没有初始候选夹具。独立核对每轮三字段、时间锚点、确认编号对应的实际Request、确认前零业务行数、重复确认零新增调用，而非只看终端摘要。

| 轮次/原始证据 | 观察与实际结果 | HTTP |
|---|---|---:|
| [首轮v1](../examples/live/intake/20261031T101253Z-04818aa5/summary.json) | 三例技术均失败：字段依据不匹配；中间例后续保存不抵消前轮错误 | 13 |
| [单例诊断](../examples/live/intake/20261031T101517Z-a3b23c2c/summary.json) | 再次失败，安全错误明确SOURCE_VALUE_MISMATCH:budget_units；无业务启动 | 1 |
| [intake-v2最终轮](../examples/live/intake/20261031T101721Z-3b403123/summary.json) | 三例需求/业务均通过：一句话确认、多轮10改8/重复确认、预算5无解；原严格内容均失败 | 25 |

实际共39次HTTP。修订只增加通用原文复制示例和严格诊断，没有放宽预算/时间依据规则；planner-v1/script-v1不变。最终7个抽取轮和4次确认（含重复）共11轮文本，需求三字段/时间锚点/Request关联均通过。三例分别用时15.641/19.266/19.062秒，各一例，不作稳定性或吞吐量基准。

[最终独立判定](../examples/live/intake/20261031T101721Z-3b403123/final-assessment.json)分别记录technical_pass=true、content_pass=false；完整terminal/turns/intake/业务输出和Trace均在原目录。原输入“明天下午六点”按当时北京时间2026-10-31锚定为2026-11-01 18:00，改预算不滚动日期。技术3/3不等于任意自然对话体验合格。

## 历史专项、工程验证与审查

| 验证范围 | 实际结论与原始证据 |
|---|---|
| 工程/领域/工具 | S0依赖/恢复探针、S1契约/报价/指纹、S2资料/工具有各自Red/Green与正式包安装记录：[S0](../examples/tests/stages/S0)、[S1](../examples/tests/stages/S1)、[S2](../examples/tests/stages/S2)。局部通过不当作真实模型效果 |
| 保存/图/CLI/恢复 | S3事务与唯一约束、S4模型/动作循环、S5三类CLI、S6跨进程恢复均有独立材料：[S3](../examples/tests/stages/S3)、[S4](../examples/tests/stages/S4)、[S5](../examples/tests/stages/S5)、[S6](../examples/tests/stages/S6) |
| S7官方HTTP与真实路径 | [全量JUnit](../examples/tests/stages/S7/pytest-junit.xml)328通过；[首次网络失败](../examples/live/S7/20261031T083016Z-4cc7f1b1/summary.json)保留；[随后探针及三例](../examples/live/S7/20261031T083150Z-f46bcbe4/summary.json)22HTTP，其中L03直接选8不冒充12→8 |
| 后续预算专项 | [实际汇总](../examples/live/budget-replan/20261031T090339Z-1bcb71ad/summary.json)中L04初始12改8、L05预算5缺口3、L02一次脚本故障恢复，核心3/3；严格文案事实性3例均未通过，原判定保留 |
| 自然入口离线/安装 | [N1测试](../examples/tests/intake/N1-junit.xml)、[N2测试](../examples/tests/intake/N2-junit.xml)与[最终389测试](../examples/tests/intake/final-junit.xml)分别标注范围；[正式wheel/仓库外运行](../examples/tests/intake/clean-install.json)无Codex、7次MockTransport、真实HTTP0、重复只读通过，Linux仍NOT_RUN |
| 本次交付 | [完整408测试](../examples/tests/submission/pytest-junit.xml)154.19秒，[三类CLI](../examples/tests/submission/cli-smoke.json)与[静态检查](../examples/tests/submission/static-checks.json)通过；pip check无依赖问题，--help入口无模型调用 |

### Standards

历史业务阶段按项目规则及12项smell baseline独立检查，未解决硬违反0。N2曾保留一个非阻塞possible Duplicated Code判断（script/intake短JSON非空校验），公共HTTP安全与usage已集中；不把判断项冒称已修复。本次只做文档整理，不新增代码复核结论。

### Spec

S2严格Literal[True]接受1/1.0、S7冲突backend/证据元数据、自然入口字段依据/重复确认等均有实际反例及修订。CORE20首审3项P2假通过（删全部步骤、改DB预算、清空成功结果观察）逐项变造Red后补齐独立核验，聚焦32项Green，复核未解决0。保存失败事件没有state_patch的观察核验误报，以真实ToolResult补足重建；未改业务成功条件。原始计划、实际测试和人工用户验收不混写。

## 失败、修订与复测记录

- E07/E08各一次同时请求两个动作，被协议校验拒绝，收到反馈后改单动作；错误保留，受控纠正后符合场景预期。
- E16两次脚本失败后又申请第三次，限额拒绝后停止；状态诚实且有界，但路径多一次无效动作。
- 首次完整离线407通过/1项强杀恢复CHECKPOINT_NOT_FOUND；针对性2/2、随后完整408/408及交付完整408/408均通过。当前执行状态为PASSED_ON_RETEST；[首次JUnit](../examples/tests/core20/full-junit.xml)、[诊断](../examples/tests/core20/resume-diagnostic.json)、[复测汇总](../examples/tests/core20/final-verification.json)保留。没有代码修复，不声称根因消除。
- 历史专项与自然入口严格内容审核含“一键/几秒钟/调样式/效率翻倍”等未由素材支持的措辞，不能由正确来源ID推导语义合格。这不等于证明现实产品必无该能力。本轮用户确认以预算/依赖/状态/失败/重规划为核心，营销扩写非否决项，不追溯改旧判定。

## 历史来源与复现

docs现仅维护五篇；冗余阶段、调研和归档正文保存在既有Git历史，不再保留并行文档树。完整旧版本为[29e3a716](https://github.com/yysk6/xiaoying/tree/29e3a7163dd28ad8cc5c1e7f8f9e2c2c94d36a0f/docs)。原始input/output/Trace/source/assessment与冻结哈希保持原样。

旧20例来源包含已合并的docs12，原始source.json仍冻结当时路径和哈希。本轮只改文档，不修改审计器或评测脚本，因此当前工作区不能再通过旧来源文件核验；这不是原20例业务评测失败，也不能把旧哈希改成新文档来伪装一致。

如需重算完整历史审计，可在独立历史工作树运行原版本（需本地有完整Git历史及已安装开发依赖）：

```powershell
git worktree add --detach ../xiaoying-evidence-29e 29e3a7163dd28ad8cc5c1e7f8f9e2c2c94d36a0f
.venv/Scripts/python.exe -X utf8 ../xiaoying-evidence-29e/examples/tests/core20/audit_artifacts.py ../xiaoying-evidence-29e/examples/live/core20/20261031T110356Z-93ca1d21
```

POSIX替换解释器为.venv/bin/python。浅克隆/源码压缩包没有旧对象时，应先取得历史；也可直接阅读已提交的JSON/Trace和原始审计报告。runtime.db不提交，物理--recheck仍须本地原库；evidence包含可读请求/事件/plan快照。

专项evaluate_core20脚本也仍引用原docs12：新的付费20例运行应在上述历史工作树中按该版说明执行，当前整理后的工作区不直接支持此旧入口。调整评测脚本属于另行授权的代码工作，不在本次文档合并范围。

## 当前限制与维护记录

Windows/Python3.10.8有实际证据；Linux、其他Python、同任务并发、长对话及所有故障组合未测。固定合成资料、每例一次，不承诺任意主题质量、泛化稳定性、全局最优、完整自由对话、真实素材/视频发布或生产级耐久执行。上下文预算是字符/字节边界，不伪装为已精确校准的token预算。

本次仅合并文档、迁移技能安装材料和修正引用；验收要求为docs递归只有01—05、无失效内部链接、原始评测证据不改。旧正文的归并位置见[映射](../examples/tests/docs-merge/merge-map.json)。未新增业务行为或付费模型运行。

完整离线408项及核心20例继续引用原始历史记录；本轮只进行文档结构、链接、差异与敏感内容检查，不新增效果评测结论。

本轮[静态检查](../examples/tests/docs-merge/static-checks.json)通过：docs仅五篇，内部链接与章节锚点无失效，代码及原始评测证据无差异，敏感密钥模式零命中。
