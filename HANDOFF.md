# 项目上下文交接

更新：2026-10-31（UTC+08）。恢复先读AGENTS、本文件及[评估维护记录](docs/03-evaluation.md#当前限制与维护记录)，再核对Git/worktree/remote。权威规格为docs五篇和contracts；content-planner-spec为忽略的历史快照。

## 最新授权与实际范围

用户授权“开始合并”，后明确仅改文档，质疑额外双轴复核。已收回扩展范围：评测器及评测脚本恢复基线，新增测试和对应新报告全部移除。曾运行的额外审查/测试不作为当前交付验证；完整回归在请求停止前已经结束，不声称已中止。后续纯文档只检查结构/链接/差异，不再自动追加审查或全量测试。

docs由35文件合为5：01需求/输入/成功标准；02工具契约/状态/流程/框架取舍；03预期/实际结果/Trace/失败复测/历史审查；04AI协作/个人判断/开发方法；05复盘/未实施方案。重复历史正文保存在Git，不另建stages/archive。全部30项删除或迁移见[归并映射](examples/tests/docs-merge/merge-map.json)；技能安装JSON移至examples/tests/tooling。README、examples索引、AGENTS和测试文档指针已同步。

## 验证与证据

本轮只记录文档结构、内部链接、差异及敏感内容检查，最终见examples/tests/docs-merge/static-checks.json。应用代码、测试代码和原始模型input/output/Trace/source/assessment无改动，零付费HTTP。

原始核心20/20仍成立：16真实模型场景、4零调用防护、6初始premium夹具，88HTTP；12完成/4正确未完成/4needs_input。属于业务集成端到端，每例单样本，不是20例自然终端E2E。历史完整408通过154.19秒见examples/tests/submission/pytest-junit.xml；本轮未重写原报告。首次强杀恢复异常后来通过，但根因未确认，详见docs03。

## 历史来源与运行

旧source.json冻结docs12等21文件，已合并文档不再存在于当前树；保留原哈希，不能冒称当前树仍字节相同。本轮不改代码，完整来源核验需在独立29e历史工作树执行原审计器，README和docs03有命令。原evaluate_core20也引用docs12，因此新付费专项运行需在该历史工作树执行；当前树旧入口限制明确记录，未来代码修订须另授权。

应用安装、离线run/show/resume与自然入口按README。自然入口仍为字段收集/修改/确认，未实现自由对话任务路由。Windows wheel/仓库外运行有历史证据，Linux等未测。runtime.db不提交，物理--recheck需原库；仓库evidence是可读快照，离线测试自建临时库。

营销扩写按用户取舍为核心之外质量备注，历史严格内容失败保留；独立事实审核DEFERRED。E07/E08协议纠正、E16多余限额请求保留。密钥、env、venv、work、DB不提交；不读取其他进程凭据、不自动重跑付费API。

## Git、交付与下一步

基线main/29e3a7163dd28ad8cc5c1e7f8f9e2c2c94d36a0f，单worktree；起始仅HANDOFF规划记录未提交。2026-10-31已fetch，origin/main仍为29e，无远端新增。用户此前授权全部提交并推送https://github.com/yysk6/xiaoying，本次文档整理延续授权；文档静态检查已通过；内容提交49fed7b80315731a95a453c46ac4cfc03b0cb615已push，ls-remote确认远端main一致；随后仅补此交付状态，最终SHA以Git为准，不强推、不改全局safe配置。

文档归并完成，用户验收尚未确认。静态检查与内容提交推送已完成，交付后等待具体修订；不继续功能开发，不追认历史阶段全部accepted。

## Suggested skills

纯文档用karpathy-guidelines控制范围；规则/交接用writing-for-agents与handoff（根HANDOFF优先）。只有已授权代码行为修改才按AGENTS触发TDD、诊断或Spec/Standards审查。技能来源/适配在docs04。
