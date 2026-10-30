# 项目上下文交接

更新：2026-10-30（UTC+08）。接手先读AGENTS.md、本文件、[S3报告](docs/stages/S3.md)及[阶段计划](docs/08-development-plan.md)，再执行git status --short --branch、git log -3 --oneline、git worktree list、git remote -v。以实际Git和最新用户指令为准，保留已有未提交改动。

## 当前阶段与授权

**S3 ready_for_review，用户验收pending。** 用户明确要求按新开发规则进行S3，已完成实现、自验与双轴审查；这不代填S0—S2的单独验收。S4—S8未开始、未获授权。下一步处理S3反馈，收到明确授权后再开S4。

历史报告：[S0](docs/stages/S0.md)、[S1](docs/stages/S1.md)、[S2](docs/stages/S2.md)。当前范围和详细事实集中在[S3](docs/stages/S3.md)，不在其他文档重复整份验收记录。

## 实现与关键决定

- 已有S1领域规则与S2本地资料/检索/修订/Fake生成/估算；S3新增storage.Repository及LocalTools可选repository/save_plan，SQLite为真实标准库实现。
- requests是不可变输入索引，events保留尝试事实，plans提交行是保存成功权威。保存成功ToolResult与completed补丁和plan原子提交，提交后才更新内存；触发器故障验证整笔回滚。
- 新请求注册检查完整输入和期限；重复ID先比较标准化指纹，原输入过期也读历史。不同输入REQUEST_CONFLICT；同内容方案复用，异内容SAVE_CONFLICT；数据库唯一约束兜底。
- 保存必须有当前revision、匹配脚本、最新可行估算，并在保存时重新报价；旧引用/新超期拒绝，失败保留有效产物。已提交方案优先，成功operation重放读取事件/补丁。
- 接入repository的LocalTools构造时注册请求并查已有提交行；这不是完整service或checkpoint恢复。只有保存动作接入事件，其他动作journal/额度归S4，跨进程恢复/manifest核对归S6。
- 接口、哈希及错误的权威细节见[存储规格S3细化](docs/07-state-and-storage.md#s3实现边界与验收入口2026-10-30实现前)。仅支持单进程串行操作，不支持并发执行同一任务的checkpoint。

## 验证与复现

Windows/Python 3.10.8，最终**193 passed、0 failed、0 skipped**（22项S3新增+171项既有回归），见[最终JUnit](examples/tests/stages/S3/pytest-junit.xml)。真实SQLite行数、外键/唯一约束、触发器回滚、关闭重开查询、保存依赖/时效、输出Schema均有断言。两轴审查发现各0，未解决项0，详细命令与Red/Green集中见S3报告。

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_storage.py tests/unit/test_save_plan.py
.\.venv\Scripts\python.exe -m pytest -q --junitxml=examples/tests/stages/S3/pytest-junit.xml
```

新环境安装与POSIX命令见README；POSIX解释器路径为.venv/bin/python。依赖锁、打包配置、资源和CLI入口未改，本轮未重建wheel或干净环境；旧dist/S2安装证据不能标为S3安装通过。完整A01—A23、Live、Linux/其他Python、S3干净安装仍NOT_RUN，真实模型调用0。无S3技术阻塞。

## Git与同步

仓库[yysk6/xiaoying](https://github.com/yysk6/xiaoying)，main，单worktree。S3起始HEAD为`0a805fdddbf34a3bff5d5c395f3307b63a732e59`，开始时已有用户要求的效率规则改动（HANDOFF、docs/05、docs/08），已保留沿用。阶段提交可通过git log -1 --format=%H -- docs/stages/S3.md定位，不猜测本文自身SHA。

本地origin/main仍为`48874f6c44dcb6bde94106a859e36bd1603bcfc3`，本轮未联网核对、未推送。需要命令级safe.directory时只针对实际项目路径，不改全局信任。

## 开发方式与下一步

用户指出S2流程和证据过量，后续必须按[开发效率约定](docs/08-development-plan.md#开发效率约定s2复盘后生效)推进；原因保留在[复盘](docs/05-retrospective.md#s2开发效率反思2026-10-29用户反馈)。本轮只保留集中阶段报告及最终JUnit，无新增辅助脚本/逐轮证据文件，无安装环境重复验证。

S4获准后按阶段计划推进薄LangGraph decide/dispatch、显式Fake动作、真实观察与累计额度；先细化规格和测试。当前不提前实现图、CLI、真实模型或恢复引擎。项目只使用公开依赖和普通工具，真实deepseek-v4-pro接入归S7，密钥仅从环境变量读取，离线测试不联网。

用户验收/修订、阶段自验结束、重要阻塞或中断时更新本文件。docs/与contracts/为维护源，content-planner-spec/为历史快照；.venv/work/dist不提交，换环境按README重建。

## Suggested skills

按[技能约定](docs/09-development-skills.md)读取所需SKILL.md：karpathy-guidelines持续适用；实现用tdd，阶段交付用code-review双轴，更新交接用handoff及writing-for-agents；出现具体接口设计问题时用codebase-design，原因不明的观察故障才用diagnosing-bugs。S3实际使用前五项及codebase-design，未触发diagnosing-bugs；根HANDOFF路径覆盖handoff默认临时目录位置。
