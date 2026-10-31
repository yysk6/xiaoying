# 输入、实际输出与Trace索引

本页将题目验收点直接映射到实际文件。所有结果来自已执行程序；正文是导航和解释，原始输入、输出、Trace、观察及判定保留在原运行目录。

## 优先评审的真实案例

固定运行20261031T110356Z-93ca1d21，官方DeepSeek deepseek-v4-pro。E11/E12的正确行为就是不调用模型；E04明确给定初始premium状态，其余下表普通业务从service空白入口开始，E18另执行resume。

| 案例 | 覆盖内容 | 实际结果 | 输入 | 输出 | 完整Trace | 模型观察/下一动作 | 判定 |
|---|---|---|---|---|---|---|---|
| E01 | 正常完成 | completed、8、plan1 | [input](live/core20/20261031T110356Z-93ca1d21/E01/input.json) | [output](live/core20/20261031T110356Z-93ca1d21/E01/output.json) | [trace](live/core20/20261031T110356Z-93ca1d21/E01/trace.jsonl) | [observations](live/core20/20261031T110356Z-93ca1d21/E01/observations.json) | [assessment](live/core20/20261031T110356Z-93ca1d21/E01/final-assessment.json) |
| E11 | 缺预算 | needs_input、业务调用0、plan0 | [input](live/core20/20261031T110356Z-93ca1d21/E11/input.json) | [output](live/core20/20261031T110356Z-93ca1d21/E11/output.json) | [trace](live/core20/20261031T110356Z-93ca1d21/E11/trace.jsonl) | 零调用：[]（见evidence） | [assessment](live/core20/20261031T110356Z-93ca1d21/E11/final-assessment.json) |
| E12 | 缺截止时间 | needs_input、业务调用0、plan0 | [input](live/core20/20261031T110356Z-93ca1d21/E12/input.json) | [output](live/core20/20261031T110356Z-93ca1d21/E12/output.json) | [trace](live/core20/20261031T110356Z-93ca1d21/E12/trace.jsonl) | 零调用：[]（见evidence） | [assessment](live/core20/20261031T110356Z-93ca1d21/E12/final-assessment.json) |
| E15 | 脚本首次失败后恢复 | 原failed保留、重试后completed | [input](live/core20/20261031T110356Z-93ca1d21/E15/input.json) | [output](live/core20/20261031T110356Z-93ca1d21/E15/output.json) | [trace](live/core20/20261031T110356Z-93ca1d21/E15/trace.jsonl) | [observations](live/core20/20261031T110356Z-93ca1d21/E15/observations.json) | [assessment](live/core20/20261031T110356Z-93ca1d21/E15/final-assessment.json) |
| E17 | 真实保存事务失败后恢复 | 回滚plan0→模型重试→plan1 | [input](live/core20/20261031T110356Z-93ca1d21/E17/input.json) | [output](live/core20/20261031T110356Z-93ca1d21/E17/output.json) | [trace](live/core20/20261031T110356Z-93ca1d21/E17/trace.jsonl) | [observations](live/core20/20261031T110356Z-93ca1d21/E17/observations.json) | [assessment](live/core20/20261031T110356Z-93ca1d21/E17/final-assessment.json) |
| E04 | 预算10、初始12改选8 | 观察缺口2→修订→重估8→保存 | [input](live/core20/20261031T110356Z-93ca1d21/E04/input.json) | [output](live/core20/20261031T110356Z-93ca1d21/E04/output.json) | [trace](live/core20/20261031T110356Z-93ca1d21/E04/trace.jsonl) | [observations](live/core20/20261031T110356Z-93ca1d21/E04/observations.json) | [assessment](live/core20/20261031T110356Z-93ca1d21/E04/final-assessment.json) |
| E07 | 预算5无可行方案 | incomplete、缺口3、plan0 | [input](live/core20/20261031T110356Z-93ca1d21/E07/input.json) | [output](live/core20/20261031T110356Z-93ca1d21/E07/output.json) | [trace](live/core20/20261031T110356Z-93ca1d21/E07/trace.jsonl) | [observations](live/core20/20261031T110356Z-93ca1d21/E07/observations.json) | [assessment](live/core20/20261031T110356Z-93ca1d21/E07/final-assessment.json) |
| E19 | 完成后重复执行 | 结果与数据库不变、额外HTTP0 | [input](live/core20/20261031T110356Z-93ca1d21/E19/input.json) | [output](live/core20/20261031T110356Z-93ca1d21/E19/output.json) | [trace](live/core20/20261031T110356Z-93ca1d21/E19/trace.jsonl) | [observations](live/core20/20261031T110356Z-93ca1d21/E19/observations.json) | [assessment](live/core20/20261031T110356Z-93ca1d21/E19/final-assessment.json) |
| E18 | 部分成功后显式续跑 | 原10条事件保留、续跑完成 | [input](live/core20/20261031T110356Z-93ca1d21/E18/input.json) | [output](live/core20/20261031T110356Z-93ca1d21/E18/output.json) | [trace](live/core20/20261031T110356Z-93ca1d21/E18/trace.jsonl) | [observations](live/core20/20261031T110356Z-93ca1d21/E18/observations.json) | [assessment](live/core20/20261031T110356Z-93ca1d21/E18/final-assessment.json) |

[E11完整证据](live/core20/20261031T110356Z-93ca1d21/E11/evidence.json)和[E12完整证据](live/core20/20261031T110356Z-93ca1d21/E12/evidence.json)包含零决策、无业务库的实际快照。空Trace是防护成功结果，不是遗漏记录。

E17的[fault-log](live/core20/20261031T110356Z-93ca1d21/E17/fault-log.json)现场记录失败时plan行数0；E18的[followup](live/core20/20261031T110356Z-93ca1d21/E18/followup.json)保存中断前后结果与数据库快照；E19的[followup](live/core20/20261031T110356Z-93ca1d21/E19/followup.json)证明第二次请求前后无新增HTTP/事件/plan。E20另验证同ID改预算的[冲突结果](live/core20/20261031T110356Z-93ca1d21/E20/phases/conflict/output.json)，原任务保持完成。

期限调整、精确边界和其他场景见[20例完整报告](../docs/03-evaluation.md#核心20场景的预期与实际结果)、[冻结配置](evaluation/core20-cases.json)、[运行汇总](live/core20/20261031T110356Z-93ca1d21/summary.json)与[最终判定](live/core20/20261031T110356Z-93ca1d21/final-assessment.json)。6个初始状态夹具在scenario与Trace中标为fixture_setup；不能把它们说成全程由模型自主产生初始premium方案。

## Trace应该怎么看

1. 先读input和scenario，确认预算、期限、模拟时钟、故障与夹具来源。
2. 看output的status、execution_steps、tool_results、total_units和saved_plan。completed只表示plan保存；未来活动仍planned。
3. 沿trace的event_id、operation_id、phase查看实际动作及结果，使用result_ref回到tool_results、next_decision_event_id找到后续决策。
4. 对照observations里的必要事实和模型返回动作，验证模型确实看到超限/错误再调整。该记录只有安全事实投影与公开响应，不含内部推理。
5. evidence保存请求、实际事件/状态补丁、plan快照、资料及故障记录。最终判定与输出一起看，不能只凭一段文案判断成功。

例如E04先有12/缺口2的报价，模型改basic后旧估算失效，再得8并保存；E17失败save与新成功save为两个attempt，失败未被重写。

## 无密钥可复现的三类案例

| 场景 | 固定输入 | 显式Fake动作与Clock | 已有实际输出 | 已有Trace |
|---|---|---|---|---|
| 正常 | [A01/input](mock/A01/input.json) | [scenario](mock/A01/scenario.json) | [output](mock/A01/output.json) | [trace](mock/A01/trace.jsonl) |
| 缺预算 | [A02/input](mock/A02/input.json) | [scenario](mock/A02/scenario.json) | [output](mock/A02/output.json) | [trace](mock/A02/trace.jsonl) |
| 持续工具失败 | [A08/input](mock/A08/input.json) | [scenario](mock/A08/scenario.json) | [output](mock/A08/output.json) | [trace](mock/A08/trace.jsonl) |

这些使用实际业务工具、SQLite和图，只替换外部模型与Clock，输出明确backend=mock；证明程序流程，不代表模型智能。执行命令、预期退出码和显式续跑见[README](../README.md#无密钥离线运行)。固定日期配scenario时钟可离线重放，真实任务应提供当前有效的新截止时间。

## 测试与历史记录

- 最新[完整离线JUnit](tests/full-validation-20261031/pytest-junit.xml)412/412通过；历史[复测汇总](tests/core20/final-verification.json)保存首次异常与后续通过的区别。
- [产物审计](tests/core20/artifact-audit.json)：23份输出、408条含阶段Trace经Schema与事实核验。
- [Windows正式包运行](tests/intake/clean-install.json)：公开运行环境、仓库外导入、MockTransport及实际业务/重复保护通过；真实HTTP0。
- [自然语言终端实际报告](../docs/03-evaluation.md#自然语言终端历史验证)引用三轮全部产物，包含失败与修订后记录。
- 更早[预算专项](../docs/03-evaluation.md#历史专项工程验证与审查)、[S7](../docs/03-evaluation.md#历史专项工程验证与审查)及tests/stages是历史证据，口径与时间分别标明。

## 复核与数据边界

Git不含runtime.db、密钥、工作目录或虚拟环境，包含可读事件/plan快照。审计已提交JSON/Trace可执行：

```sh
git worktree add --detach ../xiaoying-evidence-29e 29e3a7163dd28ad8cc5c1e7f8f9e2c2c94d36a0f
python ../xiaoying-evidence-29e/examples/tests/core20/audit_artifacts.py ../xiaoying-evidence-29e/examples/live/core20/20261031T110356Z-93ca1d21
```

需先安装开发依赖，本地Git须有该历史提交；在独立历史工作树核验原来源，当前树已合并原文档，不能直接通过旧来源核验。物理库复核`python -m scripts.evaluate_core20 --recheck <run目录>`还须原始runtime.db；本机实测已完成，不能声称仅克隆仓库即可读取未提交数据库。离线pytest会重新创建临时数据库验证相同规则。

真实评测不会自动启动。新付费运行在当前项目显式执行`python -m scripts.evaluate_core20 --live --key-stdin`；会产生费用，新运行另存新目录并记录当前来源。最新[复测结果和自然语言实测](../docs/03-evaluation.md#当前结论)与历史运行分开保存；历史产物仍按上述历史提交核验。合成资料、预算单位和模拟活动工期均不等同真实业务执行或API账单。
