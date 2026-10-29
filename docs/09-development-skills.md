# 开发技能使用约定

更新日期：2026-10-29。用户已明确要求安装并使用下列6个技能。本文规定使用时机与项目适配；阶段范围和验收顺序仍以[开发计划](08-development-plan.md)为准，业务行为以docs/和contracts/为准。

## 来源与定位

来源为第三方中文仓库[vinvcn/mattpocock-skills-zh-CN](https://github.com/vinvcn/mattpocock-skills-zh-CN)，本机安装固定在提交`5b57718666917f8a6a0ff3066ae8d5ec386baef4`。安装结果及18个文件的内容校验见[安装记录](tooling/skills-installation.json)。更新版本时先审阅变化，再同步本文与安装记录。

技能是代理使用的公开Markdown操作指引，不是项目安装、构建、测试或运行依赖。它们未进入pyproject.toml或依赖锁，也不要求其他编辑器具备Codex目录、账户、内部工具。换环境可从同一公开来源读取指引；如实记录实际读取与使用方式。

原ToolMonsters版handoff已备份到本机`$CODEX_HOME/skill-backups/handoff-ToolMonsters-20261029`，活动目录只保留本次中文版本。备份不在skills目录中，不会被同时发现为另一个handoff技能。

## 什么时候使用

| 技能 | 触发时机 | 本项目的具体用法与完成证据 |
|---|---|---|
| [tdd](https://github.com/vinvcn/mattpocock-skills-zh-CN/blob/5b57718666917f8a6a0ff3066ae8d5ec386baef4/skills/engineering/tdd/SKILL.md) | 新增或修改业务行为、修复缺陷时；S2开始持续使用 | 先对齐规格与公开接口，每次一个可观察行为、一项聚焦测试、真实Red、最小Green。测试期望来自规格或独立算例；按技能读取tests.md与mocking.md。保留命令、退出码与失败原因。 |
| [handoff](https://github.com/vinvcn/mattpocock-skills-zh-CN/blob/5b57718666917f8a6a0ff3066ae8d5ec386baef4/skills/productivity/handoff/SKILL.md) | 每阶段交付前、用户验收/修订后、重要阻塞或会话中断时 | 更新根目录HANDOFF.md，记录目标、状态、授权边界、决策和下一步；通过路径引用规格、阶段报告、提交与证据，增加suggested skills。接手时重新核对Git状态。 |
| [writing-for-agents](https://github.com/vinvcn/mattpocock-skills-zh-CN/blob/5b57718666917f8a6a0ff3066ae8d5ec386baef4/skills/productivity/writing-for-agents/SKILL.md) | 创建或修改AGENTS.md、HANDOFF.md、代理操作规则或技能文档时 | 明确触发条件和完成标准。详细规则只保留一个权威位置，其余文档通过链接引用；区分当前快照、历史证据与计划，检查链接有效性。 |
| [code-review](https://github.com/vinvcn/mattpocock-skills-zh-CN/blob/5b57718666917f8a6a0ff3066ae8d5ec386baef4/skills/engineering/code-review/SKILL.md) | 从本次配置后的业务阶段交付前，以及用户明确要求审查时 | 以阶段开始记录的commit为基线，分别审查项目规则和规格符合性；按技能使用两个并行审查子代理。报告基线、实际diff命令、两类发现和未解决项，存入阶段报告或其引用文件。纯安装/文档维护做差异与链接核对，不自动启动业务阶段审查。 |
| [diagnosing-bugs](https://github.com/vinvcn/mattpocock-skills-zh-CN/blob/5b57718666917f8a6a0ff3066ae8d5ec386baef4/skills/engineering/diagnosing-bugs/SKILL.md) | 已观察到、原因不明的失败或性能回退；尤其S3事务、S6恢复、S7协议问题 | 先建立能复现具体症状的确定性命令，缩小复现，再逐个验证假设，修复并补回归。展示的日志先脱敏；保留原始复现、修复后结果及真实限制。简单已定位错误使用聚焦TDD，不机械执行整套调查。 |
| [codebase-design](https://github.com/vinvcn/mattpocock-skills-zh-CN/blob/5b57718666917f8a6a0ff3066ae8d5ec386baef4/skills/engineering/codebase-design/SKILL.md) | 接口位置、参数或依赖关系出现具体设计问题时 | 按需参考小接口、集中行为和可替换依赖的原则，结合docs/02-solution.md确定测试入口。优先普通函数；只为真实变化引入接口。额外并行设计仅在确有多个待比较方案时使用。 |

karpathy-guidelines继续作为整体开发指导：明确假设、最小充分实现、修改范围可解释、用实际结果验证目标；与上述技能配合，保持不过度防御、不过度抽象。

## 与现有项目规则的衔接

1. **规格先行。** 先完成当前阶段的规格与验收预期，再按tdd逐个行为推进。测试边界复用现有契约和已获授权范围；只有无法从规格确定的新产品选择或接口边界才向用户确认。技能不产生跨阶段授权。
2. **保留必要整理。** 本项目按开发计划在Green后、测试保护下进行当前切片的必要整理。tdd上游将重构安排在review阶段，该通用安排以本项目既定顺序为准；避免横跨未实现功能的重构。
3. **验证真实存储。** S3及后续仍按规格使用真实临时SQLite，检查行数、事务和唯一约束。优先通过公开repository接口观察结果；规格明确要求的直接数据库事实断言继续保留，不能以通用测试建议删掉它们或Mock保存函数。
4. **交接位置固定。** 用户已指定根目录HANDOFF.md，覆盖handoff技能默认写系统临时目录的安排。完整实现与历史保留在Git及阶段报告，交接文档保存当前事实和引用，不复制整份源码；敏感信息不写入交接文档。
5. **审查覆盖实际变更。** 已提交内容使用`git diff <baseline>...HEAD`；有未提交内容时同时纳入`git diff`及`git diff --cached`并提供给两个审查子代理。基线已记录则直接使用，信息确实缺失才询问。空diff不代表未提交内容已通过审查。
6. **本地规格足够。** code-review的规格来源使用docs/、contracts/与当前阶段报告；本项目没有新增issue tracker配置需求，无须为此安装或运行setup-matt-pocock-skills。
7. **按触发条件读取。** 每次先读取实际将使用的SKILL.md和该分支需要的引用，不将六份内容每轮全部加载。阶段报告记录本次实际使用的技能、作用和证据；安装成功不等于该技能已执行或审查通过。

## 当前配置结果

2026-10-29已完成6个技能安装，核对frontmatter名称及18个文件与固定提交一致，并验证旧handoff备份完整。当前文档维护实际使用skill-installer、writing-for-agents与handoff；未执行tdd业务切片、code-review子代理审查或S2开发。业务测试未因本次文档更新重跑，S1已有结果仍见[阶段报告](stages/S1.md)。技能将在安装后的下一个用户回合可被发现使用。
