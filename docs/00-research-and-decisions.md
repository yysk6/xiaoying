# 官方资料调研与架构决策

调研时间：2026-10-29。以下能力描述来自官方资料；“适合本项目”的结论属于本项目的工程判断。没有进行框架性能基准。调研时未安装框架；后续S0已验证所选LangGraph组合，证据见docs/stages/S0.md。

## ADR-001：选择 LangGraph 的薄执行图

| 路线 | 官方能力依据 | 对本题的判断 |
|---|---|---|
| 原生 Python 循环 | 本身可以组合 HTTP 调用、函数工具和 SQLite | 最小 ReAct 实现很直接，但持久化执行位置与跨进程续跑要自行实现。作为不做续跑时的备选，不选为首版路线 |
| **LangGraph** | 支持确定性节点与模型节点组合；checkpointer 持久化线程执行状态 | **选用**。本题要展示失败续跑和状态边界，框架承担执行位置，业务代码承担约束，职责可解释 |
| PydanticAI | 有类型化工具、模型替身、请求和工具调用限额；提供持久化/耐久执行能力 | 类型与测试体验合适；本项目仍需独立业务状态和幂等设计。所查主分支要求 Python >=3.11，本机为 3.10.8；不是认定旧版本不能用，首版不为它增加解释器/版本选择工作 |
| AgentScope | ReActAgent、结构化输出、工具、状态/会话管理 | 能完成题目，但本项目没有多 Agent 协作需求；当前选择更直接对应 checkpoint 和显式执行图的路线 |
| Google ADK | 提供顺序、循环、并行等工作流 Agent 及模型工具能力 | 可用，但仅拼接固定工作流不能证明题目要求的模型重规划；本项目不需要其完整 Agent Runtime |

不采用完整 LangChain Agent/Deep Agents，不引入 LangSmith 账户、远端 checkpoint 或工作流服务。LangGraph 本身不要求必须使用 LangChain 的模型封装。

2026-10-30重新评估：用户明确决定不接入Deep Agents，继续原路线并授权S4。原任务为有界单任务工具闭环，采用结构化任务记忆、完整交互组裁剪和SQLite checkpoint即可；不为跨任务长期记忆、多Agent或通用文件工具升级框架。此前中断的环境尝试未改变项目依赖/锁文件，应用仍使用Python 3.10.8。上下文细化见docs/02的S4段落。

执行图固定为两个节点 `decide -> dispatch -> decide`；候选方案参数由真实模型选择。图中的固定边是执行骨架，不替模型选择低价方案或决定重试。

## ADR-002：DeepSeek 的薄 HTTP 适配器

- 用户指定模型：`deepseek-v4-pro`；不静默替换为其他模型。
- 使用官方 Chat Completions 接口：`POST https://api.deepseek.com/chat/completions`。
- 官方接口确认支持该模型及 tool calls。默认可能开启 thinking，因此显式设置 `thinking: {type: "disabled"}`。
- 首版不启用 Beta strict mode；所有工具参数仍由本地 Pydantic 严格验证，拒绝额外字段。
- 决策请求传函数工具 schema；脚本生成请求不传工具，使用 JSON output，仍须本地校验。
- HTTPX 直接访问官方协议，不增加完整 LangChain 模型适配或 OpenAI SDK；只维护本项目需要的消息、tool call、usage、错误映射。
- 不发送未经官方接口确认的 `parallel_tool_calls` 参数。通过提示要求一次一个动作，并在客户端拒绝多工具响应。
- 关闭 HTTP 自动重试。工具失败后是否再试必须由模型观察决定；模型请求本身失败时返回未完成，显式续跑才再次请求。
- 非思考模式依然能够实现模型观察工具结果后调整动作的 ReAct 闭环。不得把公开 Trace 包装成模型内部思维过程。

首版固定参数：`temperature=0`（不承诺确定性），决策 `max_tokens=2048`，脚本 `max_tokens=1536`，`stream=false`。HTTPX 超时：connect=5s、read=45s、write=10s、pool=5s；这些是分项超时，不是严格的总耗时 SLA。

2026-10-31 S7实现前重新核对上述官方Chat Completions/Tool Calls/JSON Output文档：指定模型、非思考工具调用、json_object及usage字段仍支持；parallel_tool_calls不在官方当前请求字段中，继续不发送。保持薄HTTPX适配、不新增SDK或依赖。用户明确授权测试直接使用提供的密钥；仅在外部测试进程内注入环境，不落盘、不回显，应用仍只读环境变量。

## ADR-003：SQLite 是本地状态后端

使用 Python `sqlite3`，本地单写者 CLI。LangGraph checkpointer 表与业务表共用一个数据库文件、不同连接；应用不访问框架内部表。

checkpoint 与业务保存不能假设在同一事务。`plans.request_id UNIQUE` 及保存后的事实核对防止重放产生第二份方案。数据库保存成功后再生成的 Markdown 是导出文件，不是第二个业务存储。

不引入 ORM、Redis、PostgreSQL、消息队列或分布式锁；不承诺多进程并发运行同一任务。数据库唯一约束仍作为保存防重复的最后一道保证。

## ADR-004：SDD + TDD，不用 Mock 冒充模型评估

规格先定义预算语义、契约、状态、错误与验收点；每个开发切片先写能失败的测试，再做最小实现。普通 pytest 默认禁止真实网络。Live eval 单独开启，记录模型参数、数据版本、真实结果和失败。

## ADR-005：公开依赖与宿主无关

新增用户约束：所有项目工具/插件应为第三方公开组件或非Codex内部能力，能适配其他环境。当前技术路线符合这一设计方向：LangGraph、Pydantic、HTTPX、pytest为公开第三方库；sqlite3、argparse、pathlib等为Python标准库。它们是普通Python依赖，不要求安装Codex插件。

开发、测试、资料读取、Trace导出使用通用命令或仓库脚本；不调用Codex专用插件作为项目流程的一环。模型调用仅走DeepSeek公开HTTP接口，不通过Codex账户或其模型配额。测试Fake放在仓库内，不依赖外部宿主替身。

路径通过CLI参数/pathlib解析；默认合成资料随Python包分发并通过importlib.resources定位，不能依赖当前cwd或开发机绝对路径。不得硬编码用户目录、Windows盘符或Codex缓存目录。文档提供Windows PowerShell和POSIX shell命令。离线测试不得隐式需要任何宿主环境变量。持久化数据库是本地运行数据，跨机器优先重新运行案例，不承诺不同依赖版本间checkpoint文件可直接迁移。

兼容性目标：Windows为主要验证环境，另以Linux干净Python环境验证安装、离线CLI和测试。Linux尚未实际验证；CI可用后运行并保留日志，不能提前标成通过。不要求首版支持所有操作系统或任意模型服务。

## ADR-006：分阶段开发与验收

用户要求分阶段开发、分阶段验收，开发遵循karpathy-guidelines。阶段范围与验收点以docs/08-development-plan.md为准，每次只交付当前阶段，明确验收后进入下一阶段。

环境兼容性与最小checkpoint探针在S0完成；真实DeepSeek适配与付费探针调整到S7。此前“模型探针是开始业务实现的前置门槛”的安排由本决策替代：它现在是真实模型阶段的前置门槛，不阻止已获准的离线阶段开发。若需提前验证，由用户明确授权，不默认跨阶段。

Mock、本地状态恢复、真实模型效果、跨环境运行分别验收；局部通过不提前计为完整用例或完整项目通过。

## 候选依赖基线与核验状态

| 依赖 | 候选版本 | 证据与状态 |
|---|---|---|
| Python | 兼容 3.10.8，支持范围首版仅验证 3.10 | 本机命令已确认；不能写成已验证所有较新版本 |
| langgraph | 1.2.18 | S0隔离安装、依赖检查及独立checkpoint恢复通过 |
| langgraph-checkpoint-sqlite | 3.1.2 | S0关闭连接、重建图后恢复成功节点不重复执行 |
| pydantic | 2.12.5 | S0严格整数探针通过；业务DTO留待S1 |
| httpx | 0.28.1 | S0安装与依赖检查通过；DeepSeek服务未验证 |
| pytest | 9.0.3 | S0四项测试在开发及干净环境各通过一次 |

S0已生成requirements.lock和requirements-dev.lock，并在干净环境用本地wheelhouse及--no-deps/--no-index实际重建。锁定42个运行依赖及15个开发/构建依赖；不锁定artifact哈希。仅验证Windows/Python 3.10.8；其他平台与真实模型效果不在本次结论中。后续变更版本先更新ADR与锁文件，不静默切换架构。

## 官方来源

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)：确定性与模型步骤组合，不强制使用 LangChain。
- [LangGraph quickstart](https://docs.langchain.com/oss/python/langgraph/quickstart)：模型节点、工具节点与回环。
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)：checkpointer 的线程执行状态与 store 的区别。
- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/use-graph-api)：recursion limit。
- [LangGraph 包版本](https://pypi.org/project/langgraph/1.2.18/)；[SQLite checkpointer 版本](https://pypi.org/project/langgraph-checkpoint-sqlite/3.1.2/)。
- [PydanticAI testing](https://pydantic.dev/docs/ai/guides/testing/)：TestModel/FunctionModel 与模型评估边界。
- [PydanticAI Agent](https://pydantic.dev/docs/ai/core-concepts/agent/)：UsageLimits；[项目 Python 版本要求](https://github.com/pydantic/pydantic-ai/blob/main/pyproject.toml)。
- [AgentScope ReActAgent](https://doc.agentscope.io/tutorial/task_agent.html)。
- [Google ADK 工作流](https://adk.dev/agents/workflow-agents/)。
- [DeepSeek 模型与能力](https://api-docs.deepseek.com/quick_start/pricing/)：模型 ID、协议与功能；本项目不固定其可能变化的真实价格。
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：消息、函数调用和参数校验要求。
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)：调用回传与 Beta strict 模式。
- [DeepSeek JSON output](https://api-docs.deepseek.com/guides/json_mode/)：JSON 输出配置与本地校验需求。
- [Pydantic models](https://pydantic.dev/docs/validation/latest/concepts/models/)；[pytest monkeypatch](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)。
- [Python sqlite3](https://docs.python.org/3.10/library/sqlite3.html)；[HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/)。

实现限制：文档确认不能替代账号可用性、余额、网络、接口兼容性与恢复行为的实际测试。
