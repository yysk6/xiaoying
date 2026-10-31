# 项目上下文交接

更新：2026-10-31（UTC+08）。恢复先读AGENTS、本文件及[评估维护记录](docs/03-evaluation.md#当前限制与维护记录)，再核对Git/worktree/remote。权威规格为docs五篇和contracts；content-planner-spec为忽略的历史快照。

## 当前阶段与授权

用户授权修复当前20场景评测脚本引用已删除docs12的问题，随后授权完整离线、真实API和端到端测试，条件满足时提交推送。此授权不追认先前阶段用户验收。已实现并验证来源修复；业务Agent决策和历史评测产物未改动。

新运行在提示凭据前记录当前五篇文档、显式机器契约/fixture、必需包内数据、业务代码、案例与依赖锁的SHA-256，以及Git commit和工作树状态。显式必需来源缺失或Git信息不可读则在提示凭据前停止。README与案例索引改为说明当前入口和Git要求；历史原始来源仍须以29e3a7163dd28ad8cc5c1e7f8f9e2c2c94d36a0f核验，旧input/output/Trace/source/assessment均未改写。

## 实际验证与审查

- Red：新增CLI边界测试在修复前实际因缺失docs12报FileNotFoundError；双轴审查后补充的缺失包内数据、Git不可用两项反例在补强前均失败，因仍进入凭据提示。
- Green：`.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_core20_evaluation.py -q --junitxml=examples/tests/core20/source-manifest-junit.xml`，23 passed，5.34秒；包含清单哈希、缺资料/文档和Git失败时的凭据前停止。测试替换凭据提示与文件/Git边界，不调用HTTP。
- Spec与Standards独立并行审查各发现必需数据缺失可被glob遗漏；Spec另发现Git失败被记为null。均已修复，两轴复核无剩余实质问题。`git diff --check`及旧真实产物差异检查通过；结果见本阶段对话及[JUnit](examples/tests/core20/source-manifest-junit.xml)。
- 用户授权后的完整复测：`.venv/Scripts/python.exe -X utf8 -m pytest -q --junitxml=examples/tests/full-validation-20261031/pytest-junit.xml`，412 passed，157.32秒。[真实核心运行](examples/live/core20/20261031T153418Z-5c0bb6c4/summary.json)20/20、89 HTTP；6例初始premium夹具、4例零HTTP，其余真实模型调用，均单样本。[自然语言终端实测](examples/live/manual-e2e-20261031/manual-assessment.json)字段确认和业务保存成功，费用8，另外7次模型调用；文案含无素材支持的“效率翻倍”“调样式”，人工内容检查失败，按此前用户确认列为非阻塞质量限制，不能冒称事实审核通过。
- 真实核心运行记录基线013329d且来源当时为未提交工作树，运行开始时37项哈希均匹配；同目录`source-working-tree.patch`保存相对基线的来源改动，`source-snapshot/`保留两份变动来源的原始字节并已核对source.json哈希；不能称为基线原样运行。旧真实产物未改写。历史完整408通过、早前核心20/20及首次强杀异常复测保持原口径，见[评估](docs/03-evaluation.md)。
- 两个本次真实运行目录的`.gitattributes`关闭换行转换；逐一比较238个暂存文件的Git blob与工作树原始字节，差异0。暂存差异使用`git -c core.whitespace=cr-at-eol diff --cached --check`检查通过，CRLF来自原始运行记录。

## 历史证据与限制

原始20例为16真实模型场景、4零调用防护、6初始premium夹具，88 HTTP；每例单样本。原始source.json冻结旧文档哈希，当前工作树不能冒称字节相同；历史审计命令见README和docs03。物理`--recheck`需要原runtime.db，仓库提供可读快照。自然语言入口为字段收集/确认，非自由对话路由；营销扩写历史严格内容失败保留，独立事实审核DEFERRED。Windows有历史wheel/仓库外验证，Linux、其他Python和同任务并发未测。首次强杀恢复异常复测通过但根因未确认。

## Git与下一步

本阶段基线main/013329d4e2233cff35620e111832db23c0a3f9e1，启动时单worktree、修复变更尚未提交；2026-10-31联网ls-remote核实远端main仍为该SHA。用户授权通过验证后提交推送，最终状态以`git status`、`git log -1`及远端实际查询为准。后续业务改进需另获授权；不自动追加付费运行。
