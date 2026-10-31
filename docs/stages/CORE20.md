# 20场景核心Agent实际评测报告

2026-10-31（UTC+08）。本次评测与自验完成，ready_for_review，用户验收pending；未开始S8、自然对话重构或事实审核模块。

## 结论

**按用户确认的原题核心标准，20/20场景通过。** 预算/耗时计算、步骤依赖、实际持久状态与完整Trace一致；超限后改选、无解停止、一次故障恢复、保留成功结果和显式续跑均有真实证据。这是20个固定场景各一个样本的结果，不能推断模型在任意输入下都稳定通过。

最终[独立判定](../../examples/live/core20/20261031T110356Z-93ca1d21/final-assessment.json)、[运行汇总](../../examples/live/core20/20261031T110356Z-93ca1d21/summary.json)、[完整案例配置](../../examples/evaluation/core20-cases.json)。本轮营销文案扩写不作否决项，未新增内容裁判；历史严格内容失败报告保留。

**最终完整离线复测已通过：408 passed、0 failed，155.10秒。** 原先出现CHECKPOINT_NOT_FOUND的强杀进程恢复测试，针对性复测和本次完整复测均已通过。当前结论为：20场景核心评测通过、408项离线测试通过。首次异常仅作为历史记录保留，详见下文复测记录；未改业务代码，不声称已经实施根因修复。

## 执行范围与指标

真实模型为官方DeepSeek HTTP API的deepseek-v4-pro，temperature=0、thinking关闭，planner/script提示版本仍为planner-v1/script-v1。先冻结[规格](../12-core20-evaluation.md)和20例预期，再开发独立检查器；运行中未修改业务代码、提示或断言，也未自动重跑失败案例。

运行ID：`20261031T110356Z-93ca1d21`，UTC 11:03:56至11:07:50。16例真实模型场景、4例零调用输入防护；其中6例（E03—E06/E08/E10）明确给定初始premium方案，夹具真实执行检索、脚本与估算并标记fixture_setup，之后由真实模型选择下一动作。其余从结构化service入口空白运行，另执行resume/重复/冲突请求。**本轮属于业务Agent集成端到端评测，不是20例自然语言终端端到端评测。** 自然语言入口的历史证据见[N3](N3.md)。

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

## 20个场景的实际结果

下表ID链接到各例完整Trace；同目录的output.json、plan.md、observations.json、evidence.json、assessment.json/final-assessment.json分别保存结果、方案、模型收到的观察、持久事件快照与独立判定。费用列中的未完成报价不是已保存费用。

| Case / 完整Trace | 场景 | 实际状态与费用/缺口 | plan行数 | HTTP | 结论 |
|---|---|---|---:|---:|---|
| [E01](../../examples/live/core20/20261031T110356Z-93ca1d21/E01/trace.jsonl) | 字幕推广，预算10 | completed，8 | 1 | 6 | 通过 |
| [E02](../../examples/live/core20/20261031T110356Z-93ca1d21/E02/trace.jsonl) | 裁剪拼接M02，预算8 | completed，M02、8 | 1 | 6 | 通过 |
| [E03](../../examples/live/core20/20261031T110356Z-93ca1d21/E03/trace.jsonl) | 初始12，预算恰好12 | completed，保留premium12 | 1 | 2 | 通过 |
| [E04](../../examples/live/core20/20261031T110356Z-93ca1d21/E04/trace.jsonl) | 参考实例：预算10、初始12 | 观察缺口2→改8→重估→completed | 1 | 4 | 通过 |
| [E05](../../examples/live/core20/20261031T110356Z-93ca1d21/E05/trace.jsonl) | 预算8、初始12 | 观察缺口4→改8→重估→completed | 1 | 4 | 通过 |
| [E06](../../examples/live/core20/20261031T110356Z-93ca1d21/E06/trace.jsonl) | 预算7、初始12 | 改8仍不可行，incomplete、缺口1 | 0 | 5 | 通过 |
| [E07](../../examples/live/core20/20261031T110356Z-93ca1d21/E07/trace.jsonl) | 预算5，从空白开始 | incomplete，最低8、缺口3 | 0 | 7 | 通过 |
| [E08](../../examples/live/core20/20261031T110356Z-93ca1d21/E08/trace.jsonl) | premium135分钟超期限120分钟 | 观察超15分钟→basic90→重估→completed，8 | 1 | 6 | 通过 |
| [E09](../../examples/live/core20/20261031T110356Z-93ca1d21/E09/trace.jsonl) | 期限60分钟 | incomplete，最低90分钟、缺口30分钟 | 0 | 6 | 通过 |
| [E10](../../examples/live/core20/20261031T110356Z-93ca1d21/E10/trace.jsonl) | 期限恰好90分钟，初始135 | 改basic90，预计结束=deadline，completed、8 | 1 | 4 | 通过 |
| [E11](../../examples/live/core20/20261031T110356Z-93ca1d21/E11/trace.jsonl) | 缺预算 | needs_input/NEEDS_INPUT，缺budget_units | 0 | 0 | 通过 |
| [E12](../../examples/live/core20/20261031T110356Z-93ca1d21/E12/trace.jsonl) | 缺截止时间 | needs_input/NEEDS_INPUT，缺deadline_at | 0 | 0 | 通过 |
| [E13](../../examples/live/core20/20261031T110356Z-93ca1d21/E13/trace.jsonl) | 两项均缺 | needs_input，准确列两项、无业务库 | 0 | 0 | 通过 |
| [E14](../../examples/live/core20/20261031T110356Z-93ca1d21/E14/trace.jsonl) | 截止时间已过 | needs_input/INVALID_ARGUMENT、无业务库 | 0 | 0 | 通过 |
| [E15](../../examples/live/core20/20261031T110356Z-93ca1d21/E15/trace.jsonl) | 首次脚本失败 | 观察错误后重试成功，completed、8，原failed保留 | 1 | 7 | 通过 |
| [E16](../../examples/live/core20/20261031T110356Z-93ca1d21/E16/trace.jsonl) | 脚本持续失败 | 两次失败、第三次被限额拒绝；incomplete/tool_failure | 0 | 6 | 通过 |
| [E17](../../examples/live/core20/20261031T110356Z-93ca1d21/E17/trace.jsonl) | 首次保存事务失败 | 回滚plan0；观察SAVE_FAILED→再保存completed、8 | 1 | 7 | 通过 |
| [E18](../../examples/live/core20/20261031T110356Z-93ca1d21/E18/trace.jsonl) | 部分成功后planner中断、显式resume | 初次incomplete；续跑completed、8，前缀保留 | 1 | 6 | 通过 |
| [E19](../../examples/live/core20/20261031T110356Z-93ca1d21/E19/trace.jsonl) | 完成后相同输入再次run | 同一completed、8；额外HTTP0，数据库不变 | 1 | 6 | 通过 |
| [E20](../../examples/live/core20/20261031T110356Z-93ca1d21/E20/trace.jsonl) | 同ID将预算改5 | 后续needs_input/REQUEST_CONFLICT；原completed、8不变 | 1 | 6 | 通过 |

## 关键Trace核验

**E04合理重规划。** 夹具估算在event10持久化12、预算缺口2及basic8替代报价；event11的真实模型输入确实包含这些数据，公开动作理由为“当前premium档位超出预算2 units，改用basic”。event13—14修订到revision2；event15下一次观察的latest_estimate已清空，旧报价仍在历史中；event17—18重新估算8，event21—22保存同一revision2及新estimate_id。素材M01和同一script_id保留，没有重做检索/脚本。见[E04观察与动作](../../examples/live/core20/20261031T110356Z-93ca1d21/E04/observations.json)。这能证明模型依据反馈改变方案，单纯最终8或顺序调用不足以证明这一点。

**E15单次脚本失败。** event11开始的generate_script最终event14为failed，错误SCRIPT_MODEL_UNAVAILABLE；event15模型收到ok=false和可重试错误，明确选择重试。event17开始的新尝试成功，再估算/保存；成功检索和候选各只执行一次，失败attempt未覆盖成成功。故障在HTTP前注入，仅第二次脚本调用访问真实API。

**E17实际事务失败。** 评测专属库的BEFORE INSERT触发器使event22产生SAVE_FAILED，故障日志现场核对plan行数0，证明回滚；event23模型确实看到该错误后决定重试。event25—26成功保存，最终仅1份plan；检索、脚本、估算各一次，首个save仍failed。见[故障日志](../../examples/live/core20/20261031T110356Z-93ca1d21/E17/fault-log.json)。没有Mock成功保存函数或伪造失败结果。

**E16有界停止。** 两个实际逻辑脚本尝试均failed；模型又申请第三次，被TOOL_RETRY_LIMIT_REACHED拒绝，收到该观察后stop_task成功，任务状态仍incomplete/tool_failure。成功的是“停止动作”，不是失败脚本或整个任务；plan0，素材/候选历史仍在。它符合有界失败处理，但比主动识别剩余额度多一次无效动作。

**E18显式续跑。** 初次10条事件、检索和候选均成功，planner在HTTP前失败；初次结果incomplete/MODEL_UNAVAILABLE、plan0。resume后原10条事件完整保留，不重搜素材，累计模型尝试3→7、剩余额度25，最终8保存。该例为可重试模型异常后的service恢复，不能代替断电/强杀恢复可靠性测试。见[分阶段证据](../../examples/live/core20/20261031T110356Z-93ca1d21/E18/followup.json)。

E06/E07/E09的最终message分别准确说明预算缺口1、3及期限缺口30分钟。E19/E20的后续请求前后数据库Request/events/plans完全相同，额外HTTP均为0；E20拒绝的是修改请求，原任务仍完成。

## 实际检查方法

费用与时间直接读取合成资料逐行独立相加，同时验证当前及替代报价、feasible、预计结束、预算/期限缺口；不调用业务quote函数生成预期。逐个持久动作核对检索→候选→匹配脚本→当前版本估算→保存，修订后旧估算不能用于保存。

每次planner调用前记录安全事实投影，从该时点之前的SQLite状态补丁独立重建候选、素材、脚本、历史报价、当前估算与最近工具观察，并与模型收到的数据核对。失败保存事件没有state_patch时，以实际ToolResult事件补足最近观察，避免检查器误报。每项成功产物历史必须单调保留。

输出execution_steps必须完整、有序对应所有持久工具/控制尝试，终态与错误码逐项相同；tool_results、保存payload和实际plan互相核对。Trace核对Schema、事件ID/operation/phase、来源、参数、动作理由、报价摘要、result_ref、next_decision以及任务状态。另从物理output/trace文件和只读SQLite重读比对，未仅信任评测器内存快照。

实际[额外产物审计](../../examples/tests/core20/artifact-audit.json)通过：23份输出、408条Trace合法，参数/理由/报价摘要/工具结果集合一致；21个运行时冻结文件哈希未变化，资料快照与公开资料一致，文本密钥模式零命中。原始summary/assessment不重写，后验结论另存final-assessment。

## 问题、限制与工程验证

E07 event11、E08 event17各有一次非注入MODEL_PROTOCOL_ERROR：模型同时请求脚本生成和估算，违反每轮单动作协议，程序拒绝，两例随后均根据反馈改为单动作并完成各自正确终态。错误事件原样保留。本轮允许受控协议纠正，因此核心案例通过；不能写成全程无模型错误。

新评测器相关测试32 passed、9.84秒，见[target-junit](../../examples/tests/core20/target-junit.xml)。包含篡改费用/状态/观察、遗漏步骤、数据库输入不符、抹除成功结果、坏Trace文件、故障/重复/续跑及付费入口保护等实际反例，已验证会变红。

**最新完整复测：** `python -X utf8 -m pytest -q --junitxml=examples/tests/core20/final-full-junit.xml`实际**408 passed、0 failed，155.10秒**，见[最终全量JUnit](../../examples/tests/core20/final-full-junit.xml)及[复测汇总](../../examples/tests/core20/final-verification.json)。本次没有业务代码修改、没有付费HTTP调用；原失败项在完整复测中通过。

历史记录：首次全量命令输出407 passed、1 failed，159.50秒，原[首次全量JUnit](../../examples/tests/core20/full-junit.xml)保留。异常用例为`test_unknown_external_result_is_interrupted_and_new_attempt_consumes_quota[unknown_planner]`：模拟强杀进程后resume返回CHECKPOINT_NOT_FOUND，失败库有1条planner started、1条checkpoint、writes0、plan0。随后针对`-k unknown_external`复测2 passed/26 deselected、7.44秒，再完成上述408项完整复测。原[诊断记录](../../examples/tests/core20/resume-diagnostic.json)中的OPEN是当时状态，最新执行状态以复测汇总的PASSED_ON_RETEST为准；根因仍未确认，不把复测通过表述为代码修复。

每例仅一个样本；未测并发、Linux、长对话、真实素材检索、真实视频制作、外部发布、完整自然对话修改体验或任意故障组合。没有测模型自动生成所有初始premium方案，6例夹具明确标识。API真实超时/限流未主动制造，外部模型失败在公开适配边界注入。未重新做干净安装/平台验证；本轮仅新增评测工具，依赖锁和应用行为不变。

## Standards

固定基线main/6885d85e6da9a6b4e8e4fe2af5b39ad6cb429711，单worktree；已检查`git diff <baseline>...HEAD`、工作区/暂存diff及未跟踪评测文件，不能把空提交diff解释为无变更。Standards审查项目规则和12项smell baseline，硬性违反0、判断项0；没有为了评测增加应用依赖或硬编码开发机路径。

## Spec

首审发现3项P2假通过：可删掉全部执行步骤、可改DB预算、可清空模型成功结果投影。均先通过变造证据实际复现Red（3 failed），再最小补齐独立核验，聚焦测试Green，Spec复核未解决0。另修正检查器对无状态补丁SAVE_FAILED事件的最近观察重建，不改应用逻辑。两轴结论分别保留，不用离线测试替代模型效果。

实际使用karpathy-guidelines、tdd（含tests/mocking）、code-review双轴；diagnosing-bugs用于保存观察误报和回归失败诊断；writing-for-agents/handoff用于交付。所有实际结果与先行预期分开。

交付自验：git diff --check退出0，6份当前Markdown中的91个本地链接零断链，新增评测源文件与产物的密钥模式检查零命中，见[交付检查](../../examples/tests/core20/delivery-checks.json)。实施双轴审查及三项修复复核已经完成；额外的最终文档子代理复核因额度限制NOT_RUN，最终文档与证据对齐由主代理完成，不将其记为另一次独立审查。

## 复现与下一步

仅复核已存在证据，零HTTP：

```powershell
.venv/Scripts/python.exe -X utf8 -m scripts.evaluate_core20 --recheck examples/live/core20/20261031T110356Z-93ca1d21
.venv/Scripts/python.exe -X utf8 examples/tests/core20/audit_artifacts.py examples/live/core20/20261031T110356Z-93ca1d21
```

POSIX将`.venv/Scripts/python.exe`换成`.venv/bin/python`；Linux未测。完整SQLite本机保留但被.gitignore排除；evidence.json包含可读事件/plan快照，迁移后单独核验快照可用，`--recheck`与物理库对齐须一并带上各例runtime.db。

显式新增付费样本才运行`python -m scripts.evaluate_core20 --live --key-stdin`，通过隐藏终端输入密钥，仅留内存；不写env/argv/源码/日志，不自动重试整例。当前进程已退出，不追加调用。

Git未commit/fetch/push，相对已知本地origin/main仍ahead8，最新远端同步未知；原有未提交修改保留。下一步为用户审阅本报告。强杀恢复测试当前复测通过，首次偶发异常留档；如再次出现，再建立确定性复现并定位原因。本次没有重跑20例或追加付费样本。
