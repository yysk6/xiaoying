# 项目上下文交接

更新：2026-10-31（UTC+08）。接手先读AGENTS.md、本文件、[S5报告](docs/stages/S5.md)及[阶段计划](docs/08-development-plan.md)，再核对git status --short --branch、git log -3 --oneline、git worktree list、git remote -v。保留已有改动，以实际Git和最新用户指令核对范围。

## 当前授权与进展

**S5 ready_for_review，用户验收pending。** 用户明确“开始s5”，本阶段实现、自验、双轴审查及安装验证完成，停在验收包。前阶段单独验收不代填，S6—S8未开始/未授权。用户已决定不接入Deep Agents，继续原LangGraph路线。

历史见[S0](docs/stages/S0.md)、[S1](docs/stages/S1.md)、[S2](docs/stages/S2.md)、[S3](docs/stages/S3.md)、[S4](docs/stages/S4.md)。S5范围、Red/Green、实际案例、审查和限制统一见[S5](docs/stages/S5.md)，本文件只保留继续工作的必要快照。

## 当前实现与决定

- Python3.10.8/LangGraph/SQLite路线及依赖锁不变；无Deep Agents依赖。遗留.venv-deepagents不参与开发/运行，不删除旧环境。
- CLI开放run/show与JSON/Markdown/Trace导出，stdout/stderr及文件UTF-8。Mock为显式场景，可指定固定Clock；省略场景为包内固定M01/basic示例，使用SystemClock。不是模型智能效果证据。
- 新请求先严格校验；缺失/格式错误不创建任务。已有请求先比较输入指纹，重复run/show只读历史及已提交方案，不加载新场景/资料或再执行，过期不覆盖历史成功。冲突返回REQUEST_CONFLICT。
- TaskResult/attempt/usage/Trace来自持久事实，提交方案优先。未完成Markdown保留当前有效估算缺口；活动表显示北京时间，四活动仍为planned。导出失败不回滚方案，completed+EXPORT_FAILED，show可重导出。
- S4任务记忆、完整历史及按完整交互组裁剪保持；模型32/动作24/候选4/同键重试2/协议错误2/图80。细节见docs/02、06、07。Trace不导出planner原响应、推理字段或内部状态补丁。
- 不提供业务resume或真实HTTP；CLI选择deepseek/resume会明确报错，不假装可用。跨进程恢复/manifest校验属S6，真实DeepSeek接入与效果属S7。

## 验证与复现

Windows/Python3.10.8，最终**260 passed、0 failed、0 skipped**（38项S5新增+222回归），见[最终JUnit](examples/tests/stages/S5/pytest-junit.xml)。259通过后干净安装发现Windows默认编码缺陷，补真实Red修复，最终重跑260并重建wheel；不复用旧产物结论。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/acceptance/test_cli.py
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml=examples/tests/stages/S5/pytest-junit.xml
.\.venv\Scripts\python.exe -X utf8 -m content_planner run --input examples/mock/A01/input.json --mock-scenario examples/mock/A01/scenario.json --db work/demo.db --output-dir work/demo-output
.\.venv\Scripts\python.exe -X utf8 -m content_planner show --request-id s5-A01 --db work/demo.db --output-dir work/demo-show
```

POSIX对应命令见README，解释器替换为.venv/bin/python。普通pytest网络禁用，模型为Fake，真实API调用0。

五组实际证据见examples/mock/A01（正常）、A02（缺预算）、A08（持续生成失败）、A04（12→8并复用脚本）、A10（重复A01）；每组含实际input/scenario/output/plan/trace/run，固定Clock来源已注明。A02无持久事件、空Trace不伪造执行。

最终正式wheel在新建work/s5-clean中由公开锁离线安装，非仓库cwd、移除宿主/模型环境、python -I实际验证默认场景run/重复run/show和Schema，均通过。[安装记录](examples/tests/stages/S5/clean-install.json)保留首轮编码失败及最终产物hash。干净环境未重复全套pytest；Linux/其他Python、S6恢复、S7 Live及完整A01—A23验收仍NOT_RUN/未全部完成。不能把S5局部安装验证当S8整体通过。

审查：Standards硬违规0/判断项0；Spec初始P2两项（Markdown缺口、时区）均真实Red后修复，独立目标复核2 passed；两轴未解决0。编码入口修正另作Standards复核，无当前技术阻塞；审查不替代用户验收。

## Git与同步

仓库[yysk6/xiaoying](https://github.com/yysk6/xiaoying)，main单worktree；S5起始HEAD为`a45595cbf1a4c13df11956e2916f76b357c7c925`，工作区干净。阶段提交用`git log -1 --format=%H -- docs/stages/S5.md`定位，不猜本文自身SHA。

已知本地origin/main仍为`48874f6c44dcb6bde94106a859e36bd1603bcfc3`，本轮未fetch/推送，不代表最新远端事实。Git需要safe.directory时仅在命令级指定实际项目路径。示例run.json记录起始基线+工作区修改状态，不能把它当运行时已提交新版本。

## 下一步与开发方式

下一步处理S5反馈；收到S6明确授权后再实现resume、跨进程业务恢复、有效产物复用、manifest核对及累计额度。当前不得自动开始S6或付费API探针。

沿用[效率约定](docs/08-development-plan.md#开发效率约定s2复盘后生效)：逐业务行为TDD，集中报告、一份最终JUnit，按变化验证；只有入口/资源/依赖/验收需要时验证最终安装。S5复用现有CLI工具和内联命令，无新增一次性记录脚本。

docs/与contracts/是维护源，content-planner-spec/为历史快照。.venv/work/dist不提交。程序只用公开包、标准库、Git/普通CLI，不能依赖Codex/MCP/账户或开发机专用路径；HANDOFF不是应用记忆。密钥仅从环境变量读取，模型固定DeepSeek官方deepseek-v4-pro；离线不发付费请求。

用户验收/修订、阶段自验结束、重要阻塞或中断时更新本文件，详细历史留在阶段报告/Git。

## Suggested skills

按[技能约定](docs/09-development-skills.md)读取实际SKILL.md：karpathy-guidelines持续适用；实现用tdd（tests.md/mocking.md）、具体接口问题用codebase-design；阶段交付用code-review双轴；交接用handoff/writing-for-agents。原因不明故障才用diagnosing-bugs。本轮使用前六项，编码缺陷已定位、用聚焦TDD修正，未执行diagnosing-bugs完整流程。根HANDOFF路径覆盖handoff默认临时目录规则。
