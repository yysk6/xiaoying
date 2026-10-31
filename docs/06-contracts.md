# 输入、工具与输出契约

本文件给出语义；精确字段见 `contracts/*.schema.json`。除明确开放的诊断details和Trace原始args外，所有对象禁止未声明字段。所有字符串做 NFC 规范化、首尾去空白；ID 大小写敏感；JSON boolean 不能当作整数。用户内容只是数据，不能更改工具白名单、预算或提示中的系统约束。

## CLI

S6实现前约定：run/show保持既有语义，本阶段开放显式resume；deepseek后端留S7，选择时明确配置错误，不降级Mock。S5历史范围见阶段报告。

```text
python -m content_planner run --input <request.json> --backend mock|deepseek --db <runtime.db> --output-dir <directory>
python -m content_planner show --request-id <ID> --db <runtime.db> --output-dir <directory>
python -m content_planner resume --request-id <ID> --db <runtime.db> --output-dir <directory>
```

`run` 默认 backend=mock、db=`work/runtime.db`、output-dir=`work/runs/<request_id>`；业务资料通过包资源 `content_planner/data/` 读取。`resume` 使用原任务 backend 和配置，不允许借续跑变更模型/资料/预算。`show` 不调用模型或业务工具。live 模式缺少模型环境变量时明确报配置错误，不退回 Mock。

S6的Mock续跑可加`--mock-scenario <后续响应.json>`，格式沿用下节；未完成任务需要显式后续响应，不能让默认演示从头重播。拒绝恢复返回incomplete/退出3及MANIFEST_MISMATCH、CHECKPOINT_NOT_FOUND、RESUME_NOT_ALLOWED或原限额原因，原持久状态不变；缺任务仍为REQUEST_NOT_FOUND/退出2。细节与公开注入入口见[恢复规格](07-state-and-storage.md#s6接通细化实现前2026-10-31)。

### S5离线入口细化（实现前，2026-10-31）

`run --mock-scenario <scenario.json>`可提供显式Fake输入；省略时读取包内mock-scenario.json（固定M01/basic动作示例，不随主题/预算选择答案）。场景对象仅允许decisions、responses、now：前两项为显式planner响应对象/脚本JSON字符串列表，故障项为`{"error":"MODEL_UNAVAILABLE"}`；now可省略，或为带偏移时间，以固定Clock演示。场景不是用户业务输入，不进入request指纹；重复run先比较输入并读取原任务，不重新读取场景或当前资料。未提供now时使用SystemClock，不自动延长用户期限。所有Mock输出明确backend/model=mock，不作为智能效果证据。

公开验收入口为CLI子进程与`service.run_task(raw_input, database=..., model=..., clock=...)`、`service.show_task(request_id, database=...)`。model/clock只作为已有外部依赖的注入点。缺失/非法输入先形成needs_input结果，不初始化数据库；缺失字段顺序沿用Request。已有ID输入冲突返回REQUEST_CONFLICT/退出2，不输出原方案冒充本次请求成功。show与重复run只读取原记录、checkpoint、事件和提交方案；无checkpoint时以已持久状态补丁和提交事实构造视图，不调用模型、工具，不写新的业务事件。S5不把未结束started标成成功或恢复执行。

导出文件固定为output.json、plan.md、trace.jsonl；未完成plan.md明确未保存，保留候选和估算缺口。needs_input无持久事件，trace_path=null，trace.jsonl为空（不编造请求事件）。TaskResult数值取最新有效估算，completed优先使用已提交方案。execution_steps从tool/control的started派生，每次尝试一项；attempt按逻辑键累计（无键时按工具名），status取同operation最后结束事件，未结束保持started；result_index引用tool_results原结果。协议拒绝有ToolResult但未执行动作时不计attempt。

Trace逐行符合trace-event.schema.json，额外显式backend/model；origin=模型选择的动作/协议拒绝时为model，系统模型请求/生命周期为system，明确夹具来源才为fixture_setup。next_decision_event_id指向本事件之后首个planner started事件，无则null。参数只导出公开动作参数（剥去内部logical_key），不导出完整planner响应、状态补丁或模型推理。摘要仅含动作状态、错误码及费用/约束等必要观察；result_ref用`tool_results:<index>`引用原结果。未知token/美元账单为null；业务费用不作为API账单。

operation_id由最长200字符的tool_call_id加`tool:`及`:script`等内部前后缀形成；Trace/ExecutionStep将其上限细化为256，保留原调用ID，不截断或重写模型提供的ID。

导出失败仍在stdout输出可信TaskResult，trace_path=null、warnings含EXPORT_FAILED，同时stderr告警；状态和退出码按业务事实，已提交方案不回滚。show可选新目录重导出。无可信存储结果时仅stderr进程错误、退出1；参数/文件/配置错误可形成needs_input JSON、退出2。帮助输出沿用argparse约定。

退出码：0=completed；2=needs_input/输入或配置错误/请求冲突；3=incomplete；1=不能构造可信结果的进程/存储故障。`show` 的退出码反映所查任务状态。错误和进度写 stderr，stdout 只写最终 JSON；CLI两流及导出文件统一UTF-8，不依赖用户设置Python编码变量。输出目录创建失败不回滚已提交方案，输出 `EXPORT_FAILED` 警告并允许重新 show。

## 用户输入

| 字段 | 类型/限制 | 含义 |
|---|---|---|
| request_id | string，1—64，`[A-Za-z0-9_-]+` | 用户提供，重复执行的业务键 |
| topic | string，1—200；可缺失/null | 内容活动主题；缺失时 needs_input |
| budget_units | strict integer，1—100000；可缺失/null | 模拟方案预算；禁止 float/string/bool |
| deadline_at | string，带偏移的 ISO 8601；可缺失/null | 硬性活动截止时间，必须晚于实际当前时间 |

只允许这四个用户字段。受众/平台按需求文档的固定默认值进入标准化请求；首版不扩展交互式修改需求。缺失或格式非法的请求不创建持久任务，不消耗 request_id；补齐后可使用原 ID 重新 run。已有任务的重复 run 先比较标准化业务输入，返回已保存事实，不因为现在已过截止时间把历史成功改成失败。

输入示例只说明格式，不是执行记录：

```json
{"request_id":"demo-budget-01","topic":"影芽剪辑字幕功能推广","budget_units":10,"deadline_at":"2026-10-30T18:00:00+08:00"}
```

环境变量：`DEEPSEEK_API_KEY`（仅 live 必需）、`DEEPSEEK_BASE_URL=https://api.deepseek.com`、`DEEPSEEK_MODEL=deepseek-v4-pro`。首版运行仅支持官方 host 与此模型 ID；其他值报配置错误，不暗示兼容任意代理。`.env.example` 只有占位符；环境变量由 shell 设置，本程序首版不自动加载 `.env` 文件。

## S1 领域接口细化（2026-10-29，先于实现）

S1只实现`Request`、`ScriptDraft`与纯领域函数，不提前实现六动作分派、完整TaskResult或数据库。`Request`与request.schema.json一致：request_id必填，三个业务字段可缺失/null；格式错误由Pydantic ValidationError按字段报告。`missing_fields`按topic、budget_units、deadline_at顺序列出缺失/null字段；空白字符串规范化后为空，属于格式错误，不当成缺失。

`require_complete(request, clock)`先检查缺失（NEEDS_INPUT，details.missing_fields），再检查deadline严格晚于clock.now()（INVALID_ARGUMENT，details.field=deadline_at）。结构解析不读取系统时间；后续重复run可先比对指纹再决定是否检查新请求期限。Clock.now()约定返回有时区datetime，SystemClock返回UTC。内部纯函数接收结构合法、字段完整的Request和已经读取的合成数据，不反复验证可信参数，不做通用异常兜底。

`quote(request, material, pricing, production_mode, clock)`只计算调用方指定档位，不替模型选择。返回固定四项line_items、quoted_at、total_units、total_minutes、estimated_finish_at、within_budget、within_deadline、feasible及两个缺口；时间均为UTC ISO字符串，每次调用重新读取Clock。catalog_item_id依次为素材ID、script_finalize、video_edit:<档位>、review。S2再封装工具ID、alternatives、资料读取/校验和工具错误；S1不访问文件、网络或业务数据库。

`ScriptDraft`只接收title/hook/body/cta/source_ids；脚本ID与指纹是后续工具从可信状态补充的派生字段，模型不能提交。`parse_script(raw_json, material)`将JSON/结构错误统一映射为SCRIPT_INVALID，再执行来源与事实规则，不自动修复。百分比按完整数字token比较，不能因80%是180%的子串就视为有依据；允许小数和数字与%之间的空白。固定禁用语按去空白后的单字段文本检查。事实校验版本基线为script-v1；此处细化匹配方式，不扩展到任意自然语言事实证明。

## 所有动作的共同规则

### S2本地入口与验收细化（实现前）

S2的公开测试入口为`load_catalog(directory=None)`、`Catalog.search(query, top_k)`和`LocalTools`的search_materials/revise_plan/generate_script/estimate_cost四个方法。每个方法接收调用方提供的唯一tool_call_id及arguments字典，严格校验模型参数，返回现行ToolResult；调用方负责选择动作，不存在自动执行下一步。save_plan归S3，stop_task及自主循环归S4，不创建空实现。

合成数据以原始fixture字节复制到`content_planner/data/`并随wheel/sdist打包，默认通过importlib.resources读取，与cwd无关；显式directory只替换资料位置。原始文件SHA-256进入manifest。加载时校验严格类型、非负报价/分钟、结构和唯一素材ID；材料/别名读取或格式错误为CATALOG_UNAVAILABLE，报价不可读为ESTIMATOR_UNAVAILABLE、内容非法为PRICING_INVALID。加载结果是本任务的已验证资料快照，工具不在每次调用重复读取；跨资料快照恢复的manifest核对属于S6。

LocalTools持有单请求的本地工具状态，snapshot()只返回JSON兼容副本，包含请求、manifest、候选与产物历史、当前引用及工具结果。每次拒绝/失败也保留ToolResult，但不替模型重试；失败不创建脚本或估算成功产物，已有有效结果保留。S2不写数据库、事件表、checkpoint或业务执行Trace，不提前实现累计动作/模型额度；最多4个候选版本的本地规则在本阶段守住。

ModelClient在S2只定义model_id和generate_script(context)->JSON字符串的外部边界，后续再添加planner决策能力。生成上下文仅含主题、素材ID/事实、brief、固定受众/平台与ScriptDraft输出Schema；FakeModelClient使用显式响应/故障列表，耗尽或ModelUnavailable映射为SCRIPT_MODEL_UNAVAILABLE，不内置自动重试。脚本ID与哈希由程序补充，不接受模型提交。

估算时Clock只读一次，当前档位与另一档位使用同一时刻计算，避免alternatives比较混入时间差；估算ID为`estimate_`加tool_call_id的完整SHA-256。只有当前候选的匹配脚本才能估算；每次显式估算产生新引用。实质修订清除current_estimate_id，invalidated只列实际失效的当前产物类型，历史不删除。保存时拒绝旧estimate的端到端断言留S3，不能因S2观察到失效就记为保存链路通过。

模型每次选择恰好一个动作。四个业务工具为 `search_materials`、`generate_script`、`estimate_cost`、`save_plan`；两个控制动作为 `revise_plan`、`stop_task`。六者均以函数工具 schema 暴露，只有前四个计为题目业务工具。

每个动作都要求 `rationale`：1—200 字符，公开的一句话决策依据，例“当前估算超过预算，改用基础剪辑后重新估算”。该字段不进入内容指纹，不要求或接收长篇内部推理。

统一返回 `ToolResult`：

| 字段 | 类型 | 规则 |
|---|---|---|
| tool_call_id | string | 回应真实模型提供的调用 ID，Mock 也提供唯一 ID |
| tool | 六个固定名称之一 | 不允许动态导入函数 |
| ok | boolean | 执行是否成功；不表示候选是否满足预算 |
| reused | boolean | 是否返回已存在、仍有效的成功结果 |
| data | object/null | 成功时按工具结果 schema；失败时 null |
| error | object/null | 失败时含 code、message、retryable、details；成功时 null |

`error.retryable=true` 的唯一含义是“相同业务参数可以尝试重执行”；不表示自动重试。估算正常完成但超预算为 `ok=true`、`feasible=false`，不能当作工具宕机。

## T01：search_materials

输入：`query`（1—200 字符）、`top_k`（strict integer，1—5）、`rationale`。

输出 data：`query`、`catalog_hash`、`materials[]`。每项为 `material_id`、`version`、`title`、`tags[]`、`facts[]`、`fee_units`、`lead_minutes`、`score`。最多 top_k 项；0 项也是成功。

检索定义：对查询做 NFC/lower/trim，按 `aliases.json` 将别名替换为规范词（长别名优先、相同长度按字典序）；对每条素材，统计出现在查询中的不同 tags 数量作为 score；score>0 才命中；按 score 降序、material_id 升序排序。首版不用 embedding/BM25，不宣称泛化检索质量。

成功命中的素材 ID 加入当前任务 `seen_material_ids`。补充检索是累加，不抹掉此前命中项。故障：`CATALOG_UNAVAILABLE` 可重试；非法参数为 `INVALID_ARGUMENT` 不可按原参数重试。

## C01：revise_plan

输入：`material_id`（已在本任务成功检索到）、`creative_brief`（1—500 字符）、`production_mode`（basic/premium）、`rationale`。

行为：首次建立候选；后续改变素材、brief 或档位建立新 revision。相同当前候选重复提交返回原 revision，`reused=true`。topic、budget、deadline 不可修改；档位只有合成表中两个值。

输出 data：`revision`、`candidate_hash`、上述三个候选字段、`script_input_hash`、`script_reused`、`invalidated[]`。candidate_hash 包含标准化请求、素材内容哈希、brief、档位、报价版本；不包含 rationale 和时间戳。

模式变化保留同一素材/brief 的脚本；素材或 brief 变化使当前脚本失效；任何实质候选变化使当前估算失效。历史结果仍保留。超过 4 个不同版本终止为 `REVISION_LIMIT_REACHED`，不创建第 5 版。

错误：未见素材 `MATERIAL_NOT_OBSERVED`、未知素材 `MATERIAL_NOT_FOUND`、参数非法。它是控制动作，不自动生成脚本或估算。

## T02：generate_script

输入：`plan_revision`（当前版本）、`rationale`。素材和 brief 从可信候选读取，不允许模型在调用时偷换。

前置：已有候选、对应素材仍存在且内容哈希与任务 manifest 一致。无候选或旧版本返回 `PRECONDITION_FAILED`/`STALE_REVISION`。

行为：若存在匹配 script_input_hash 的成功草稿，直接复用；否则使用同一 ModelClient 生成一次 JSON 草稿。script_input_hash 由请求主题、素材内容、brief、固定受众/平台、脚本提示版本、模型 ID 与 thinking 配置生成；**不包含制作档位**。

输出 data：`script_id`、`script_input_hash`、`title`（1—100）、`hook`（1—200）、`body`（1—2000）、`cta`（1—200）、`source_ids`（恰好包含当前一个素材 ID）。script_id 为 `script_` + script_input_hash 的完整 SHA-256 hex。

模型原始 JSON 非法、缺字段、错误来源或命中明确禁用表述时为 `SCRIPT_INVALID`，错误摘要返回模型，允许它决定再次生成/改 brief/停止。百分比与固定禁用表述的规则见contracts/README.md；其他事实仍须人工评估。网络瞬时错误为 `SCRIPT_MODEL_UNAVAILABLE`。没有内部自动修复循环。对任意语义幻觉不做“已完全防止”的承诺。

## T03：estimate_cost

输入：`plan_revision`（当前版本）、`rationale`。

前置：当前候选以及与 script_input_hash 匹配的成功草稿。缺少草稿时拒绝，不让没有交付内容的方案进入保存。

输出 data：`estimate_id`、`revision`、`candidate_hash`、`script_id`、`pricing_hash`、`quoted_at`、`line_items[]`、`total_units`、`total_minutes`、`estimated_finish_at`、`within_budget`、`within_deadline`、`feasible`、`budget_gap_units`、`deadline_gap_minutes`、`alternatives[]`。

line_items 固定四项：material_prepare、script_finalize、video_edit、review；各含 catalog_item_id、fee_units、duration_minutes。`feasible=within_budget AND within_deadline`；缺口分别为 max(total-budget,0) 和 max(ceil((finish-deadline)/60秒),0)。

alternatives 仅列出**同素材、同 brief、同草稿**的另一档位的报价、工期和约束结果；不替模型选档位，也不声称搜索了所有素材。每次显式估算重新读取 Clock，不复用旧时间判断；生成新的 estimate_id，之前估算保留。估算 ID 使用工具调用 ID 的 SHA-256 派生，避免同秒碰撞。

故障：`ESTIMATOR_UNAVAILABLE` 可重试；`PRICING_INVALID` 不可原样重试；前置/旧版本错误不可按原参数重试。

## T04：save_plan

输入：`plan_revision`、`estimate_id`、`rationale`。request_id、价格、脚本内容和输出文件路径由程序取值，不能让模型传入。

前置：候选当前、脚本有效、estimate_id 是当前候选最近一次成功估算且 feasible=true。保存前再用当前 Clock 和锁定报价表重新计算，确保生成过程中没有跨过截止时间。若有约束不满足，返回 `CONSTRAINT_VIOLATION`，包括当前缺口；不写方案。

成功事务保存：request_id、candidate_hash、脚本、分项报价、重新计算后的完成时间、四项 planned 活动步骤及来源。返回 data：`plan_id`、`request_id`、`saved_at`、`content_hash`、`saved_plan`。plan_id 为 `plan_` + SHA-256(request_id)；首版只一份终版，不支持保存后编辑。

同 request_id、同 content_hash 已提交时返回原行、`reused=true`；同 request_id、不同内容返回 `SAVE_CONFLICT`。content_hash 包括请求、候选、脚本与报价内容，不包括保存时间/重新读取的当前时间。唯一约束是最后保障，不能只“先查询再插入”。

失败 `SAVE_FAILED`/`STORAGE_UNAVAILABLE` 必须明确，不能设置 completed。事务提交成功但进程在 checkpoint 前中断时，由下次 service 的已提交方案核对恢复 completed。导出 Markdown 失败不等同数据库保存失败。

## C02：stop_task

输入：`reason`（no_material/constraints_unsatisfied/tool_failure）、`message`（1—500）、`rationale`。

前置证据：no_material 要求至少一次成功的空检索且尚无候选；constraints_unsatisfied 要求当前最新估算不满足约束；tool_failure 要求存在当前仍未解决的工具失败。无对应证据返回 `STOP_REASON_UNSUPPORTED`，不允许模型凭空宣布工具失败。

输出 data：`status=incomplete`、对应 reason、message、`evaluated_candidates[]`、`latest_gap`、`retained_artifact_ids[]`。约束停止的文案只描述已评估范围。已存在提交方案时不允许停止覆盖成功事实。

## 任务结果

必须包含：`schema_version`、`request_id`、`backend`、`model`、`status`、`reason`、`message`、`missing_fields[]`、`task_plan[]`、`execution_steps[]`、`tool_results[]`、`current_revision`、`candidate`、`total_units`、`saved_plan`、`usage`、`limits`、`warnings[]`、`trace_path`、`manifest`。具体 schema 见 result.schema.json。

status=needs_input 时不持久化，缺失字段或字段错误写 message/missing_fields；status=completed 时 saved_plan 必须非 null；其他状态 saved_plan 必须 null（若核对发现已提交方案，先恢复为 completed）。无当前有效估算时 total_units 必须 null，不能把旧候选金额当当前报价。

所有工具原结果保留在 tool_results；execution_steps 展示同任务截至查询时全部真实动作尝试，重复动作保留独立 attempt，续跑不截掉此前历史。task_plan 仅 completed 时包含最终四项活动；未完成可在candidate与工具结果中查看草稿，不把未确认候选渲染为已保存方案。candidate为null当且仅当尚未建立候选；current_revision必须与candidate.revision一致。初始错误没有manifest/trace时使用null；无法解析request_id时结果该字段为null。
