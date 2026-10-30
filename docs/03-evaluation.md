# 测试与效果验证规格

**完整业务案例A01—A23及Live评估仍为NOT_RUN。** S0—S2历史171项结果见[S2报告](stages/S2.md)；S3新增存储/保存断言，最新测试与审查集中见[S3报告](stages/S3.md)，不代表CLI端到端、跨进程checkpoint恢复或真实模型效果通过。下表仍是完整业务验收设计。

S2实际通过A04/A06的报价与换档位工具断言、A14的失效/复用、A17的空检索/改写、A19的脚本拒绝，以及候选四版上限；未验证这些案例的模型决策、保存或恢复部分。错误观察保留与显式再次调用通过，不等于模型观察后自主重试通过。Windows/Python 3.10.8 wheel安装与包内资源通过；A23的业务CLI及Linux仍NOT_RUN。实际日志和JUnit见examples/tests/stages/S2/。

## 测试分层

### S3验收预期（实现前，2026-10-30）

通过docs/07规定的Repository与save_plan入口，使用真实临时SQLite验证请求去重/冲突及不可变记录、版本/连接设置、事件顺序/唯一键、保存行与成功事件同事务、提交前故障零方案、同内容复用/异内容冲突、重开数据库查到已提交事实。保存需核对最新revision/estimate/脚本，重读Clock拒绝新超期，失败不置completed；成功输出符合现行Schema且四个活动均为planned。先逐行为取得Red/Green，集中记录命令与关键失败，最终全量回归一次；实际结果另记S3报告，不回填本段为已通过。

### S2验收预期（实现前）

逐个行为增加测试：包内三份数据与fixture一致且可在仓库外导入；资料加载失败/非法报价不补默认值；别名NFC/lower/trim、长别名优先、不同tag计分与稳定排序；空检索后改写命中且seen集合累加；未见/未知素材拒绝；候选重复不增版本、第五版拒绝；无候选/旧revision拒绝；脚本严格校验及失败保留已有结果；相同输入复用脚本、换档位复用脚本但估算失效、换素材/brief生成新脚本；超预算/超期仍为成功估算并列同素材另一档位；每次重新读取Clock且同次alternatives共享时刻；所有结果符合common.ToolResult及四个输入Schema。状态snapshot可JSON往返。

测试优先通过上述公开入口及返回状态观察；仅ModelClient、Clock和资料目录属于可替换边界。完整CLI案例、模型观察后自主重试/重规划、保存及跨进程恢复不属于S2通过结论。实际Red/Green单独保存在examples/tests/stages/S2/及阶段报告。

### S1验收预期（实现前补充）

- 输入：逐个/组合缺失与null、非法ID/额外字段/类型/长度、budget=10.0和上限、空白/NFC、非法真实日期/无偏移时间；固定Clock下过去/等于now拒绝，未来允许。
- 指纹：固定已知SHA-256向量、跨子进程一致、等价时区/Unicode/键顺序一致，request_id不参与；候选受档位/报价/素材/brief影响，脚本不受档位影响但受素材/brief/模型/提示版本影响。
- 报价：从contracts/fixtures读取M01/M02与pricing-v1，核对四分项、basic=8/90、premium=12/135，精确预算/期限、秒与微秒缺口向上取整、换时间重新计算、调整测试报价数据后结果随之变化。
- 脚本：JSON、必填/类型/长度/额外字段、来源恰好一个、所有文本字段的禁用语/百分比，小数与空白支持、80%不能误匹配180%；不验证任意自然语言命题。
- 契约：导出Request与ScriptDraft的Pydantic Schema，与现行请求Schema及common.Script的模型生成字段投影比较字段/必填/类型/范围/额外字段语义（忽略title/default等注释）。

以上是S1单元断言，不意味着A02/A03/A19端到端通过。Red/Green实际结果另记docs/stages/S1.md和examples/tests/stages/S1/，不能回填计划为通过。

1. Unit：预算/时间边界、Pydantic 契约、指纹、依赖失效、状态转换；固定 Clock，零网络。
2. Integration：真实本地工具 + 临时 SQLite + Fake ModelClient；检查事务、checkpoint、重复请求和跨进程恢复。不得 Mock 掉需要验证的保存函数。
3. Acceptance：从 CLI 子进程执行固定场景，核对退出码、JSON、数据库 plan 数量与 Trace；普通执行默认 Mock。
4. Live eval：同一业务实现、真实 DeepSeek、实际工具观察；单独启用、记录所有失败，不把离线动作脚本当真实模型。

默认测试使用临时数据库与输出目录；禁止覆盖用户数据库。网络在普通 pytest 中通过 fixture 禁用；只有显式 live marker 可以访问官方 API。

## 需求—测试—证据矩阵

案例基准时间为注入 Clock `2026-10-29T10:00:00+08:00`；live 案例由运行器按实际当前时间生成 deadline，不使用已经过期的固定日期。预算10/basic8、premium12为 pricing-v1 的预期值，不硬编码在业务分支。

| Case ID | 输入/故障条件 | 核心断言 | 覆盖 | 未来证据目录 |
|---|---|---|---|---|
| A01 | 预算14，截止+180分钟，正常工具 | 有脚本、来源和四项 planned 活动；报价合计正确且可行；保存1行；completed | R02—R06 | examples/mock/A01/ |
| A02 | 分别缺预算、缺截止时间、缺主题 | needs_input；missing_fields准确；模型0调用；plan0行 | R01 | examples/mock/A02/ |
| A03 | budget=0/-1/true/10.5/字符串；非法/无偏移/过去时间 | 明确字段错误；不创建任务、不调用模型 | R01 | examples/mock/A03/ |
| A04 | Fake先选premium，预算10，后改basic | 真实估算12 -> 8；中间稿不保存；脚本复用；最终1行 | R04/R05/R08 | examples/mock/A04/ |
| A05 | 预算5，两个档位都不满足 | incomplete；列出已评估报价与缺口；不宣称全局最优；plan0行 | R08 | examples/mock/A05/ |
| A06 | 截止+100分钟，premium135超期，basic90可行 | 模型调整后再次估算；只能保存满足deadline的版本 | R04/R08 | examples/mock/A06/ |
| A07 | generate_script首次瞬时失败，下一次成功 | 失败观察真实进入下一次决策；模型选择重试；检索不重做；失败attempt保留 | R05/R07 | examples/mock/A07/ |
| A08 | generate_script持续失败 | 每逻辑参数最多2次；模型可停止；不得记录草稿成功或保存 | R07/R10 | examples/mock/A08/ |
| A09 | save_plan事务提交前故障 | plan0行；incomplete或模型重试成功；失败时不返回已保存 | R06/R07 | examples/mock/A09/ |
| A10 | 成功后原ID原输入重复run | 第二次模型/工具0调用；相同plan_id；数据库仍1行 | R09 | examples/mock/A10/ |
| A11 | 原ID不同预算/主题/截止时间 | REQUEST_CONFLICT；原行与状态不变 | R09 | examples/mock/A11/ |
| A12 | 检索成功后生成失败并停止；新进程resume | 从已存状态续跑；保留素材；恢复成功且不超累计限额 | R07/R11 | examples/mock/A12/ |
| A13 | save提交后、checkpoint前注入崩溃；新进程恢复 | 读到已提交plan即completed；不再调用模型；只有1行 | R09/R11 | examples/mock/A13/ |
| A14 | 候选换素材/brief；或仅换档位 | 前者旧脚本/估算失效；后者脚本复用、估算失效；旧estimate不能保存 | R04/R08 | examples/mock/A14/ |
| A15 | 估算后Clock前进到无法按期 | save拒绝；包含新缺口；plan0行 | R04/R08 | examples/mock/A15/ |
| A16 | 无意义重复动作、候选5次、调用额度耗尽 | 在约定上限停止；明确reason；resume不能重置 | R10/R11 | examples/mock/A16/ |
| A17 | 首次空检索，改写命中；以及持续无素材 | 第一条继续完成，第二条说明资料不足；不造素材 | R02/R05 | examples/mock/A17/ |
| A18 | 非法参数/未知工具/多调用/无工具自由文本 | 无越权执行；协议错误按规格处理；自由文本不产生完成状态 | R05/R10 | examples/mock/A18/ |
| A19 | JSON非法/错误source_id/明确无依据效果数字 | SCRIPT_INVALID；无成功草稿；模型可调整或停止 | R03/R07 | examples/mock/A19/ |
| A20 | 报价或素材内容变化 | 新ID按新数据计算；旧任务resume拒绝manifest变化；历史show不变 | R04/R08/R11 | examples/mock/A20/ |
| A21 | 无密钥离线运行；live缺配置/401/429/5xx | mock明确标识；live不降级；错误映射准确 | R07/R13 | examples/mock/A21/ |
| A22 | 方案已保存但Markdown导出失败 | completed + EXPORT_FAILED；show可重导出；不会重复保存 | R06/R09/R12 | examples/mock/A22/ |
| A23 | 无Codex、无项目专用宿主环境变量的干净虚拟环境；Windows与Linux | 按锁文件安装；从非仓库cwd用显式路径运行离线CLI与测试；不访问Codex目录/内部接口；结果Schema一致 | R15 | examples/tests/portability/ |

边界单测还要覆盖：预算恰等合计、完成时间恰等deadline、相同绝对时间的不同偏移得到相同输入指纹、rationale改变不影响缓存键。

## 真实模型评估

至少执行 L01 正常、L02 工具失败、L03 预算受限三类场景。L01/L02 必须来自普通入口的完整 live 调用，不使用预制决策日志。每个场景建议运行3次，样本很小，只报告次数，不报告泛化成功率。

- L01：约束可行，检查真实调用参数、估算和最终提交；不强求模型选择premium。
- L02：检索成功后令脚本生成工具第一次返回可重试失败，模型必须观察后自己选择重试或说明未完成。仅由程序自动重试不算通过“动态调整”检查。
- L03：预算10。模型可能直接选择basic，这是合理行为，不能为了演示强迫它先犯错。若没有出现12->8轨迹，不写“已验证超预算后的模型重规划”。

若需要专门验证“观察12后调整”，增加 L04 **显式状态夹具**：测试setup使用真实本地工具建立premium候选与12-unit估算，记录origin=fixture_setup；不伪造模型消息、工具调用或决策理由。随后把该事实状态交给真实模型，让其选择修订/估算/保存或停止。它验证给定状态下的真实模型决策，不能标注为从空输入开始的完整live路径，也不能替代L01/L02。

Live断言按性质判断，不要求固定措辞/严格工具顺序：完成时约束与保存事实必须正确；无依据内容为失败；失败时保留结果且不虚报；响应工具观察的动作与理由可核查。工具改变前后对照使用新request_id，明确保留两边运行记录。

## 每组实际证据的内容

```text
examples/<backend>/<case>/
  input.json             # 实际输入
  scenario.json          # 数据哈希、故障注入、Clock来源、是否fixture_setup
  output.json            # 程序实际最终输出
  plan.md                # 若成功，实际导出方案
  trace.jsonl            # 实际执行事件
  run.json               # 命令、开始/结束时间、退出码、commit、backend、模型参数
```

Trace事件至少含schema_version、event_id、request_id、origin(model/fixture_setup/system)、阶段、动作、参数、公开rationale、观察摘要、结果引用和状态。后续模型动作通过next_decision_event_id关联；最后事件该字段为null。此关联由导出器根据实际事件顺序构建，不事先编造。Token用量记录真实返回值；未知为null；禁止写入密钥、认证头或reasoning_content。

测试结果：`examples/tests/pytest-junit.xml`、`summary.json`；summary保留总数/失败/跳过及pytest退出码。评估文档必须在实现后逐项填写实际路径和结果，不只写“测试通过”。

## 交付门槛

- 必做验收点全部有可执行测试；关键不变量零失败。
- 至少3组实际输入/输出/Trace，覆盖正常、信息不足、工具失败；建议保存上述全部确定性案例。
- 至少2条真实模型路径，能查到模型依据不同观察改变动作的证据；Mock路径另列。
- 预算与时限算错、失败记成功、重复保存、无真实模型闭环属于发布阻塞。
- 真实模型偶发失败如实报告，不能用成功样本覆盖失败记录；若模型不可用，标记未完成真实效果验证。
- 可移植性须保留无Codex干净环境的实际安装/离线运行日志，Windows与Linux分别标注结果；未执行的平台写NOT_RUN。
