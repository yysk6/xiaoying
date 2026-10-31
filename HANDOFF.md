# 项目上下文交接

更新：2026-10-31（UTC+08）。接手先读AGENTS.md、本文件、[S7报告](docs/stages/S7.md)及[阶段计划](docs/08-development-plan.md)，再核对git status --short --branch、git log -3 --oneline、git worktree list、git remote -v；保留已有改动，以实际状态和最新用户授权为准。

## 当前授权与进展

**S7 ready_for_review，用户验收pending。** 用户授权“进行s7”及测试直接使用提供的密钥；实现、自验、双轴审查和安装验证完成。前阶段不代填accepted，S8未开始。Python3.10.8/LangGraph路线保持，无Deep Agents、依赖锁未变。

完整范围、Red/Green、审查修复、真实样本与限制集中见[S7](docs/stages/S7.md)，历史恢复实现见[S6](docs/stages/S6.md)。本文件保存接手必要事实，不是应用记忆。

## 当前实现与关键决定

- CLI run/show/resume及JSON/Markdown/Trace已接通。run默认mock，--backend deepseek使用官方HTTP；不回退、不自动重试、不跟随重定向。应用只读环境变量，固定deepseek-v4-pro、thinking关闭。
- HTTP保留工具配对与usage，脚本JSON交领域校验；错误不记录认证头/provider body/推理。AUTH/配置/协议错误停止；瞬时script失败交planner决定后续。任一未知用量令相应总token为null，美元费用未知null；报价units独立。
- 重复run/show/已完成resume只读，无需当前密钥。冲突输入返回本次选择backend；未完成live resume按原backend读取配置。服务关闭自己创建的HTTP客户端，外部注入由调用者管理。
- S6恢复检查next或tasks；持久结果重放不重复执行/计数。未知started标interrupted，新尝试累计额度；提交plan优先，不承诺API exactly-once。准入、额度、manifest和失效规则见docs/07及S6报告。

权威规格在docs/和contracts/；content-planner-spec/是历史快照。应用不依赖Codex/MCP/账户/开发机目录。

## 验证与真实证据

最终**328 passed、0 failed、0 skipped，143.44秒**，见[JUnit](examples/tests/stages/S7/pytest-junit.xml)。40项S7新增+288项既有回归；普通pytest禁网络。Standards硬违反0/判断项0；Spec两项P2均修复复核，最终未解决0。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/unit/test_deepseek.py
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml=examples/tests/stages/S7/pytest-junit.xml
# 下列评估需要自行配置环境密钥，会发真实付费请求：
.\.venv\Scripts\python.exe scripts/evaluate_live.py --live
```

用户提供的密钥仅隐藏输入到临时测试进程环境，两个进程均已结束；未落盘/回显、未配置持久环境，主shell无密钥。后续live评估由用户自行配置，不从文档找密钥。

[成功真实运行](examples/live/S7/20261031T083150Z-f46bcbe4/summary.json)：工具/回传/JSON探针通过；L01正常保存，L02观察首次script注入失败后自主重试，L03预算10直接选basic8，均completed。每例仅1样本，L03不是12→8重规划；L04 NOT_RUN。成功运行22次HTTP尝试；L02为8逻辑尝试/7 HTTP，包含一次HTTP前注入失败，token未知null；美元费用全部null。初次沙箱socket权限失败另保留[记录](examples/live/S7/20261031T083016Z-4cc7f1b1/summary.json)，1次尝试；保留全部结果。元数据事后补齐已注明，业务Trace未改写，不代表最终提交经过重复付费运行。

最终wheel在原S5公开运行环境离线重装、非仓库cwd/python -I验证安装后的Mock CLI、DeepSeek适配器离线完整图、配置缺失/历史恢复、Schema/UTF-8和pip check；[安装记录](examples/tests/stages/S7/clean-install.json)保留hash/命令。验证器漏本地Schema registry的初次失败修正后通过，应用未变。未重复干净运行环境全套pytest或付费调用，Linux/其他Python及S8收尾仍NOT_RUN。

## Git、同步与下一步

仓库[yysk6/xiaoying](https://github.com/yysk6/xiaoying)，main单worktree；S7起始HEAD为0a8ed602c2e0bd87abb1f02d59815afc77d7eaed且工作区干净。阶段提交用git log -1 --format=%H -- docs/stages/S7.md定位，不猜本文自身SHA。已知本地origin/main为48874f6，本轮未fetch/推送，不代表最新远端事实。

下一步仅处理S7验收/反馈；收到S8明确授权才做完整交付归档、覆盖缺口与平台限制核对。无已知技术阻塞。沿用[效率约定](docs/08-development-plan.md#开发效率约定s2复盘后生效)：按行为TDD、集中报告、一份最终JUnit、按变化补验，不新建重复环境或付费样本。work/s7-live.db为本地案例库，dist/环境不提交；遗留.venv-deepagents不参与运行，不删除旧环境。

用户验收/修订、阶段自验结束、重要阻塞或中断时更新本文件，历史留在阶段报告/Git。

## Suggested skills

按[技能约定](docs/09-development-skills.md)读取实际SKILL.md：karpathy-guidelines持续适用；业务实现用tdd，接口选择用codebase-design，阶段交付用code-review双轴，原因不明故障用diagnosing-bugs，交接用handoff/writing-for-agents。S7实际用了除diagnosing-bugs之外的上述技能；根HANDOFF路径覆盖handoff默认临时目录规则。
