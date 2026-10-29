# 机器可读契约说明

这些文件是规格，不是已执行项目的输出：

- `request.schema.json`：CLI业务输入。允许缺失业务字段以形成needs_input；request_id本身必须存在。
- `tools.json`：实际拟发送给模型的六个函数工具定义，未启用Beta strict。
- `common.schema.json`：候选、脚本、估算、保存方案和工具结果的严格结构。
- `result.schema.json`：CLI最终结果；明确completed必须有保存方案，其他状态不能带保存方案。
- `trace-event.schema.json`：导出的单条JSONL事件。
- `fixtures/`：首版合成资料、报价和别名的确定基线；不是实际运行案例。

Schema只负责结构，领域代码负责跨字段语义：合计等于分项之和、四项步骤顺序/依赖正确、source_ids确实存在、当前revision匹配、时间与预算约束、ID指纹可复算。

Pydantic必须使用严格整数校验：JSON Schema对`10.0`和`10`的数学整数判断可能相同，实际接口仍按规格拒绝浮点型预算。时间字符串先按Schema形式校验，再解析真实日期、偏移与过去时间。

唯一开放对象为诊断信息`error.details`和Trace中的原始`args`：前者是错误码对应的非权威诊断JSON，不能直接修改业务状态；后者必须与当次工具参数Schema一致，非法原始参数只用于validation事件且做长度限制。禁止利用开放对象绕过成功产物契约。

脚本事实校验首版边界：source_ids必须等于所选主素材；出现百分比表达（整数或小数后接可选空白和`%`）时，规范化空白后必须在所选facts出现，否则拒绝；固定禁用语“行业第一”“100%准确”不得出现。其他自然语言事实依赖受限提示和人工评估，不宣称已被程序完全证明。校验规则与脚本提示同版本维护，变更必须提升script_prompt_version。

实现阶段以Pydantic定义DTO并导出Schema，CI检查与本规格的字段/必填/枚举/范围语义一致。不能一边改DTO一边保留过时规格。首次生成代码前，本包JSON Schema是接口结构基线。
