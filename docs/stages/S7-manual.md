# S7 用户手工预测入口记录

2026-10-31（UTC+08）。用户要求启动、注入密钥并提供可自行输入的端到端预测入口。项目原有CLI没有HTTP服务，因此新增薄控制台适配，不增加网页、HTTP服务、新依赖或业务决策。该请求作为S7手工验收支持，不启动S8，也不替用户验收此前阶段。

## 实现与使用

[interactive_planner.py](../../scripts/interactive_planner.py)逐行接收原Request JSON，直接使用service.run_task、真实模型、实际工具、LangGraph、SQLite及结果导出。支持show/resume/exit；JSON错误可继续，缺字段走既有needs_input，重复输入仍只读。终端打印方案、真实步骤状态、用量及导出目录。

Windows启动：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/interactive_planner.py --launch-window
```

POSIX对应命令（未实测）：

```sh
.venv/bin/python scripts/interactive_planner.py
```

密钥由隐藏终端输入直接进入内存。Windows父进程通过匿名stdin管道交给独立可见子终端，随后子进程恢复CONIN/CONOUT供用户输入；不放入环境变量、参数或文件。默认数据库work/manual/runtime.db、导出work/manual/runs/<request_id>/，与评测库分开。

在标题“内容活动规划 - DeepSeek 手工预测”的终端，JSON提示后输入一整行并回车。示例仅适用于当前日期之前仍未来的deadline，之后使用者应更新：

```json
{"request_id":"manual-001","topic":"影芽剪辑字幕功能推广","budget_units":10,"deadline_at":"2026-11-01T23:00:00+08:00"}
```

新主题/预算/截止时间用新ID；相同JSON可检查幂等。预算改5且新ID可观察无解；删除budget_units或deadline_at可观察缺失提示。普通模型可能直接选8，这属于有效决策，不会强制先选premium12。show manual-001读取结果，exit关闭客户端/终端会话。仍保留前轮发现的脚本事实性缺口，本次未修改提示或模型输出规则。

## 实际启动与验证

Windows独立终端已实际启动，业务子进程PID32492；就绪文件work/manual/session.json显示ready、deepseek-v4-pro、api_key_configured=true、启动http_attempts=0。只读Get-Process确认存活，数据库当时尚不存在，未替用户发出真实预测。启动核查快照见[记录](../../examples/tests/manual-interactive/startup.json)，其中不含密钥；会话是否仍在运行以实时进程/状态为准。

原启动器在venv重定向器PID与实际业务PID不同时误报“就绪未确认”，子终端仍正常运行，后经独立进程/状态核查确认。修复后源码使用与密钥无关的launch_id关联，并避免子进程继承父PTY输出句柄；该修复通过离线回归，本轮未为验证新启动器重复弹窗或重启当前用户会话。

## 测试与审查

按docs/06契约和docs/03预期先行，使用karpathy-guidelines、tdd（既有公开service/ModelClient/Clock及真实临时SQLite）、codebase-design、code-review双轴、writing-for-agents/handoff。

- 缺截止时间交互案例：初始模块缺失仅记搭建Red；实现后needs_input、missing_fields准确、0模型调用、无数据库写入，实际导出可读。
- 完整输入、无效JSON后继续、重复输入及show：在真实SQLite和Fake边界验证completed、8 units、5个实际步骤；重复/show后仍只一次脚本、5次决策。首次即通过，作为验证，不编造Red。
- Spec审查发现就绪JSON并发读取P2：空文件使JSONDecodeError，真实Red后增加读取容忍及原子替换，Green。
- Windows启动实测发现venv PID不同：参数化不同PID反例真实Red后改launch_id，Green。Windows特有启动测试在其他平台标skip，未声称Linux已测。

最终交互4项测试通过。相关回归覆盖交互入口、既有CLI验收和HTTP适配器，**83 passed、0 failed/errors/skipped，50.70秒，退出0**，见[最终JUnit](../../examples/tests/manual-interactive/pytest-junit.xml)。命令为`python -m pytest -q tests/acceptance/test_interactive.py tests/acceptance/test_cli.py tests/unit/test_deepseek.py --junitxml=examples/tests/manual-interactive/pytest-junit.xml`。本轮只改变独立脚本入口，没有重跑不相关的恢复/领域全仓测试；此前342项是专项评测的历史完整回归，不冒记为本轮全量。

Standards初审硬违反0、判断项0。Spec初审就绪文件竞态1项P2已修复并复核；PID实测问题也已补回归并复核，最终未解决审查项0。密钥未进入状态文件、进程参数或日志。未重建wheel，未做新的付费预测、Linux或S8验证。
