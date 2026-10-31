# 提交材料整理与GitHub交付记录

2026-10-31。用户明确授权按既定方案整理项目，并将全部项目变更提交至https://github.com/yysk6/xiaoying 。本次交付整理与自验完成；独立用户验收不代填accepted。没有扩展业务能力或调用新的付费API。

## 实际范围

- README收敛为环境/安装、三类离线命令、自然语言交互、评审入口与边界说明。
- docs01—05重写为当前需求、实际方案、最新评估、AI协作与本人设计判断、真实复盘；整理前版本保存在docs/archive/pre-submission，注明历史状态并调整链接。
- examples/README直接映射正常、缺预算/截止时间、工具失败、12→8、无解、重复及续跑的输入/输出/Trace/观察/判定；原始证据路径与内容保留。
- 运行数据继续保留包内唯一来源，增加资料说明；未复制JSON或移动应用模块。补充.env.example隐藏输入/环境变量的适用边界，AGENTS规则与已获授权的实际入口一致。
- 此前已开发而未提交的N阶段自然需求入口、评测器、测试、真实证据与阶段报告，按“全部提交”一起纳入；本轮没有重写这些业务实现。
- 原始terminal.txt中的提示符自带尾空格，使用窄范围Git属性保留捕获字节并关闭该类文件的空白检查；未裁剪或重写原始会话输出。

## 实际验证

| 检查 | 结果/证据 |
|---|---|
| 完整离线回归 | 408 passed、0 failed，154.19秒；[本次JUnit](../../examples/tests/submission/pytest-junit.xml) |
| README三类CLI | 正常completed/8/退出0；缺预算needs_input/退出2/无业务库；持续脚本失败incomplete/退出3/失败保留；[实测](../../examples/tests/submission/cli-smoke.json) |
| 入口帮助 | content_planner、evaluate_core20和interactive_planner --help均退出0，不读取密钥或调用模型 |
| 依赖检查 | python -m pip check：No broken requirements found，退出0 |
| 真实证据离线审计 | 23份输出、23份Trace/408条，Schema/参数/理由/摘要/工具结果/公开资料/21个冻结文件均通过；[审计](../../examples/tests/core20/artifact-audit.json) |
| 文档和提交扫描 | 本轮所有Git候选文件、Markdown本地链接及8个待推送历史提交扫描，零密钥模式命中；[静态检查](../../examples/tests/submission/static-checks.json) |
| 差异检查 | git diff --check通过；文档、索引、配置变更不引入新业务测试 |

本轮沿用20例实际评测的20/20通过结果，没有重跑真实API。当前完整离线回归再次全通过，原首次强杀恢复异常仍仅为历史记录，未声称根因已修复。

## 取舍与限制

使用karpathy-guidelines控制改动范围，writing-for-agents/handoff整理主入口与接手记录。按docs/09，纯提交文档维护做差异/链接核对，不重新发起业务双轴审查；既有N阶段/CORE20的审查与实际修订保留。为核对一并提交的既有代码，执行了上述完整回归。

Windows安装/正式wheel的先前验证在[安装记录](../../examples/tests/intake/clean-install.json)。本次无依赖/JSON资源/业务入口变动，未重新做干净安装或Linux验证；Linux仍NOT_RUN。自然入口的字段模板回应、内容扩写质量、单例样本与恢复边界见[评估](../03-evaluation.md)。未执行项不因目录整理而变为通过。

## Git与同步

整理起始基线main/6885d85e6da9a6b4e8e4fe2af5b39ad6cb429711，单worktree。已fetch核对origin/main为48874f6，本地原有8个未推送提交，无远端分叉；保留原历史，不强推。全部项目源码/文档/合成资料/可读证据按用户授权提交；虚拟环境、work、缓存、dist、真实密钥及SQLite工作库不提交。

本记录完成时尚待提交/推送，最终同步情况将由Git核对并补记。最终提交SHA通过git rev-parse HEAD获取，远端通过git ls-remote origin refs/heads/main核对；仓库与分支为上述origin/main。
