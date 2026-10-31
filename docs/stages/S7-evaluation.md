# S7 题目专项效果评测报告

2026-10-31（UTC+08）。本报告针对用户授权的完整专项评测：预算10、初始12、替代8的真实重规划；无可行方案及缺口；一次失败后的自主处理与成功结果保留。它不代表S8可移植性收尾或用户已验收S7。

## 结论

**本轮三类真实场景的计算、依赖、持久化状态及目标决策均通过（各一个样本）；内容事实性三例均不通过，因此包含内容质量门槛的整体评测不通过。**

题目强调的“观察超预算后改选、重新估算并保存”已有真实模型证据，已超出仅展示串行调用的范围。失败样本中模型观察到工具错误后自主重试，成功的素材检索和候选被保留，原失败attempt仍为failed。无解样本正确停止、报告缺口且没有保存。

问题集中在脚本生成：模型增加了素材未提供的一键操作、生成速度、样式编辑及质量效果表述。当前程序的结构/来源/百分比/禁用语校验未拦截这些语义扩写。该问题如实保留，本轮没有修改提示词或事实校验来替换失败样本。

机器可读最终结论见[assessment.json](../../examples/live/budget-replan/20261031T090413Z-8bf82de2/assessment.json)。其中`technical_pass=true`、`content_pass=false`、`passed=false`；运行时原始summary中的technical_pass只表示技术/行为判定，不能作为整体通过。

## 范围、实现与来源

- 业务基线：`6885d85e6da9a6b4e8e4fe2af5b39ad6cb429711`，main单worktree。开始时已有上一回合的HANDOFF和评测计划文档改动，保留并续写；本轮未提交、fetch或推送。
- 评测实现：[evaluate_budget.py](../../scripts/evaluate_budget.py)，沿用实际本地工具、LangGraph、SQLite及DeepSeek适配器。新增安全的模型观察投影、L04给定状态接入、L05无解、L02严格恢复判定、独立预算/依赖/状态/时间检查。没有新增依赖或自动业务重规划分支。
- 用户要求本轮不用环境变量：先补[契约](../06-contracts.md#s7-http适配与效果验证实现前2026-10-31)，再为DeepSeek客户端增加可选内存`api_key`注入。密钥经隐藏终端输入传给临时进程，未放入命令参数、环境变量、源码或评测文件；两个真实运行进程均已结束。
- 官方模型`deepseek-v4-pro`；temperature=0、thinking关闭、非流式，planner max_tokens=2048、script=1536。资料为原有M01/M02合成资料及pricing-v1，原提示版本planner-v1/script-v1未变。
- 使用独立于历史S7案例库的`work/budget-evaluation.db`，每例新request_id，deadline为例开始时刻+4小时。失败首轮与获准联网后的运行共用该评测库，但请求ID不同，证据按run_id隔离；数据库本体不提交，逐例实际查询快照在evidence.json。

运行时Git子进程因safe.directory检查未取得commit/status，原metadata保留null。已修复今后运行的读取命令，并在[source-provenance.json](../../examples/live/budget-replan/20261031T090413Z-8bf82de2/source-provenance.json)事后补充会话实际核对的基线、运行时适配器/脚本SHA256及最终检查器SHA256。live运行后只修复检查器，随后用未改写的原始产物离线复判，未重复请求模型。

## 实际真实运行

首次[沙箱内运行](../../examples/live/budget-replan/20261031T090339Z-1bcb71ad/summary.json)返回连接不可用：三个案例均未完成，合计3次HTTP尝试；安全适配器未保留底层OS错误或provider body。该轮保留，未当作成功。获准联网后重新执行，三个案例在北京时间17:05:13—17:05:54完成，合计17次HTTP尝试。含隐藏输入等待的整个运行时间见原始summary。

两轮共20次HTTP尝试，不等同20次成功计费。未为了改善内容结果追加样本。

| 案例 | 实际输入/来源 | 观察到的轨迹 | 最终状态/plan行数 | 技术与行为 | 内容 |
|---|---|---|---|---|---|
| [L04](../../examples/live/budget-replan/20261031T090413Z-8bf82de2/L04/assessment.json) | budget10；初始premium12由显式setup建立 | 12且缺口2→真实模型修订basic→重新估算8→保存；revision1→2 | completed / 1 | 通过 | 不通过 |
| [L05](../../examples/live/budget-replan/20261031T090413Z-8bf82de2/L05/assessment.json) | budget5；普通完整live入口 | basic估算8、缺口3，premium替代12、缺口7→模型主动stop | incomplete / 0 | 通过；未完成为正确业务结果 | 不通过，未保存的草稿仍纳入核查 |
| [L02](../../examples/live/budget-replan/20261031T090413Z-8bf82de2/L02/assessment.json) | budget10；普通完整live入口；首次script在HTTP前注入一次可重试错误 | 检索成功→候选→脚本失败→模型观察并重试→生成成功→估算8→保存 | completed / 1 | 失败处理和恢复均通过 | 不通过 |

### L04：题目12→8的直接证据

request_id=`L04-50d7bf9467a0`。[Trace](../../examples/live/budget-replan/20261031T090413Z-8bf82de2/L04/trace.jsonl)和[evidence](../../examples/live/budget-replan/20261031T090413Z-8bf82de2/L04/evidence.json)可核对：

1. setup真实调用检索、修订premium、DeepSeek脚本生成和本地估算；这些动作明确origin=fixture_setup。事件22返回12、预算缺口2及basic8替代报价。
2. planner事件23接收的安全事实投影含预算10、当前报价12、缺口2及替代8。它没有预制assistant/tool历史，也没有“下一步选basic”的夹具指令。
3. 事件26是模型自主选择的修订，公开理由为“premium 档位超出预算 2 units，改用 basic 档位以符合预算。”
4. 事件30对revision2重新估算得到8，事件34保存成功。旧估算没有被当作新估算使用。
5. 全例检索实际执行1次、脚本模型实际请求1次；素材和brief未变，脚本沿用原指纹。换档位只使旧估算失效。最终数据库对应plan恰好1行。

**边界：这是题目给定初始12状态后的真实决策评测，不是模型从空白输入自主产生premium方案的完整路径。** 模型接手后的修订、再估算和保存都由真实模型选择；初始12来自真实工具，不是伪造报价。普通完整live路径由L02/L05及历史L01/L03另行覆盖。

### L05：无解及缺口

request_id=`L05-007d20dcbf46`。实际估算basic为`1+2+4+1=8`，预算5，缺口3；同一估算返回premium12，缺口7。模型停止信息明确列出四分项和3-unit缺口，原因`constraints_unsatisfied`；没有放宽预算。停止依据来自当前素材/报价范围，报告不据此证明任意资料中的全局无解。

估算工具为`ok=true, feasible=false`，因为它成功算出了不可行方案；stop_task成功执行，任务仍为incomplete。对应数据库plan0行、saved_plan=null，没有把工具成功误当任务完成。

### L02：一次失败及成功结果保留

request_id=`L02-7e3938bf0c96`。[Trace](../../examples/live/budget-replan/20261031T090413Z-8bf82de2/L02/trace.jsonl)事件60为成功检索、64为成功候选，70为首次生成failed/SCRIPT_MODEL_UNAVAILABLE。planner事件71的观察投影保留该失败；事件76生成成功，理由为“脚本模型暂时不可用，重试生成脚本”。事件80估算8，84保存成功。

原失败attempt与后续成功attempt分开保存，状态分别failed/succeeded；检索只执行1次，候选维持revision1，素材和候选指纹保留。脚本逻辑尝试2次，其中首次在HTTP前注入，真实脚本HTTP请求仅后一次。没有程序自动重试或预设最终决策。

## 预算、依赖与状态核验

独立检查器读取实际资料重算，不调用业务quote函数作为预期：premium=`1+2+8+1=12`、135分钟；basic=`1+2+4+1=8`、90分钟。核对报价分项、替代报价、预算/时限缺口及保存时重新报价。

按事件检查素材先检索再选择；脚本匹配当前候选；估算匹配revision、candidate_hash和script_id；修订后旧估算失效；保存引用最新可行估算。联合核对业务输出、事件终态及真实SQLite：两个completed各1行plan，L05为0行。未来四个制作步骤均planned，依赖依次衔接，首步开始于保存时刻，末步结束等于预计完成时间且满足deadline。

最终检查器对三例均返回`invariants_pass=true, behavior_pass=true`、errors为空；另以只读数据库查询核对导出的events/plans快照未变。3份output及72条Trace全部符合当前JSON Schema。原始`output.json/trace.jsonl/evidence.json/run.json/verdict.json`未被最终判定覆盖，补充结论另写assessment.json。

## 内容事实性：实际未通过项

三例选中的M01只有两条允许事实：“影芽剪辑支持自动生成字幕”“自动生成的字幕文本可以编辑”。由当前评测代理逐条对照源事实做语义审核，没有额外调用评分模型，尚无用户或独立人工评审复核；详细原文位置、依据及判断保存在各例content-review.json。以下列出足以判定不通过的实例，不声称穷尽全部语言问题。

| 案例 | 脚本原文 | 缺失依据 |
|---|---|---|
| L04 | “自动生成字幕只需一键”；“准确又专业” | 操作步骤/次数、准确性和质量保证未由素材提供 |
| L05 | “瞬间完成”；“调样式” | 生成速度、样式编辑能力未由素材提供 |
| L02 | “几秒钟字幕就出来了”；“调样式” | 明确耗时、样式编辑能力未由素材提供 |

这属于“当前素材不支持这些断言”，不据此断定现实产品一定不具备相应能力。来源ID正确和JSON合法不能使这些新增断言获得依据。L04的草稿由setup阶段真实模型生成并被后续复用；重规划决策通过，不使该草稿内容自动合格。

## 运行指标

| 案例 | 逻辑模型尝试 | 动作尝试 | 实际HTTP尝试 | input/output tokens |
|---|---:|---:|---:|---|
| L04 | 4 | 7（含4个setup动作） | 4（含setup脚本） | 9948 / 543 |
| L05 | 6 | 5 | 6 | 14916 / 998 |
| L02 | 8 | 6 | 7 | null / null |

L02有一次HTTP前注入的失败逻辑尝试，其用量未知，按现行保守汇总规则总token为null；不能把已知请求用量之和冒充完整总量。所有API美元费用为null；业务8/12 units是模拟活动报价。

## 离线验证与评测器审查

先对评测预期、密钥注入例外补规格，再逐行为测试和实现。聚焦命令为`python -m pytest -q tests/unit/test_evaluation.py tests/unit/test_deepseek.py`，最终聚焦54项通过。评测器测试13项，适配器新增显式内存密钥测试1项；既有基线328项。

实际Red/Green关键记录：

| 行为 | 实际Red | Green |
|---|---|---|
| 入口/独立报价/失败评测搭建 | 缺模块/函数；仅作搭建证据 | 已有12报价通过；自洽但错误的8报价被拒绝；失败观察进入下一决策 |
| L04给定状态接入 | 未seed时behavior=false | 真实工具setup后12→8、一次脚本请求、无虚构历史 |
| 错误证据与无解判定 | 旧估算、篡改观察未拒绝；L05错误按completed要求判失败（3 failed/6 passed） | 9 passed；五类破坏被拒绝，正确incomplete可通过 |
| 显式付费开关 | 脚本无main时零参数退出0，预期2失败 | 缺--live/--key-stdin拒绝且零产物/请求 |
| 内存密钥 | 完善测试导入后，构造器TypeError | 不依赖环境密钥即可构造；HTTP协议回归通过 |
| 审查发现的失败语义缺口 | 失败事件和步骤双方误标成功，检查器仍通过 | 新反例通过，错误结果与succeeded不一致被拒绝 |
| 审查发现的时间锚点缺口 | 整条制作时间轴后移一天仍通过 | 新反例通过，plan_time_anchors拒绝 |
| 非法证据丢报告 | 缺events抛KeyError | 返回明确失败verdict；先保存原始evidence |

第一次全量在检查器最后三项修复前为339 passed/148.76秒，仅作为中间回归。最终全量为**342 passed、0 failed、0 errors、0 skipped，146.97秒**，命令退出0；[最终JUnit](../../examples/tests/budget-evaluation/pytest-junit.xml)和[汇总](../../examples/tests/budget-evaluation/summary.json)保留实际结果。`pip check`已通过。普通pytest保持网络禁用；离线Fake/MockTransport不当作真实效果。

### Standards

按code-review技能，以6885d85为基线检查three-dot diff（无新commit）、working/cached diff及未跟踪评测脚本/测试；独立代理初审及增量复核硬违反0、Fowler判断项0。规则来源AGENTS、阶段计划、技能约定与karpathy-guidelines。

### Spec

另一独立代理初审2项P2：失败终态缺少ok/error语义一致性、制作时间轴缺少保存/截止锚点。均通过上述真实Red/Green修复。代理再次用三个真实evidence离线复判均通过；对两类错误再次做内存破坏均被拒绝。最终未解决的检查器审查项0。

审查对象是本轮实现和判定器；“未解决审查项0”不代表实际模型脚本的内容缺口已修复。内容问题保持不通过，列为下一步业务改进对象。

交付前`git diff --check`、变更文档本地链接路径检查及仓库文本密钥模式检查通过。独立Spec代理另核对报告、HANDOFF、最终assessment与JUnit一致；无新增结论或证据问题。未重建wheel或执行Linux验证。

## 复现与限制

PowerShell（使用已有公开依赖环境）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml=examples/tests/budget-evaluation/pytest-junit.xml
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_budget.py --live --key-stdin
```

POSIX对应命令（本轮未在Linux实测）：

```sh
.venv/bin/python -m pytest -q --junitxml=examples/tests/budget-evaluation/pytest-junit.xml
.venv/bin/python scripts/evaluate_budget.py --live --key-stdin
```

第二条会在隐藏终端读取密钥并发起真实付费请求，生成新run_id和request_id；不能保证模型决策/措辞重复。默认输出`examples/live/budget-replan/<run_id>/`，数据库`work/budget-evaluation.db`；程序初始verdict将内容标为PENDING，需对实际草稿另做源事实审核，不能把退出0解释成内容通过。可用`evaluate_evidence(case, bundle)`离线复核已保存evidence，无需密钥或网络。

本轮每例只有1个新样本；结果说明这三个给定条件下的观察，不提供稳定性或泛化成功率。首次连接失败单列，不被成功样本覆盖。可选L06同任务重规划+保存故障组合、3次重复、Linux/其他Python和S8最终归档仍NOT_RUN。本报告完成题目专项的首批全部必需案例及完整离线回归，不宣称全部平台和A01—A23均已用户验收。

实际使用karpathy-guidelines、tdd及tests/mocking、codebase-design（评测接口复用与独立判定位置）、code-review双轴、writing-for-agents/handoff。未把公开技能当作运行依赖。下一步优先处理脚本事实性与相应回归，再另行验证效果；本轮评测不会自动修复或覆盖该失败。
