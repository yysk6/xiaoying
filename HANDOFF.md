# 项目上下文交接

更新：2026-10-29（北京时间）。首读本文件后核对实际Git；需求与契约以docs/、contracts/为准，历史实现与证据引用阶段报告，不靠本快照推定授权。

## 接手步骤

1. 阅读AGENTS.md、本文件、[阶段计划](docs/08-development-plan.md)、[S2报告](docs/stages/S2.md)。
2. 执行git status --short --branch、git log -3 --oneline、git worktree list、git remote -v；保留已有未提交改动。完成标准是确认实际HEAD、分支、工作区和远端配置。
3. 确认用户最新授权/验收。当前仅S2获准，已交付待验收；下一步处理反馈，S3等待明确授权。

## 当前事实与授权

**S2 ready_for_review，用户验收pending。** 用户明确要求“现在进行s2”，因此完成了本阶段；没有将该授权当作S0/S1单独验收通过。S3—S8未开始。

| 阶段 | 实现/自验 | 用户验收 | 证据 |
|---|---|---|---|
| S0 工程基线 | ready_for_review | pending | [S0](docs/stages/S0.md)，原4项工程证据保留 |
| S1 契约与领域 | ready_for_review | pending | [S1](docs/stages/S1.md)，当时开发/正式wheel各115项通过 |
| S2 本地工具 | ready_for_review | pending | [S2](docs/stages/S2.md)，当前开发/正式wheel各171项通过；双轴审查完成 |
| S3—S8 | planned | 未开始 | [计划](docs/08-development-plan.md)按阶段执行 |

S2实际增加包内资料及校验、别名/tag确定性检索、候选修订、Fake脚本生成、估算与本地状态。未实现数据库保存、业务图、累计额度、CLI、业务恢复或真实HTTP。全项目尚未完成。

## 版本与同步

仓库为[yysk6/xiaoying](https://github.com/yysk6/xiaoying)，main，单worktree。S2起始提交`c83699d1e8417fd917f69da74150604aff5499a1`，开始时工作区干净。S2提交用`git log -1 --format=%H -- docs/stages/S2.md`定位；不要猜测本文自身SHA。

本地origin/main为`48874f6c44dcb6bde94106a859e36bd1603bcfc3`。本轮未联网核对远端，未推送；本地跟踪引用不等于远端实时状态。S0原同步记录与S1提交细节见对应阶段报告。本机Git需要命令级safe.directory时只针对实际项目路径设置，不改全局信任。

## 当前验证与复核

Windows/Python 3.10.8；依赖锁与S2基线相同，42个运行依赖、15个额外开发依赖。当前共171项（56项S2 + 115项既有回归），开发环境和正式wheel干净环境均171 passed、0 failed、0 skipped。两个环境不累计成342项。真实模型调用仍为0；完整A01—A23及Live、Linux/其他Python仍NOT_RUN。

PowerShell项目根目录：

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build --no-isolation
.\.venv\Scripts\python.exe scripts/verify_s2.py --venv work/s2-review --wheelhouse work/s0-wheelhouse
.\.venv\Scripts\python.exe examples/s2_local_tools.py
```

新机器按README安装；无本地wheelhouse时省略该选项，从公开PyPI按锁安装。POSIX路径与安装命令见README，未实测的平台仍标NOT_RUN。verify_s2要求全新环境路径；保留已有work/s0-clean、s1-clean、s2-clean、s2-reviewed，选新名称。旧verify_s0只测4项工程测试，不能当作完整S2验证。

实际记录：[汇总](examples/tests/stages/S2/summary.json)、[开发JUnit](examples/tests/stages/S2/final.xml)、[干净环境命令](examples/tests/stages/S2/clean-install.json)、[干净JUnit](examples/tests/stages/S2/clean-junit.xml)、[Red/Green命令](examples/tests/stages/S2/cycles.jsonl)、[工具演示](examples/tests/stages/S2/local-tools-demo.json)。演示使用固定Clock和显式动作，状态仍running，不是Agent、保存记录或真实模型效果。

双轴审查见[S2-review](docs/stages/S2-review.md)：Standards发现0；Spec初始发现1项synthetic数字类型缺口，真实Red后修复并复核；两个轴未解决项均0。无S2技术阻塞，用户验收仍独立待定。

## 继续时要保持的决策

- 公开边界和本阶段细化以[契约](docs/06-contracts.md)为准；先改规格/验收，再TDD改变行为。遵循karpathy-guidelines，保持最小充分修改。
- LocalTools拥有一份已验证资料快照，每个动作不重读文件；manifest记录原始文件哈希。跨快照恢复核对归S6。
- 档位变化复用脚本、废弃当前估算；素材/brief变化使两者失效，历史保留。每次显式估算新读一次Clock，两档位共用时刻；估算不自动替调用方选basic。
- 调用方提供唯一tool_call_id。工具失败留观察，不自动重试；Fake只提供显式生成响应，planner与额度归S4。
- 预算是活动模拟报价；completed只表示本地事务提交。保存、幂等、唯一约束和保存前期限复核归S3，不能把当前工具测试当作这些链路通过。
- 应用只依赖公开包/标准工具，无Codex运行依赖。DeepSeek官方deepseek-v4-pro接入归S7，密钥只读环境变量；离线测试不联网、不发付费请求。

## 文档与下一步

当前维护入口：docs/01需求、02模块设计、06/contracts契约、07状态/存储、08阶段计划、09技能约定。content-planner-spec/是不维护的历史快照；.venv/work/dist不提交，换机器按README重建。

下一步仅处理S2验收反馈；获得S3明确授权后，先读其范围、细化存储断言，再用真实临时SQLite验证事务/幂等。未获授权不提前实现。

用户验收/要求修订、阶段自验结束、重要阻塞或中断时更新本文件；详细证据继续写阶段报告，Git保留历史。S2交付时已按handoff和writing-for-agents更新本文，根路径覆盖handoff默认临时目录规则，见docs/09。

## Suggested skills

接手按[技能约定](docs/09-development-skills.md)读取实际SKILL.md：交接更新用handoff、代理文档用writing-for-agents、业务实现用tdd（含tests.md/mocking.md）、阶段审查用code-review双轴。karpathy-guidelines持续适用。原因不明的已观察故障才用diagnosing-bugs，具体模块接口问题才用codebase-design；本次S2未触发后两者。
