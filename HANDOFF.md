# 项目上下文交接

更新日期：2026-10-29（北京时间）。本文件是接手开发的首读入口，记录当前事实和允许推进的范围；规格以docs/与contracts/为准，历史细节以阶段报告和Git记录为准。

## 1. 接手后的第一步

1. 阅读AGENTS.md、本文件、[阶段计划](docs/08-development-plan.md)和当前阶段报告。
2. 执行`git status --short --branch`、`git log -3 --oneline`、`git remote -v`，核对实际工作区。不要仅依据本文假定HEAD、权限或环境未变化。
3. 检查当前阶段是否已获用户明确验收；未验收不得进入下一阶段。不要覆盖接手时已有的未提交改动。

项目位置：`C:/Users/11250/Desktop/xiaoying/`，仅用于本机定位。仓库：[yysk6/xiaoying](https://github.com/yysk6/xiaoying)，分支main，remote为origin。程序与测试不得硬编码该绝对路径。

## 2. 当前停在哪里

**S1已完成实现与自验，状态ready_for_review，用户验收pending。** 用户于2026-10-29明确授权S1；S0未收到单独验收通过表述，保留pending，不将推进授权伪记为验收。S2及以后未获授权。

S0基线为`576acfbbc000da535f1ee7ae9164029434ed2aed`，此前已核对与远端main一致。S1实现提交为`018903379bde17b7443907a459354ce1f3e0eb2c`。本轮技能配置开始时main工作区干净、单一worktree，HEAD为S1提交、本地origin/main仍为`48874f6c44dcb6bde94106a859e36bd1603bcfc3`；未重新联网核对或推送项目远端。后续文档提交通过`git log -1 --format=%H -- HANDOFF.md`定位。

当前新增工作仅为用户授权的6个开发技能安装和文档规则，详见[开发技能使用约定](docs/09-development-skills.md)与[安装记录](docs/tooling/skills-installation.json)。旧ToolMonsters版handoff已在活动技能目录外备份；当前handoff来自用户指定中文仓库。本次未修改业务代码、未重跑pytest、未调用模型；下述115项通过属于S1已有证据，S2仍未获启动授权。

| 阶段 | 实际开发状态 | 用户验收 | 证据或下一步 |
|---|---|---|---|
| S0 工程基线 | ready_for_review | pending | [S0报告](docs/stages/S0.md)；等待明确验收 |
| S1 契约与领域规则 | ready_for_review | pending | [S1报告](docs/stages/S1.md)；115项含S0回归，开发/正式wheel环境均通过 |
| S2 本地工具 | planned | 未开始 | 以阶段计划为准 |
| S3 存储与幂等 | planned | 未开始 | 以阶段计划为准 |
| S4 离线Agent循环 | planned | 未开始 | 以阶段计划为准 |
| S5 CLI核心链路 | planned | 未开始 | 以阶段计划为准 |
| S6 失败续跑 | planned | 未开始 | 以阶段计划为准 |
| S7 真实模型 | planned | 未开始 | 配置与效果尚未验证 |
| S8 可移植性与交付 | planned | 未开始 | 不得将未执行的平台标为通过 |

## 3. 已完成的工程事实

- Python 3.10.8 / Windows，使用项目内独立.venv，不修改全局环境。
- LangGraph 1.2.18、SQLite checkpointer 3.1.2、Pydantic 2.12.5、HTTPX 0.28.1、pytest 9.0.3组合已安装并通过S0验证。
- requirements.lock固定42个运行依赖；requirements-dev.lock另外固定15个开发/构建依赖。基于Windows/Python 3.10生成，固定版本但未强制校验下载产物哈希。
- S1新增contracts.py/domain.py：严格输入与脚本DTO、NFC/UTC、可注入Clock、输入/候选/脚本指纹、确定性四分项报价、脚本JSON/来源/明确事实规则。不含业务工具分派、Agent、业务数据库或CLI。
- 当前默认pytest有111项S1单测和4项S0回归，合计115项；开发环境115 passed，正式wheel干净环境115 passed，独立测试总数仍为115。S0原始4项结果是历史记录，不覆盖重写。
- checkpoint探针验证“节点一成功、节点二失败、关闭连接重建图后继续，节点一不重跑”；它不证明业务续跑、幂等或真实模型ReAct效果。
- S1重新构建sdist/wheel，全新work/s1-clean从本地wheelhouse离线安装。仓库外cwd以隔离模式导入contracts/domain的实际路径均为新环境site-packages；关闭pytest源路径注入后运行全部115项。两份依赖锁与S0一致。
- 模型调用次数仍为0；A02/A03/A19仅有S1领域断言，完整A01—A23端到端案例与Live仍为NOT_RUN。素材文件读取/校验与工具封装留S2。

当前证据：[S1汇总](examples/tests/stages/S1/summary.json)、[开发JUnit](examples/tests/stages/S1/green-junit.xml)、[干净安装](examples/tests/stages/S1/clean-install.json)、[干净JUnit](examples/tests/stages/S1/clean-junit.xml)、[领域演示](examples/tests/stages/S1/domain-demo.json)。两轮Red分别33 failed/10 passed与42 failed/23 passed，均退出码1；完整命令见S1报告。S0原证据保留在examples/tests/stages/S0/。

S1决策：结构解析与Clock时效检查分开；脚本指纹不含制作档位；报价只计算指定档位，不自动降档；只在外部输入与脚本边界做规格要求的校验，内部函数接收可信参数，不添加通用重试或防御框架。

## 4. 关键文件与使用方法

| 文件或目录 | 用途/注意事项 |
|---|---|
| docs/01-requirements.md | R01—R15需求；未实现不等于可省略 |
| docs/06-contracts.md、contracts/ | 接口和工具契约；改行为先改规格 |
| docs/07-state-and-storage.md | 状态权威、缓存失效、保存事务、幂等、限额 |
| docs/08-development-plan.md | S0—S8范围、逐阶段验收和停止边界 |
| docs/09-development-skills.md | 技能使用时机、项目适配、固定来源和安装证据 |
| docs/stages/S0.md | 已发生的S0自验事实，用户验收待定 |
| docs/stages/S1.md | 当前S1验收入口；范围、两轮Red、Green与正式wheel复核命令 |
| tests/unit/test_environment.py、test_package.py | 4项S0回归 |
| tests/unit/test_contracts.py、test_domain.py | 已从草稿审阅迁入并扩充的111项S1单测；原planned副本已删除 |
| scripts/lock_dependencies.py | 从已安装项目metadata生成精确版本快照；不是求解器 |
| scripts/verify_s0.py | 新环境安装正式wheel并验证，目标路径必须不存在，不自动删除旧环境 |
| content-planner-spec/ | 迁入前历史快照，不是维护源，已被Git忽略 |
| .venv/、work/、dist/ | 本地环境和中间产物，不提交Git；新机器需按README重建 |

已有开发环境中的快速复核（PowerShell）：

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

预期无依赖冲突、115 passed。新机器安装见[README](README.md)，S1正式wheel干净验证见S1报告。verify_s0.py只验证4项S0测试；不要将它当作完整S1验证。已有work/s0-clean/work/s1-clean时使用新环境路径，不删除已有证据。

## 5. 必须保持的设计与开发边界

- 使用karpathy-guidelines、SDD和TDD；先定义可验收行为、测试失败、最小实现，再作必要整理，不提前做下一阶段。
- 项目仅依赖公开第三方库和标准工具；不依赖Codex内部插件/MCP/账户/目录，换编辑器不影响运行。
- 选定模型deepseek-v4-pro，真实接入属于S7。密钥只能从本地环境变量读取，不能从聊天、交接文档、日志或提交中硬编码复制。密钥和API可用性目前未验证。
- 四个业务工具：search_materials、generate_script、estimate_cost、save_plan；两个控制动作：revise_plan、stop_task。程序守住约束，模型选择下一动作。
- 预算是最终活动方案的模拟报价，不是Agent尝试费用或API账单。报价/工期来自合成数据，不能用固定条件分支替模型选择basic。
- completed仅表示本地方案事务提交成功，不表示视频制作/审核/发布完成。原输入的预算、截止时间不可擅自修改。
- mock只验证流程，不能证明真实模型效果；测试、工具执行和用户验收必须分别记录。
- 当前已验证目标为Windows。Linux及其他Python版本未测；Linux不是题目要求或S0验收条件，用户无需安装。后续不要把可移植性说明误作已完成的跨系统验收。

## 6. 下一步允许做什么

S1已交付验收包，当前只允许处理S1验收反馈。**等待用户明确验收S1或明确授权S2后再开展S2。** 无S1技术阻塞，不需要提前调用模型、联网安装或增加系统。

S2后续获准时，先按阶段计划补验收断言并取得Red，再做包内资料、检索、候选修订、Fake脚本生成与工具封装。不接保存、CLI、自主循环或真实模型。已有S1契约与哈希语义有变动时先修规格和必要回归，不静默改口径。

## 7. 更新要求与历史

每阶段完成实现和自验后、交付验收包前，必须更新本文的当前快照和阶段表；用户验收通过、要求修订、发生阻塞或中断交接时再次更新。未更新不能宣称阶段交接完成。Git保留历史，不把本文变成逐条工具流水账。

更新至少覆盖：日期/阶段、实现状态与用户验收、实际范围和改动、关键决策、测试命令/结果/证据、基线提交与已知远端同步情况、未验证项/阻塞、下一步授权边界、恢复/复核命令。未知信息明确写未核对；不得填造密钥、通过结果、个人贡献或自身提交SHA。

| 日期 | 事件 | 状态说明 |
|---|---|---|
| 2026-10-29 | S0工程基线提交并推送 | 576acfb；技术自验通过，用户验收pending |
| 2026-10-29 | 按用户要求建立持续交接文档及强制更新规则 | 仅文档维护，未开始S1、未新增模型调用 |
| 2026-10-29 | 用户明确授权S1；实现并完成自验 | ready_for_review；115项含S0回归，开发/正式wheel环境均通过；用户验收pending，未开始S2 |
| 2026-10-29 | 用户要求安装6个中文开发技能，并写入开发规则 | 已安装并核对固定来源；旧handoff已备份，仅更新规则和交接，S1验收/S2授权状态不变 |

## Suggested skills

下一位代理按[使用约定](docs/09-development-skills.md)选择并读取实际SKILL.md：处理交接用handoff，修改代理文档用writing-for-agents；S2明确获准后先用tdd逐个行为开发，业务阶段交付前用code-review。遇到已观察的疑难缺陷或具体接口问题时，再读取diagnosing-bugs或codebase-design。karpathy-guidelines继续适用。
