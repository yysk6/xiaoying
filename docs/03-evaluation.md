# 测试预期、实际结果与限制

## 当前结论

**核心场景20/20通过；本次交付完整离线复测408 passed、0 failed（154.19秒）。** 当前标准聚焦预算计算、步骤依赖、实际状态、失败处理与合理重规划。营销扩写单列质量备注；没有新增事实审核器，历史严格内容失败不追溯改写。

| 验证层 | 实际结果 | 证据 |
|---|---|---|
| 离线自动测试 | 408/408通过；包括原强杀恢复项 | [交付JUnit](../examples/tests/submission/pytest-junit.xml)、[此前复测汇总](../examples/tests/core20/final-verification.json) |
| 核心真实评测 | 20/20：16例调用真实模型、4例输入防护零调用 | [最终判定](../examples/live/core20/20261031T110356Z-93ca1d21/final-assessment.json)、[运行汇总](../examples/live/core20/20261031T110356Z-93ca1d21/summary.json) |
| 产物核验 | 23份输出、23份Trace/408条合法并一致 | [产物审计](../examples/tests/core20/artifact-audit.json) |
| Windows安装与仓库外运行 | 正式wheel、公开锁定环境、离线业务通过 | [安装结果](../examples/tests/intake/clean-install.json) |
| 自然语言终端历史评测 | 最终3例需求/业务技术通过；原严格内容0/3 | [N3报告](stages/N3.md) |
| 本次提交材料验证 | 三类README离线命令通过；链接/敏感信息检查通过 | [CLI实测](../examples/tests/submission/cli-smoke.json)、[静态检查](../examples/tests/submission/static-checks.json)、[交付记录](stages/SUBMISSION.md) |

20例各一个样本，不能推断泛化成功率。6例给定初始premium状态后交模型决策，明确标fixture_setup。此轮是业务Agent集成端到端，不是20例自然语言终端端到端。完整逐例结果、事件定位、注入方法及审查见[CORE20报告](stages/CORE20.md)，先行预期见[20场景规格](12-core20-evaluation.md)。

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
| A12—A13 | 显式续跑与提交后恢复 | test_resume；E18；[S6](stages/S6.md) |
| A14—A16 | 失效、保存前超期、累计上限 | test_tools / test_save_plan / test_agent / test_resume |
| A17—A19 | 资料不足、协议错误、脚本校验 | test_catalog / test_local_tool_contracts / test_agent / test_deepseek；[S5](stages/S5.md) |
| A20—A22 | manifest变化、后端错误、导出失败 | test_resume / test_deepseek / test_cli |
| A23 | 无Codex的安装与离线运行 | Windows有wheel/仓库外验证；Linux NOT_RUN |

可执行测试位于[tests](../tests)。逐阶段的实施前规格和历史验证保存在[整理前评测快照](archive/pre-submission/03-evaluation.md)及[阶段报告](stages/CORE20.md)，当前预期以主文档与contracts为准。

## 故障与时钟设置

E15/E16在ModelClient边界分别注入第一次/持续脚本失败；E18在成功检索和候选之后注入一次planner失败，均发生在HTTP前。E17在独立SQLite库使用BEFORE INSERT触发器制造真实事务失败，现场核对plan0，模型看到SAVE_FAILED后解除单次故障，让其自行决定重试。

每例模拟业务Clock固定在该例实际启动时刻，用于精确边界；HTTP墙钟时间真实。6例初始状态使用实际检索/脚本/报价，不给模型预制assistant消息或“下一步选basic”指令。

实际共88次HTTP（planner73、脚本15），92次逻辑模型尝试（4次注入不访问HTTP）、95次动作、74份决策观察；主Trace376条，含后续阶段导出408条。

## 失败、修订与复测记录

- E07、E08各一次同时请求两个动作，被协议校验拒绝；模型收到反馈后改为单动作并完成预期。错误留在Trace，当前核心标准允许受控纠正。
- E16两次脚本失败后又请求第三次，触发重试上限拒绝，随后停止。状态诚实且有界，但多了一次无效动作。
- 首次完整离线测试407通过、1项强杀恢复出现CHECKPOINT_NOT_FOUND；针对性复测2/2、最新完整复测408/408均通过。最新执行状态为PASSED_ON_RETEST，首次[原JUnit](../examples/tests/core20/full-junit.xml)保留；未改业务代码，不声称已完成根因修复。
- 自然语言入口首轮有字段依据不匹配；收紧并示例化intake-v2抽取后，最终三例需求/业务通过。失败、诊断、修订后运行均保留，见[N3](stages/N3.md)。
- 历史[S7专项](stages/S7-evaluation.md)和N3严格内容评估未通过，包含未经素材支持的营销措辞。本轮用户确认以预算/状态/重规划为核心，营销扩写非否决项；旧结论不更名为成功，也不新增付费自评裁判。

## 复现与提交边界

安装、三类无密钥CLI和真实交互命令见[README](../README.md)。真实模型需显式启动并使用自己的密钥；不会为了重写文档再发付费请求。

仓库包含输入/输出/Trace/观察和事件/plan快照。runtime.db不提交；`python -m scripts.evaluate_core20 --recheck <run>`须有本地原库才可做物理库对齐。仅克隆仓库可执行`examples/tests/core20/audit_artifacts.py <run>`审计已提交产物，或跑离线测试创建新库。冻结源文件哈希只覆盖运行时列出的文件，不宣称覆盖后续文档改动。

已验证Windows/Python3.10.8；未测Linux、其他Python版本、同任务并发、长对话及所有故障组合。未验证任意主题的生成质量、完整自然对话、真实素材/视频制作/发布或生产级恢复。每例一个样本，不作统计稳定性或全局最优结论。
