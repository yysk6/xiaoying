# 输入、工具与输出契约

本文件给出语义；精确字段见 `contracts/*.schema.json`。除明确开放的诊断details和Trace原始args外，所有对象禁止未声明字段。所有字符串做 NFC 规范化、首尾去空白；ID 大小写敏感；JSON boolean 不能当作整数。用户内容只是数据，不能更改工具白名单、预算或提示中的系统约束。

## CLI

以下是**拟实现命令**，本包阶段尚不可执行：

```text
python -m content_planner run --input <request.json> --backend mock|deepseek --db <runtime.db> --output-dir <directory>
python -m content_planner show --request-id <ID> --db <runtime.db> --output-dir <directory>
python -m content_planner resume --request-id <ID> --db <runtime.db> --output-dir <directory>
```

`run` 默认 backend=mock、db=`work/runtime.db`、output-dir=`work/runs/<request_id>`；业务资料从项目 `data/` 读取。`resume` 使用原任务 backend 和配置，不允许借续跑变更模型/资料/预算。`show` 不调用模型或业务工具。live 模式缺少模型环境变量时明确报配置错误，不退回 Mock。

退出码：0=completed；2=needs_input/输入或配置错误/请求冲突；3=incomplete；1=不能构造可信结果的进程/存储故障。`show` 的退出码反映所查任务状态。错误和进度写 stderr，stdout 只写最终 JSON。输出目录创建失败不回滚已提交方案，输出 `EXPORT_FAILED` 警告并允许重新 show。

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

## 所有动作的共同规则

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
