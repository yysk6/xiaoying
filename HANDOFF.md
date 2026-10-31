# 项目上下文交接

更新：2026-10-31（UTC+08）。开始或恢复先读AGENTS.md、本文件和当前[提交整理记录](docs/stages/SUBMISSION.md)，再核对git status --short --branch、git log -3 --oneline、git worktree list和git remote -v。权威需求/设计/评估为docs01—05与contracts；技术细节在docs06—12。content-planner-spec是忽略的历史快照，docs/archive/pre-submission是整理前归档。

## 当前授权与状态

用户已授权“开始改造，然后全部提交到GitHub”，并再次明确目标https://github.com/yysk6/xiaoying 。本轮材料整理与自验完成，ready_for_review；不得把用户要求提交当成所有历史阶段的accepted。已按授权将此前未提交的自然需求入口、评测器、测试、原始证据和本次文档一起提交并推送，内容提交与远端已核对一致；不是另开自然对话/事实审核开发。

主评审入口为README、docs01—05及examples/README。五篇原稿归档但未删历史；包内data仍是唯一运行资料源，新增说明；原始Trace/输出路径保留。AI贡献记录基于需求/开发/评测会话，强调本人选题/架构取舍、阶段约束、过程纠偏、真实体验反馈及验收设计，代码/提示/测试的AI辅助如实说明，不编造独立手写或开发工时。

## 当前结果

核心20/20通过：16例真实DeepSeek、4例零调用防护，6例明确给定初始premium12夹具；12完成、4正确未完成、4needs_input，88次HTTP。业务集成端到端，不是20例自然终端端到端。每例一个样本，不推断泛化率。

本次提交完整离线复测408 passed、0 failed、154.19秒，examples/tests/submission/pytest-junit.xml；README正常/缺预算/持续失败三条CLI实测通过，cli-smoke.json；pip check通过。23份输出/408条含阶段Trace离线审计通过，21个冻结文件哈希未变。静态链接、当前Git候选文件和8个未推送历史提交的密钥模式扫描零命中，证据在examples/tests/submission/static-checks.json。纯整理不新增业务行为，未再调用付费API或重复业务双轴审查。

此前核心阶段完整复测408/408、155.10秒及最初407/1的原始记录均保留。强杀恢复unknown_planner最初CHECKPOINT_NOT_FOUND，后针对性及两轮完整复测都已通过；当前执行成功，根因未确认，不写成已修复。CORE20评测器三项P2假通过均Red/Green修复并复核，Standards硬违反0，详情docs/stages/CORE20.md。

## Git与发布

本轮起始main/6885d85e6da9a6b4e8e4fe2af5b39ad6cb429711、单worktree；已fetch到origin/main=48874f6，原本ahead8，无远端分叉。已明确授权commit/push到上述仓库，不强推或改写历史。内容提交57ab79fc3dae73ddde723761804b657b42698745已成功推送，git ls-remote确认GitHub main与本地相同。随后仅补记交付/扫描元数据，不改业务或证据；最终分支SHA通过git rev-parse HEAD与ls-remote获取。Git在沙箱中写.git受限；经批准提升执行，命令用-c safe.directory指向当前仓库，不改全局配置。

真实密钥、env文件、虚拟环境、work/build/dist/cache及*.db不提交。evidence.json包含可读持久快照；仅克隆仓库没有runtime.db，物理--recheck须原库。产物审计可只用已提交JSON/Trace，离线pytest重建临时库。

## 运行与复现

PowerShell按README创建.venv、从requirements-dev.lock安装并pip install --no-deps --no-build-isolation -e .，POSIX替换解释器路径，Linux未实测。离线入口python -m content_planner run/show/resume；三类无密钥命令见README，固定scenario Clock可重放历史输入。pytest默认禁网络。

真实交互python scripts/interactive_planner.py，隐藏输入自己的密钥后整理需求并“确认”；Windows可--launch-window。原结构化CLI使用环境变量，交互/专项评测沿用用户明确授权的隐藏stdin/内存注入，无密钥写入env/argv/源码/日志。勿提取其他进程密钥、自动替用户提交真实预测。

新的20例真实运行必须显式python -m scripts.evaluate_core20 --live --key-stdin，会产生费用；本次不追加。历史手工终端上次PID35380，本轮未核查或重启，不当实时状态。

## 已知边界与下一步

自然入口已完成字段抽取/修改/确认，仍是固定模板，不具备结合运行任务自由对话的意图路由；重构未实施。事实审核方案DEFERRED，营销扩写本轮非核心否决项，旧严格内容失败不改写。E07/E08协议拒绝后纠正、E16多余一次已达上限请求保留；程序保证真实状态，不承诺模型路径最短。

Windows正式wheel/仓库外运行有既有证据，Linux/其他Python/并发未测。本次完成交付整理范围，不把S8全部平台验证写成完成。原S7/N阶段验收pending照实保留，不因后续授权伪记accepted。下一步用户审阅交付或提出具体修订；未获新范围不继续功能开发。

## Suggested skills

用karpathy-guidelines控制范围，文档/交接用writing-for-agents/handoff（根HANDOFF覆盖技能临时目录位置）；业务行为才用tdd/tests/mocking，实际缺陷用diagnosing-bugs，接口设计才用codebase-design，业务阶段审查按docs/09做code-review双轴。本轮仅材料整理和验证，没有新业务实现。
