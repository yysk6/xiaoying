# 项目上下文交接

更新：2026-10-30（UTC+08）。接手先读AGENTS.md、本文件、[S4报告](docs/stages/S4.md)及[阶段计划](docs/08-development-plan.md)，再执行git status --short --branch、git log -3 --oneline、git worktree list、git remote -v。保留已有改动，以实际Git和最新用户指令核对范围。

## 当前授权与进展

**S4 ready_for_review，用户验收pending。** 用户明确决定不接入Deep Agents，继续现有路线并授权下一阶段S4；本阶段实现、自验、双轴审查完成，停在验收包。前阶段单独验收不代填，S5—S8未开始/未授权。

历史证据保留在[S0](docs/stages/S0.md)、[S1](docs/stages/S1.md)、[S2](docs/stages/S2.md)、[S3](docs/stages/S3.md)。最新范围、Red/Green、审查和限制集中见[S4](docs/stages/S4.md)。

## 当前实现与决定

- 保留LangGraph/Python 3.10.8路线，无Deep Agents依赖或锁文件变化。前轮中断尝试留下的.venv-deepagents不参与开发/运行；本轮只使用原.venv，保留旧环境。
- PlanningAgent.run接通真实decide/dispatch图、LocalTools六动作、SQLite业务事件和SqliteSaver。Fake显式提供决策/故障列表，不按预算或观察内置正确动作。
- requests保存不可变输入，plans提交行优先于旧checkpoint；事件started是累计调用权威。模型32/动作24的计数检查和started写入同一短事务；候选4、同键可重试失败2次、连续协议错误2次、图80步。
- 失败/拒绝配真实工具反馈；多调用整组不执行，合法ID逐个配对，无法构成合法协议立即停。模型推理字段在持久化前去除，提示版本集中在prompts常量。
- 任务记忆保存当前候选/产物、当前适用的失败引用及完整历史。给模型的历史按完整交互组裁剪，旧组为程序摘要；完整事实仍在checkpoint/events，没有额外摘要模型或跨任务长期记忆。
- 重复run只读已有checkpoint；提交事实优先。此入口不提供业务resume，跨进程恢复/manifest校验仍归S6。完整TaskResult/Trace/CLI归S5，真实DeepSeek HTTP及效果归S7。

权威规格：[架构与上下文](docs/02-solution.md#s4任务记忆与上下文边界实现前2026-10-30)、[状态与额度](docs/07-state-and-storage.md#s4接通范围实现前2026-10-30)、docs/06及contracts。HANDOFF属于开发交接，不进入应用运行记忆。

## 验证与复核

Windows/Python 3.10.8；最终**222 passed、0 failed、0 skipped**（29项S4新增+193项既有回归），见[最终JUnit](examples/tests/stages/S4/pytest-junit.xml)。初次全量后因新增当前失败引用修正而重跑，保留最终结果。真实工具、数据库和checkpoint验证，普通测试网络禁用，真实API调用0。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/unit/test_agent.py
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml=examples/tests/stages/S4/pytest-junit.xml
```

新环境安装与POSIX命令见README，解释器路径替换为.venv/bin/python。依赖/打包/资源/CLI入口未改，本轮未重建wheel或干净环境；旧dist不能作为S4产物。完整A01—A23、Live、CLI、跨进程业务resume、Linux/其他Python、S4干净安装仍NOT_RUN。

审查：Standards初始判断项1（提示版本来源分散），Spec初始P2 1（非法content），均已修正复核；针对关键修正5项测试通过，当前失败引用另作核对，两个轴未解决均0。无当前技术阻塞，用户验收仍独立待定。

## Git与同步

仓库[yysk6/xiaoying](https://github.com/yysk6/xiaoying)，main单worktree；S4起始HEAD为`e032837ab9ce1892ff29ba977016cd641305bb70`，tracked工作区干净。阶段提交用git log -1 --format=%H -- docs/stages/S4.md定位；不猜本文自身SHA。

本地origin/main仍为`48874f6c44dcb6bde94106a859e36bd1603bcfc3`，本轮未联网核对或推送。Git如需safe.directory仅在命令级指定实际项目路径。

## 下一步与开发方式

下一步处理S4反馈，收到S5明确授权后才接CLI/run/show、完整结果与Trace导出。沿用[开发效率约定](docs/08-development-plan.md#开发效率约定s2复盘后生效)：围绕业务行为TDD，集中记录，按变化验证，不添加逐轮证据文件或一次性辅助脚本。当前只新增集中阶段报告与最终JUnit。

项目只依赖公开包和普通CLI；密钥仅从环境变量读取，真实模型为DeepSeek官方deepseek-v4-pro。离线开发不发付费请求；运行不能依赖Codex或开发机专用目录。docs/与contracts/为维护源，content-planner-spec/为历史快照，.venv/work/dist不提交。

用户验收/修订、阶段自验结束、重要阻塞或中断时更新本文件；具体实现和历史留在阶段报告/Git。

## Suggested skills

按[技能约定](docs/09-development-skills.md)读取实际SKILL.md：karpathy-guidelines持续适用；实现用tdd（含tests.md/mocking.md），阶段交付用code-review双轴，交接用handoff/writing-for-agents；具体接口问题用codebase-design，原因不明故障才用diagnosing-bugs。本轮实际使用前五项及codebase-design，未触发diagnosing-bugs；根HANDOFF路径覆盖handoff默认临时目录规则。
