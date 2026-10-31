# 状态、持久化、幂等与恢复

## 状态权威

N1—N3自然语言入口新增的IntakeDraft/版本/确认Request只在交互进程内存；确认之前不注册requests、不启动graph、不写plans。输入整理事件与usage可导出到独立intake.jsonl，限制为字段变更、时间锚点、状态和确认关联，不保存完整自由对话、认证或推理。业务状态/限额/manifest继续以本文件原有规则为权威，抽取用量独立统计。重复确认沿同一Request调用run_task只读；业务输入变更生成新Request，不修改已提交任务。

- 用户要求：`requests` 的标准化不可变输入。
- 正在执行的候选、有效产物和合法消息：LangGraph checkpoint。
- 工具尝试事实与累计调用数：应用事件表；模型不得直接写这些字段。
- 是否保存成功：`plans` 中已提交的行，优先于未更新的 checkpoint。
- JSON/Markdown/JSONL 文件均为导出，可从数据库重建，不是业务真相来源。

不在 `requests` 再保存一份可自由修改的 graph_state；不编写第二套通用 checkpoint 引擎。

## AgentState 的确定字段

图状态使用TypedDict，内部DTO写入checkpoint前转为JSON兼容的dict/list/string/int/bool/null，不存客户端、数据库连接或Pydantic实例。

| 字段 | 类型与用途 |
|---|---|
| request | 标准化完整请求dict，禁止模型改写 |
| manifest | Manifest，与请求注册记录一致 |
| status/reason/message | 任务状态、可空原因、面向用户摘要 |
| decision_seq | 已持久化planner决策序号，初始0；包含协议错误响应 |
| consecutive_protocol_errors | 连续协议/参数格式错误次数，初始0 |
| planner_messages | 合法协议消息list，含原始tool_call_id及配对结果；不含脚本生成内部提示或推理内容 |
| pending_call | null或{id,name,arguments}；arguments保留模型原始JSON字符串供严格校验 |
| seen_material_ids | 去重、排序的素材ID列表 |
| candidate_history | revision字符串到Candidate的映射；最多4项 |
| current_revision | null或当前revision整数 |
| script_artifacts | script_input_hash到Script的映射；保留旧结果但使用前必须核对指纹 |
| estimate_history | estimate_id到Estimate的映射；保留历史 |
| current_estimate_id | null或当前候选最近一次成功估算ID；候选变化立即置null |
| tool_results | 成功、失败和拒绝的ToolResult列表；按真实operation顺序 |
| last_observation | null或最近ToolResult，供下一次模型决策 |
| saved_plan_id | null或已核对提交的plan_id |

累计限额、execution_steps和Trace从事件表派生，不在checkpoint维护第二份权威计数。状态补丁合并以operation_id/artifact_id/revision幂等；不使用无条件list append reducer，以免恢复重放重复追加。planner_messages只在完成一轮合法回传后作为稳定恢复历史；pending响应在下一次模型请求前必须被完整配对。

## 状态枚举与转换

任务状态：needs_input、running、completed、incomplete。

```text
输入缺失/非法 -> needs_input（不创建持久任务）
输入有效 -> running
running -> completed（只允许方案事务提交后）
running -> incomplete（模型停止、错误或上限）
incomplete -> running（仅显式 resume 且满足可续跑条件）
completed -> completed（重复 run/show；不重新调用模型）
```

每个执行 attempt：started -> succeeded/failed/rejected。未完成的 started 在重新启动时标记为 interrupted/结果未知，不能推定成功。执行步骤的当前视图：pending/succeeded/failed/stale；失效不删除历史成功 attempt。不存在真实工具结果时禁止填 succeeded。

任务中断的存储结果未知不等于保存失败：必须先查 plans；查询也失败则返回进程级 STORAGE_UNAVAILABLE，不能猜测状态。

## 数据表

业务表与框架表共用 `runtime.db`；框架表结构交给框架版本管理。

| 表 | 应用字段与约束 |
|---|---|
| requests | request_id TEXT PRIMARY KEY；input_hash；input_json；backend；model；manifest_json；created_at；schema_version |
| events | event_id INTEGER PRIMARY KEY；request_id FK；kind(model/tool/control/validation/lifecycle)；operation_id；phase(started/succeeded/failed/rejected/interrupted)；name；args_json；result_json；state_patch_json（可空） ；error_code；rationale；created_at；UNIQUE(request_id, operation_id, phase) |
| plans | plan_id TEXT PRIMARY KEY；request_id TEXT NOT NULL UNIQUE FK；content_hash；payload_json；saved_at |

事件按 event_id 排序；started 在外部模型或工具调用**之前提交**。每次逻辑调用只一条 started，结束另添事件，不覆盖失败历史。相同 operation_id 的已完成工具重放读取原结果与状态补丁，不能再次产生业务副作用。

operation_id规则：planner为`decide:<checkpoint中的决策序号+1>`；工具为`tool:<原始tool_call_id>`；脚本内部模型请求为`<工具operation_id>:script`。重新尝试是新的模型决策/工具调用ID；同一pending节点的重放沿用原ID。已存成功planner响应也按operation_id复用；对未存结果的started只保留调用额度，标为interrupted后创建带`:recovery:<序号>`的新尝试，不能覆盖原事件。

`state_patch_json`是应用内部的已验证状态更新，不进入ToolResult公开结构；成功事件和补丁一起提交。Trace不直接导出完整planner响应，只导出动作、公开理由和必要观察。

派生调用计数统计 started：model 类计模型请求；tool/control 类计动作调用，失败和复用也消耗次数。validation 类不算已执行工具，但对应模型请求已计数。统计和写入同一短事务；不在 HTTP 请求期间持有数据库事务。

首版实现数据库初始化与 schema_version=1 检查；未知版本拒绝打开，不做通用迁移系统。启用 foreign_keys、WAL、busy_timeout=5000ms。单进程串行执行；不保证并发操作同一任务的 checkpoint 一致性，README 明确不支持这种运行方式。

### S3实现边界与验收入口（2026-10-30，实现前）

公开入口为`Repository(path)`、register/get_request/get_plan/record_event/events/close，以及`LocalTools(..., repository=repo).save_plan(tool_call_id, arguments)`。使用标准库sqlite3和真实临时数据库；连接与SQL由repository持有，工具负责候选依赖及保存前复核。无repository时保留S2纯本地调用。注入repository时构造工具会注册请求；新ID先检查完整输入/期限，已有同输入ID直接读原记录，不因过期修改历史；不同输入报REQUEST_CONFLICT。

使用SQLite PRAGMA user_version=1记录业务版本。未知非零版本报SCHEMA_VERSION_MISMATCH，初始化/读取故障报STORAGE_UNAVAILABLE。register只写请求索引，返回原始注册记录；get_plan无方案时返回null，缺失请求的get_request为REQUEST_NOT_FOUND。事件按event_id读取并还原JSON，唯一键重复写入返回原事件。S3只接通保存动作的started及成功/失败/拒绝事件；其他动作事件、额度、图恢复归S4/S6，不编写空实现。

保存动作先持久started，校验当前候选、匹配脚本和最新estimate引用。缺失依赖为PRECONDITION_FAILED、旧revision为STALE_REVISION、旧估算为STALE_ESTIMATE；不可行估算或保存时重新计算不可行为CONSTRAINT_VIOLATION。拒绝/失败保留原草稿和估算，不能设completed。数据库触发器注入成功事件写入失败时，plan与成功事件一并回滚，started/失败历史可查。

已有提交方案的任务不再执行检索/修订/生成/估算，返回TASK_ALREADY_COMPLETED；保存重放仍读取既有事实。LocalTools接入repository时也核对已有方案以恢复completed标记，完整历史结果导出与checkpoint恢复仍归后续阶段。

content_hash按现行canonical JSON，对`{request, candidate, script, pricing_hash, line_items}`整体SHA-256；request为标准化四字段，candidate为六字段可信候选，script为含程序ID的完整脚本，line_items为锁定报价分项。不含estimate_id、tool_call_id、rationale、保存/估算时刻或派生时间表。相同内容已提交时先读原方案，允许期限过后仍复用历史；不同内容为SAVE_CONFLICT。新方案在当前时刻重报价，以该时刻依序生成四项planned时间表，每项依赖前一项，来源为选中素材。成功ToolResult和`{status:completed,saved_plan_id}`补丁与plan同事务提交，之后才修改内存状态。同operation成功重放读取原成功结果/补丁，新的同内容保存调用记录独立事件但复用原行。

本阶段通过真实行数、唯一约束、触发器故障、关闭重开查询和ToolResult Schema核对A09/A10/A11/A13的存储断言，以及旧估算/超期保存拒绝；不把它们记作CLI幂等或跨进程checkpoint恢复通过。依赖/打包/资源/入口未变时无需重建wheel或新建安装环境。

## 指纹与重复请求

input_hash = SHA-256(标准化后的 topic、budget_units、deadline_at UTC、固定受众与平台的 canonical JSON)。request_id 不进入 input_hash；canonical JSON 排序键、UTF-8、无多余空白。

S1确定的指纹序列化：JSON使用ensure_ascii=false、sort_keys=true、separators=(",", ":")，UTC时间使用datetime.isoformat()（+00:00，相同绝对时间的小数尾零归一）。输入对象的键为topic、budget_units、deadline_at、audience（新手创作者）、platform（短视频平台）。

candidate_hash对象包含input_hash、material_hash、creative_brief、production_mode、pricing_hash；script_input_hash对象仅包含topic、audience、platform、material_hash、creative_brief、script_prompt_version、model_id、thinking。brief先做NFC/trim。material_hash对素材内容对象做相同JSON哈希，排除检索score；素材内容变化必须改变指纹。pricing_hash由调用方提供报价文件内容SHA-256，不能只传版本名。模型ID和提示版本显式传入；thinking首版为disabled。request_id、revision、rationale、tool_call_id和当前时间不进入这些内容指纹。指纹纯函数不做缓存读写、版本推进或候选选择，依赖失效执行留待S2。

环境 manifest 独立保存：素材文件内容 SHA-256、报价文件 SHA-256、别名文件 SHA-256、planner/script 提示版本、模型 ID、thinking 配置、契约版本。版本名相同但内容变化仍能被识别。

| 操作 | 条件 | 结果 |
|---|---|---|
| run | ID 不存在，输入有效 | 注册请求，启动 graph，thread_id=request_id |
| run | ID 存在，input_hash 相同 | 只返回已有状态/方案，不续跑、不新建 plan |
| run | ID 存在，input_hash 不同 | REQUEST_CONFLICT，无修改 |
| show | ID 不存在 | REQUEST_NOT_FOUND |
| resume | 已 completed | 原方案，零模型调用 |
| resume | 可恢复 incomplete/中断，manifest 一致且尚有额度 | 恢复；保留已完成、仍有效的结果 |
| resume | manifest 变化/不可恢复原因/无剩余额度 | 拒绝并给原因；不得自动换输入或重置额度 |

查询历史方案不受本地资料后续变化影响；历史输出使用原 manifest 和提交内容。对改变报价或素材后的模型行为做评估必须使用**新 request_id**，避免将正确幂等读缓存误判为“模型没调整”。

## 依赖和失效

```text
request + material_hash + creative_brief + script_prompt/model
    -> script_input_hash -> script artifact

request + material_hash + creative_brief + production_mode + pricing_hash
    -> candidate_hash

candidate_hash + script_id + 当前 Clock
    -> estimate

current candidate + current script + 最新 feasible estimate + 保存时复核
    -> saved plan
```

- 换档位：脚本仍有效；旧估算 stale，必须再次估算。
- 换素材/brief：新 script_input_hash；旧脚本仍保留但不能作为当前脚本，旧估算 stale。
- 改预算/截止时间：不允许原任务修改，使用新 request_id。
- 重复相同候选：不增加 revision；重复同脚本输入：复用成功结果。
- 估算每次调用重新取时间，不复用历史时间判断。保存再复核，过期候选不能通过。
- 资料文件变化：原任务不允许续跑，防止混用旧资料和新报价。

## 保存事务与恢复边界

save_plan 必须在一个业务事务中写 plan 和保存成功事件，任何写失败回滚。plan payload 从可信当前状态构造，不接受模型传价格或成功状态。先提交再设置内存/checkpoint completed。

若提交后、checkpoint 前崩溃：下次入口查到 plan 后修正返回为 completed；不重新检索、生成或保存。若提交前崩溃：没有 plan，不得报成功；可以恢复相同 pending tool call。保存结果用 UNIQUE 防重复。

checkpoint 与 events 不是统一跨连接事务。dispatch 重放相同 operation_id 时若已存在成功结束事件，复用已持久化结果与经过校验的状态补丁；补丁按 artifact ID/revision/event_id 幂等合并，不能再次追加同一事件。

若外部模型已经返回、但进程在结果持久化前崩溃，结果无法证明，恢复可能重新请求并产生额外真实 API 费用。首版不承诺模型调用 exactly-once，不宣称生产级耐久执行。已持久化的成功产物才保证复用。

## 续跑行为

### S6接通细化（实现前，2026-10-31）

公开入口为`service.resume_task(request_id, database=..., model=None, clock=None, mock_scenario=None, catalog=None)`及CLI `resume --request-id ... --db ... --output-dir ... --mock-scenario <后续响应.json>`。catalog仅复用既有公开资料加载入口的可替换目录/快照，供真实资料变化验证；不创建新框架。Mock后续场景只提供新的显式响应/测试Clock，不能更改原任务输入、backend/model或manifest；未完成Mock续跑需要后续场景（或注入ModelClient）。completed查询不需要场景、当前资料或模型配置。

先读requests/plans：有提交方案直接返回completed，无新事件/模型/工具；checkpoint不可读时可用提交事实与已有事件返回并附CHECKPOINT_UNAVAILABLE告警。无提交时需有效checkpoint。恢复前比较原manifest与当前资料三hash、提示版本、契约版本、model_id/thinking及backend，差异为MANIFEST_MISMATCH；缺checkpoint为CHECKPOINT_NOT_FOUND。不可恢复正常停止为RESUME_NOT_ALLOWED；累计模型/动作耗尽使用既有对应LIMIT原因。拒绝只返回带明确reason的incomplete视图，不修改原任务/历史/额度。

可恢复的正常结束只限MODEL_UNAVAILABLE，以及tool_failure中仍适用且retryable=true的业务错误；显式停止资料不足、约束不足、SCRIPT_INVALID等不可重试错误、MODEL_STOPPED、协议/候选/图/调用限额均拒绝。成功resume清运行终态字段，不清候选、产物、失败历史、决策序号、协议错误计数或任何累计额度；原截止时间不变，保存时重新报价守住期限。

框架有pending节点时使用LangGraph invoke(None)，不重跑已完成节点；恢复可信checkpoint到LocalTools工作状态。dispatch按原tool_call_id核对同operation的结束事件，有已持久结果/补丁则复用并补齐原消息配对，不再次执行或追加同一ToolResult。候选/脚本使用当前指纹；换素材/brief仍废弃旧脚本引用，换档位只废弃估算。日志有已提交状态补丁但checkpoint落后时，重放补丁恢复业务事实。

框架中断判断同时检查StateSnapshot.next及tasks：已完成节点的pending writes可能使next为空而tasks仍存在，此时仍使用invoke(None)应用框架持久写入，不能当作正常停止，也不能从START重启。

每个model请求先按operation查日志：已成功响应直接复用；已失败响应恢复为同一次失败观察；只有started且无结束结果时追加interrupted，结果仍未知。未知的模型/工具尝试以`<原operation_id>:recovery:<n>`记录新started，args中内部recovery_of关联原operation，沿用原工具调用ID与原模型决策序号；新started照常计数。内部script模型operation仍关联原工具调用，已有脚本模型成功响应在工具节点重放时复用。未知外部请求可能再次产生费用，不承诺exactly-once。恢复后仍不得绕过同键两次可重试失败或全局额度。Trace不暴露recovery_of等内部参数；attempt按真实started保留interrupted与后续尝试。

日志分组必须同时核对operation基名与kind（model/tool/control），结束事件通过同operation_id的started关联，不能依赖结束事件恰好携带recovery_of。外部合法调用ID可含`:script`等字符；与内部operation基名碰撞时使用未占用的recovery后缀记录该新动作，不复用另一kind的响应，原tool_call_id保持不变。

验收用新进程及真实SQLite/checkpoint，在持久结果前、工具事件提交后但节点checkpoint前、plan事务提交后但checkpoint前注入进程退出；不以Mock保存结果替代真实提交。故障注入只在测试进程的数据库适配边界，业务程序不增加隐藏故障参数。离线阶段不发真实HTTP。

- checkpoint 有未完成框架节点：按框架接口恢复 pending 节点，不从头再跑正常路径。
- 上一轮已经以可恢复 incomplete 正常结束：保留 checkpoint 产物与合法历史，将运行状态设为 running，从 decide 让模型观察已有错误并选择下一步。
- 可恢复原因：工具瞬时失败、模型网络/限流/服务故障、进程中断；受每参数最多两次工具尝试和累计限额限制。
- 不可恢复原因：资料不足、约束停止、参数/权限配置错误、连续协议错误、执行上限、版本不兼容。输入变化必须新请求。
- 续跑不重置工具尝试、revision 或累计模型额度；修改密钥值本身不改变 manifest，允许修复本地认证后为新任务运行。原任务 AUTH_ERROR 不自动续跑。

## 限额和失败策略

### S4接通范围（实现前，2026-10-30）

本阶段接通六动作的事件及planner/script模型请求日志，所有started先提交；Repository.start_operation将累计计数检查与写started放在同一短事务。模型32、动作24、候选4沿用下表；同逻辑键连续可重试失败最多2次，第三次返回TOOL_RETRY_LIMIT_REACHED而不实际执行，仍受动作总额限制。合法动作后清除协议错误连续计数，普通业务失败不会被当成参数协议错误。GraphRecursionError映射GRAPH_LIMIT_REACHED。

S4动作事件args_json用`{arguments: 原参数, logical_key: 程序指纹}`信封保存审计参数与重试键；S3保存事务的成功事件继续保存原参数，不改公开ToolResult。计数只从started派生。业务成功/失败及状态补丁随后单独提交；save成功事件与plan保持原事务。JSON参数非法、未知工具及多调用为validation事件，不算执行动作；有完整合法ID时逐一配对错误工具消息，缺ID等无法合法回传时立即停止。重复tool_call_id为协议错误，不能当作新动作执行。

任务工作记忆补充unresolved_failures（逻辑键到失败工具/调用引用），成功解决同键；检索成功清除此前检索不可用，候选变更后stop只考虑仍适用的生成/估算/保存失败。stop_task校验真实空检索/当前不可行估算/当前未解决业务工具错误；成功输出历史估算和保留产物引用，状态incomplete。纯文本结束为MODEL_STOPPED。累计日志和工作状态进入真实SQLite/checkpoint，本阶段不开放CLI/resume或完整导出。

| 限制 | 固定首版值 | 命中后的行为 |
|---|---|---|
| 模型请求 | 每任务累计 32 次，包含 script 生成和失败请求 | incomplete / MODEL_CALL_LIMIT_REACHED |
| 动作调用 | 每任务累计 24 次，包含四工具、两控制动作、失败与复用 | incomplete / ACTION_LIMIT_REACHED |
| 不同候选版本 | 最多 4，含初始版 | incomplete / REVISION_LIMIT_REACHED |
| 同逻辑参数的可重试失败 | 初次 + 1 次，最多 2 次 | 再试拒绝；模型可改变参数/方案或停止，受总上限约束 |
| 连续协议/参数错误 | 最多 2 次，成功合法动作后清零 | incomplete / MODEL_PROTOCOL_ERROR |
| LangGraph recursion_limit | 每次 invoke=80 个 supersteps，防御性兜底 | 捕获错误，incomplete / GRAPH_LIMIT_REACHED |

参数错误的第一次作为工具错误反馈，允许模型修正；第二次连续错误停止。未知工具名、非法 JSON、一次多个工具调用、缺 tool_call_id 属于协议错误。多工具响应整组不执行；有合法 ID 时为每个原调用配对错误反馈，不能只执行第一个或留下未回应调用。无法构造合法回传时立即 MODEL_PROTOCOL_ERROR。

逻辑重试键：检索=规范化query+top_k+catalog_hash；生成=script_input_hash；估算=candidate_hash+script_id+pricing_hash；保存=request_id+candidate_hash+script_id+pricing_hash。均排除rationale、tool_call_id与当前时间。最多两次指同键的实际执行尝试；成功缓存的读取仍计动作额度，但不再发外部请求。改变无关措辞或新estimate_id不能绕过保存重试限制。

模型只返回普通文本、未调用 stop/save 时：incomplete / MODEL_STOPPED，保留草稿，不把文本“已完成”当成功。HTTP 401/403 是 AUTH_ERROR，不自动重试；429/超时/5xx 映射为可恢复模型错误；其他 4xx 是配置/协议错误。

如果方案已经提交，后续导出、日志或 checkpoint 故障不抹掉已保存事实；先查已提交结果，再返回 completed + warning，查不到时才按未完成处理。
