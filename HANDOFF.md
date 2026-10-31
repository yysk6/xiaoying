# 项目上下文交接

更新：2026-10-31（UTC+08）。接手先读AGENTS.md、本文件、[S6报告](docs/stages/S6.md)及[阶段计划](docs/08-development-plan.md)，再核对git status --short --branch、git log -3 --oneline、git worktree list、git remote -v。保留已有改动，以实际Git及最新用户指令核对范围。

## 当前授权与进展

**S6 ready_for_review，用户验收pending。** 用户授权“进行s6”；实现、自验、双轴审查及最终产物验证完成，停在验收包。前阶段验收不代填，S7/S8未开始/未授权。仍为LangGraph/Python3.10.8路线，未引入Deep Agents，依赖锁未变。

历史结果见[S5](docs/stages/S5.md)及其前阶段引用。S6设计、真实Red/Green、诊断、案例、审查和限制集中见[S6](docs/stages/S6.md)，本文件只保留继续工作的必要信息。

## 当前实现与关键决定

- CLI已有run/show/resume及JSON/Markdown/Trace。普通重复run只读；显式resume先核对原请求/提交事实、manifest、额度和可恢复原因。已完成任务无需新场景/模型配置。
- 未完成Mock续跑需后续显式场景或注入ModelClient；不能改变原输入/backend/model/manifest。工具瞬时失败或MODEL_UNAVAILABLE可续跑；资料/约束停止、非法脚本、协议/执行上限等拒绝，原任务不改写。
- 框架恢复检查next **或tasks**，用invoke(None)应用真实pending writes/节点；正常可恢复结束从下一次decide继续。不能只看next：已完成节点持久写入可能令next为空。
- 已提交plan优先；坏checkpoint不抹掉方案，返回completed+CHECKPOINT_UNAVAILABLE。已持久模型/工具结果重放，不再次执行；保存失败事件缺完整补丁时补齐原结果和当前失败引用。
- 模型/动作日志按kind及started operation关联结束事件，避免外部合法ID和内部script操作碰撞，保留原tool_call_id。结果未知的started标interrupted；新recovery尝试照常计数，不承诺外部API exactly-once。
- 恢复保留候选/产物/历史/决策序号及累计限额（模型32、动作24、候选4、同键可重试失败2）。换档位复用脚本，换brief/素材失效，必须重估并保存前重新核对截止时间。

权威规格为docs/06、[docs/07恢复细化](docs/07-state-and-storage.md#s6接通细化实现前2026-10-31)和contracts。HANDOFF是开发交接，不是应用记忆。

## 验证与复现

Windows/Python3.10.8，最终**288 passed、0 failed、0 skipped**（28项S6新增+260回归），见[最终JUnit](examples/tests/stages/S6/pytest-junit.xml)。首次全量285 passed/2 failed暴露异步checkpoint窗口，新增确定性回归并修复后重跑；不改写初次失败为通过。诊断过程及测试夹具的flush固定见阶段报告。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/acceptance/test_resume.py
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml=examples/tests/stages/S6/pytest-junit.xml
.\.venv\Scripts\python.exe -m content_planner run --input examples/mock/A12/input.json --mock-scenario examples/mock/A12/scenario.json --db work/resume-demo.db --output-dir work/resume-before
.\.venv\Scripts\python.exe -m content_planner resume --request-id s6-A12 --mock-scenario examples/mock/A12/continuation.json --db work/resume-demo.db --output-dir work/resume-after
```

演示用新数据库；初次预期incomplete/退出3，后续completed/退出0。POSIX命令见README。普通pytest网络禁用；Fake仅验证程序，真实API调用0，token/美元成本未知为null。

实际[A12](examples/mock/A12/)失败续跑：方案0→1、事件18→32、累计9模型/7动作；[A13](examples/mock/A13/)真实保存后os._exit(91)，新进程恢复仍1方案/22事件，零新增模型/工具。原输入、固定Clock/场景、前后输出及Trace/run记录均保留。

最终wheel已重建并在S5原干净公开运行环境离线重装（锁未变，未新建重复环境）；非仓库cwd、移除宿主/模型变量、python -I验证续跑链及最终pending-writes恢复窗口，Schema/UTF-8通过。[安装记录](examples/tests/stages/S6/clean-install.json)区分原/最终产物hash与实际检查。未重复干净环境全套pytest。Linux/其他Python、真实DeepSeek HTTP/效果及S8完整交付仍NOT_RUN；不能称完整项目已验收。

审查：Standards硬违反0/判断项0；Spec初始3项P2均真实Red后修复复核；自验的pending-writes缺陷另作独立复核，两轴最终未解决0。无已知技术阻塞，用户验收仍独立pending。

## Git、同步与下一步

仓库[yysk6/xiaoying](https://github.com/yysk6/xiaoying)，main单worktree；S6起始HEAD `feb17bc71a2bdc55f52bd04619b0d06c9bcff5ec`，工作区干净。阶段提交用`git log -1 --format=%H -- docs/stages/S6.md`定位，不猜本文自身SHA。已知本地origin/main仍为48874f6，本轮未fetch/推送，不代表最新远端事实。案例run.json标注起始基线+工作区修改状态。

下一步处理S6反馈；收到S7明确授权后才接DeepSeek官方deepseek-v4-pro的HTTP协议测试、真实探针与效果评估。没有提前付费调用或配置密钥。遗留.venv-deepagents不参与运行，不删除旧环境。当前work/s6-evidence保存演示库，work/dist不提交。

沿用[效率约定](docs/08-development-plan.md#开发效率约定s2复盘后生效)：逐行为TDD，集中报告、一份最终JUnit，按实际变化补验；不增加逐轮证据或一次性辅助脚本。docs/与contracts/为维护源，content-planner-spec/为历史快照。应用不依赖Codex/MCP/账户/开发机目录。

用户验收/修订、阶段自验结束、重要阻塞或中断时更新本文件，历史留在阶段报告/Git。

## Suggested skills

按[技能约定](docs/09-development-skills.md)读取实际SKILL.md：karpathy-guidelines持续适用；业务实现用tdd（tests.md/mocking.md）、具体接口用codebase-design；阶段交付用code-review双轴；原因不明故障用diagnosing-bugs；交接用handoff/writing-for-agents。本轮实际使用以上七项；根HANDOFF路径覆盖handoff默认临时目录规则。
