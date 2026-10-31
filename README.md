# 内容任务规划 Agent

编写日期：2026-10-29（北京时间）。选题：第 2 题。开发方式：SDD（规格驱动开发）+ TDD（测试驱动开发）。

已实现领域规则、本地工具、SQLite保存/幂等、LangGraph循环、run/show/resume及JSON/Markdown/Trace导出，并接通DeepSeek官方HTTP API。当前阶段、授权与验收状态统一见[HANDOFF](HANDOFF.md)，实际测试、真实样本与限制见[S7报告](docs/stages/S7.md)。

接手或恢复开发请先阅读[上下文交接文档](HANDOFF.md)。该文档须在每阶段交付验收前更新，用户验收或修订后同步更新；规则见AGENTS.md与阶段计划。

## 当前评审入口

- [S7验收报告](docs/stages/S7.md)：真实HTTP适配、协议测试及L01—L03单次真实样本。
- [S6验收报告](docs/stages/S6.md)：显式续跑、跨进程恢复、重放及累计限额。
- [S5验收报告](docs/stages/S5.md)：历史CLI核心案例、导出与安装验证。
- [S4验收报告](docs/stages/S4.md)：历史离线循环、停止/限额及上下文验证。
- [S3验收报告](docs/stages/S3.md)：历史存储/保存验证。
- [S2验收报告](docs/stages/S2.md)：历史工具层测试与wheel验证。
- [本地工具演示](examples/tests/stages/S2/local-tools-demo.json)：显式调用得到12→8报价，脚本复用；不是Agent决策或保存记录。
- [S1验收报告](docs/stages/S1.md)：历史契约与领域层证据。
- [S0验收报告](docs/stages/S0.md)：范围、Red/Green、限制和验收步骤。
- [开发环境结果](examples/tests/stages/S0/green-tests.txt)：4项工程测试通过。
- [干净安装结果](examples/tests/stages/S0/clean-install.json)：运行/开发锁离线安装、正式wheel导入、相同4项测试通过。
- [阶段规划](docs/08-development-plan.md)：范围、效率约定与逐阶段交付规则。

Windows PowerShell（项目根目录，Python 3.10）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build --no-isolation
```

POSIX shell的对应命令（尚未在Linux实测，留待S8）：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
.venv/bin/python -m build --no-isolation
```

requirements.lock锁定42个运行依赖，requirements-dev.lock增加15个开发/构建依赖，基于Windows/Python 3.10实际环境生成。固定版本，未启用artifact哈希校验；不修改全局环境。全新机器首次安装需联网。

需要复核安装时，先重新构建，再运行`python scripts/verify_s2.py --venv work/package-review`：脚本从仓库外cwd隔离导入正式wheel、检查包内资料并运行当前全部测试。目标路径必须不存在，保留旧环境。脚本移除模型及宿主专用环境变量，不调用真实模型。S2已有实际安装证据；S3未重新验证安装，不能把旧dist当作S3产物。旧verify_s0.py仅复核4项S0工程测试。

若先将锁定依赖下载到wheelhouse，可增加`--wheelhouse work/s0-wheelhouse`离线安装。本次已实际验证该方式；wheelhouse、虚拟环境和dist产物不提交Git。

## 开发位置与可移植性约束

后续项目根目录由用户指定为 `C:/Users/11250/Desktop/xiaoying/`。该路径只用于本地开发定位，程序、测试和运行命令不得依赖这一绝对路径。根目录下的docs/与contracts/是后续唯一维护版本；现有content-planner-spec/保留为迁入前快照，不要求同步修改。

项目及开发流程采用公开第三方库、Python标准库、Git和通用命令行工具，不依赖Codex内部插件/MCP/账户/宿主运行时。S2支持直接调用本地工具，`python examples/s2_local_tools.py`输出固定Clock下的演示；离线业务CLI在S5交付、真实模型模式在S7验证。

## 离线CLI

下列场景含固定Clock和显式Fake动作，重复运行读取已有任务；它们验证程序流程，不代表模型智能效果。三个必需案例及修订/重复执行证据见[S5报告](docs/stages/S5.md)。

PowerShell（完成上述安装后，在项目根目录）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m content_planner run --input examples/mock/A01/input.json --mock-scenario examples/mock/A01/scenario.json --db work/demo.db --output-dir work/demo-output
.\.venv\Scripts\python.exe -X utf8 -m content_planner show --request-id s5-A01 --db work/demo.db --output-dir work/demo-show
```

POSIX对应命令（Linux仍未实测）：

```sh
.venv/bin/python -m content_planner run --input examples/mock/A01/input.json --mock-scenario examples/mock/A01/scenario.json --db work/demo.db --output-dir work/demo-output
.venv/bin/python -m content_planner show --request-id s5-A01 --db work/demo.db --output-dir work/demo-show
```

省略`--mock-scenario`时使用包内固定M01/basic演示，采用真实当前时间；自备输入需要提供未来deadline。场景字段、退出码与错误规则见[CLI契约](docs/06-contracts.md)。stdout仅最终JSON，进度/错误在stderr；默认数据库work/runtime.db，默认输出work/runs/<request_id>/的output.json、plan.md、trace.jsonl。completed仅表示方案已保存，四项活动仍为planned。不支持同时运行同一任务的多个进程。

显式续跑示例（新数据库，第一条预期退出3；第二条在新进程完成）：

```powershell
.\.venv\Scripts\python.exe -m content_planner run --input examples/mock/A12/input.json --mock-scenario examples/mock/A12/scenario.json --db work/resume-demo.db --output-dir work/resume-before
.\.venv\Scripts\python.exe -m content_planner resume --request-id s6-A12 --mock-scenario examples/mock/A12/continuation.json --db work/resume-demo.db --output-dir work/resume-after
```

```sh
.venv/bin/python -m content_planner run --input examples/mock/A12/input.json --mock-scenario examples/mock/A12/scenario.json --db work/resume-demo.db --output-dir work/resume-before
.venv/bin/python -m content_planner resume --request-id s6-A12 --mock-scenario examples/mock/A12/continuation.json --db work/resume-demo.db --output-dir work/resume-after
```

上述两流固定UTF-8，无需Python编码参数；POSIX/Linux仍未实测。Mock未完成任务的resume需提供后续显式响应；已完成任务resume直接返回原方案，无需场景。资料/提示/模型配置变化、不可恢复停止或额度耗尽会明确拒绝，不修改原任务，也不重置额度。已持久成功产物/响应会复用；外部返回但未持久的请求结果未知，恢复可能再请求，不承诺API exactly-once。普通重复run始终只读。详细边界见[恢复规格](docs/07-state-and-storage.md#s6接通细化实现前2026-10-31)。

## 真实DeepSeek后端

应用仅从环境变量读取密钥，不自动加载.env。使用未来的带时区deadline及新request_id；以下命令会产生真实API费用。

```powershell
$env:DEEPSEEK_API_KEY = '<your-key>'
.\.venv\Scripts\python.exe -m content_planner run --backend deepseek --input examples/inputs/live-input.json --db work/live.db --output-dir work/live-output
.\.venv\Scripts\python.exe -m content_planner resume --request-id <request-id> --db work/live.db
# 按当前时间生成输入，探针后各运行L01—L03一次：
.\.venv\Scripts\python.exe scripts/evaluate_live.py --live
```

```sh
export DEEPSEEK_API_KEY='<your-key>'
.venv/bin/python -m content_planner run --backend deepseek --input examples/inputs/live-input.json --db work/live.db --output-dir work/live-output
.venv/bin/python -m content_planner resume --request-id <request-id> --db work/live.db
.venv/bin/python scripts/evaluate_live.py --live
```

`live-input.json`由使用者按[Request Schema](contracts/request.schema.json)准备，示例目录不含固定未来日期文件。默认官方地址https://api.deepseek.com及模型deepseek-v4-pro，thinking关闭；不接受其他地址/模型。live不接受mock场景，不自动回退；缺配置返回CONFIG_ERROR。历史查询及已完成任务resume无需当前密钥。真实token按响应记录，未知为null；模拟报价units与API美元费用分开。S7只测各一个样本；L03直接选basic8，不是12→8重规划；L04和Linux未测。详细证据见S7报告。

## 已确定的路线

- 语言：Python，兼容本机 3.10.8；实现不要求升级解释器。
- 模型：用户指定 DeepSeek V4 Pro，官方 API ID 为 `deepseek-v4-pro`。
- 执行：单 Agent、CLI、串行工具调用；LangGraph 只承担执行图与 checkpoint。
- 契约：Pydantic v2；持久化：SQLite；模型 HTTP 接入：HTTPX；测试：pytest。
- 功能：检索合成素材、生成脚本草稿、估算活动费用与工期、重规划、保存方案、防重复、失败续跑。
- 不做：网页、真实视频制作/发布、付款、真实素材抓取、多 Agent、通用 DAG 调度平台、生产级分布式恢复。

## 阅读顺序

| 文档 | 用途 |
|---|---|
| [00-research-and-decisions.md](docs/00-research-and-decisions.md) | 官方资料调研、框架选择、依赖版本与接入验证门槛 |
| [01-requirements.md](docs/01-requirements.md) | 需求编号、业务口径、范围、完成标准 |
| [02-solution.md](docs/02-solution.md) | 模块边界、调用图、模型与程序分工 |
| [06-contracts.md](docs/06-contracts.md) | CLI、四个工具与两个控制动作的契约 |
| [07-state-and-storage.md](docs/07-state-and-storage.md) | 状态、缓存失效、事务、幂等、恢复语义 |
| [03-evaluation.md](docs/03-evaluation.md) | 测试矩阵、模型评估、证据产物与验收门槛 |
| [08-development-plan.md](docs/08-development-plan.md) | SDD/TDD 顺序、阶段完成条件、建议时间分配 |
| [09-development-skills.md](docs/09-development-skills.md) | 六个开发技能的使用时机、来源和项目适配；不属于项目运行依赖 |
| [04-ai-usage.md](docs/04-ai-usage.md) | 当前真实 AI 使用范围和后续记录方式 |
| [05-retrospective.md](docs/05-retrospective.md) | 设计阶段风险；实现后填写实际复盘 |

机器可读规格在 [contracts/](contracts/)。接口字段约束以 JSON Schema 为准，状态和业务语义以相应文档为准。两者冲突必须先修规格，禁止实现自行选择一种解释。

规格阶段的历史静态检查见 [spec-review.json](spec-review.json)；后续实现和测试结果分别以阶段报告为准，该历史文件不代表当前代码覆盖或模型效果。

## 必须一致理解的业务口径

1. 预算是**最终活动方案的模拟报价**，不是模型 API 账单，也不是每次 Agent 尝试的累计收费。所有业务工具在本地模拟执行；改稿不会模拟扣款。
2. 费用与工期按版本化合成报价表计算。活动交付物固定为“一条短视频的活动方案 + 脚本草稿”，不制作视频。
3. 活动工期是素材准备、脚本定稿、剪辑制作、审核的串行预计耗时，不是 CLI 的运行时间。
4. `completed` 只表示合规方案已事务提交至本地数据库，不表示活动、视频或发布已经完成。
5. 模型决定检索、选择素材/制作档位、重规划、重试或停止；程序计算数字、校验依赖、维护真实状态并阻止违规保存。
6. 续跑必须显式调用 `resume`；普通重复 `run` 只返回已有任务，不能悄悄再执行。
7. 真实模型表现需要真实运行证据。离线 Mock 只验证程序流程和约束。
8. 无Codex环境可运行是独立验收项R15/A23；最终须在干净环境实际验证，不能仅凭未导入Codex模块就声称兼容验证完成。

## 开始实现前的门槛

开发按[分阶段计划](docs/08-development-plan.md)推进。每阶段先写测试、最小实现、自验，提交阶段报告后等待用户验收；最新状态见HANDOFF。当前数据库仅支持单进程串行操作，不支持并发执行同一任务的checkpoint。

语言和模型已经确定，技术验证门槛按阶段区分：

- S0：在隔离虚拟环境安装候选依赖，验证 LangGraph checkpoint/恢复与 Pydantic 契约兼容，生成精确依赖锁文件。
- S7：在本地环境配置有效密钥后，验证指定模型的一次工具调用、工具结果回传和脚本 JSON 输出。未通过之前不能声称真实模型路径可运行；不阻止已获准的离线阶段开发。

密钥只允许从环境变量读取；本包没有收录用户发送的密钥。首版固定关闭 thinking，避免把内部推理内容写入日志；简要动作依据通过工具参数 `rationale` 单独提供。

## 最终项目的目录约定

```text
README.md
pyproject.toml
requirements.lock
requirements-dev.lock
.env.example
.gitignore
src/content_planner/
tests/{unit,integration,acceptance}/
examples/{inputs,mock,live,tests}/
src/content_planner/data/{materials.json,pricing.json,aliases.json}
docs/                       # 保留本包文档并更新实际结果
contracts/                  # 本包接口规格；实现后由 Pydantic 导出并检查兼容
```

PlanningAgent通过LangGraph decide/dispatch执行ModelClient明确返回的六动作；LocalTools和SQLite守住依赖、约束、保存及恢复事实。Fake仅验证流程，不证明真实模型效果。任务记忆与上下文裁剪见docs/02；真实HTTP和真实决策效果归S7。
