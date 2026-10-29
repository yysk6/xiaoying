# 项目上下文交接

更新日期：2026-10-29（北京时间）。本文件是接手开发的首读入口，记录当前事实和允许推进的范围；规格以docs/与contracts/为准，历史细节以阶段报告和Git记录为准。

## 1. 接手后的第一步

1. 阅读AGENTS.md、本文件、[阶段计划](docs/08-development-plan.md)和当前阶段报告。
2. 执行`git status --short --branch`、`git log -3 --oneline`、`git remote -v`，核对实际工作区。不要仅依据本文假定HEAD、权限或环境未变化。
3. 检查当前阶段是否已获用户明确验收；未验收不得进入下一阶段。不要覆盖接手时已有的未提交改动。

项目位置：`C:/Users/11250/Desktop/xiaoying/`，仅用于本机定位。仓库：[yysk6/xiaoying](https://github.com/yysk6/xiaoying)，分支main，remote为origin。程序与测试不得硬编码该绝对路径。

## 2. 当前停在哪里

**S0已完成技术自验并推送，状态ready_for_review；用户验收仍为pending。S1未开始。** 用户询问Linux不构成S0验收通过；新增交接文档的要求也不构成继续S1的授权。

已验证的S0基线提交：`576acfbbc000da535f1ee7ae9164029434ed2aed`。此前已核对该SHA与远端main一致。本轮交接/规则更新属于文档变更，不产生新的业务测试结论；最新文档提交通过`git log -1 --format=%H -- HANDOFF.md`查询，避免嵌入自身提交SHA。

| 阶段 | 实际开发状态 | 用户验收 | 证据或下一步 |
|---|---|---|---|
| S0 工程基线 | ready_for_review | pending | [S0报告](docs/stages/S0.md)；等待明确验收 |
| S1 契约与领域规则 | planned | 未开始 | 有未激活草稿，不是通过的测试 |
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
- src/content_planner/__init__.py仅包说明和版本0.1.0，没有领域代码、业务工具、Agent循环、业务数据库表或CLI。
- 默认pytest有4项工程测试。开发环境4 passed；正式wheel的干净环境中同样4 passed，独立用例总数仍为4。
- checkpoint探针验证“节点一成功、节点二失败、关闭连接重建图后继续，节点一不重跑”；它不证明业务续跑、幂等或真实模型ReAct效果。
- 已构建sdist/wheel，并通过本地wheelhouse离线安装。仓库外cwd以隔离模式导入的模块来自干净环境site-packages。
- S0模型调用次数为0；A01—A23业务案例与Live评估尚未通过。

证据入口：[汇总](examples/tests/stages/S0/summary.json)、[开发环境JUnit](examples/tests/stages/S0/green-junit.xml)、[干净安装结果](examples/tests/stages/S0/clean-install.json)、[干净环境JUnit](examples/tests/stages/S0/clean-junit.xml)。完整命令和Red记录见S0报告。

## 4. 关键文件与使用方法

| 文件或目录 | 用途/注意事项 |
|---|---|
| docs/01-requirements.md | R01—R15需求；未实现不等于可省略 |
| docs/06-contracts.md、contracts/ | 接口和工具契约；改行为先改规格 |
| docs/07-state-and-storage.md | 状态权威、缓存失效、保存事务、幂等、限额 |
| docs/08-development-plan.md | S0—S8范围、逐阶段验收和停止边界 |
| docs/stages/S0.md | 已发生的S0自验事实，用户验收待定 |
| tests/unit/test_environment.py、test_package.py | 当前默认收集的4项S0测试 |
| tests/planned/domain_cases.py | S1测试草稿；不收集、不算通过或跳过，S1获准后再激活 |
| scripts/lock_dependencies.py | 从已安装项目metadata生成精确版本快照；不是求解器 |
| scripts/verify_s0.py | 新环境安装正式wheel并验证，目标路径必须不存在，不自动删除旧环境 |
| content-planner-spec/ | 迁入前历史快照，不是维护源，已被Git忽略 |
| .venv/、work/、dist/ | 本地环境和中间产物，不提交Git；新机器需按README重建 |

已有开发环境中的快速复核（PowerShell）：

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

预期无依赖冲突、4 passed。新机器安装、构建和干净验证见[README](README.md)。已有work/s0-clean时不要复用该路径运行新建环境脚本，使用新的--venv路径，不删除已有证据。

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

当前允许继续处理S0验收反馈和文档维护；**等待用户明确验收S0或明确授权S1后再进入S1**。目前无S0技术阻塞，不需要为此提前调用模型或安装其他系统。

S1获准后，仅做输入契约、严格预算/时间校验、Clock、指纹、确定性报价与脚本规则；先审阅/激活S1草稿并取得真实Red。不接数据库、CLI、模型HTTP或业务执行图，不用之前的ModuleNotFoundError冒充完整业务测试证据。

## 7. 更新要求与历史

每阶段完成实现和自验后、交付验收包前，必须更新本文的当前快照和阶段表；用户验收通过、要求修订、发生阻塞或中断交接时再次更新。未更新不能宣称阶段交接完成。Git保留历史，不把本文变成逐条工具流水账。

更新至少覆盖：日期/阶段、实现状态与用户验收、实际范围和改动、关键决策、测试命令/结果/证据、基线提交与已知远端同步情况、未验证项/阻塞、下一步授权边界、恢复/复核命令。未知信息明确写未核对；不得填造密钥、通过结果、个人贡献或自身提交SHA。

| 日期 | 事件 | 状态说明 |
|---|---|---|
| 2026-10-29 | S0工程基线提交并推送 | 576acfb；技术自验通过，用户验收pending |
| 2026-10-29 | 按用户要求建立持续交接文档及强制更新规则 | 仅文档维护，未开始S1、未新增模型调用 |
