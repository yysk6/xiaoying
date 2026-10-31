# 内容任务规划 Agent

选题2：帮助运营人员在预算与截止时间内形成一份短视频活动方案。模型负责选择动作、观察结果和调整计划；程序负责报价、依赖校验、真实状态与保存事务。

当前交付包含真实 DeepSeek 决策循环、四个业务工具、任务记忆、失败处理、重复请求保护、显式续跑、自然语言需求收集及离线 Mock 入口。`completed` 表示本地方案保存成功，未来的视频制作与发布没有执行。

**实际结果：最新核心评测20/20通过；最新完整离线测试412/412通过。** 20例含16例真实模型场景、4例零调用输入防护；其中6例明确给定初始premium方案，再交真实模型决策。结果来自每例一个样本；自然语言实测仍发现素材未支持的营销措辞，范围和限制见[评估](docs/03-evaluation.md)。

## 评审入口

| 想了解什么 | 从这里看 |
|---|---|
| 用户、业务口径、范围和成功标准 | [01 需求](docs/01-requirements.md) |
| 模型闭环、工具、记忆、框架职责与取舍 | [02 方案](docs/02-solution.md) |
| 测试预期、实际结果、失败记录与限制 | [03 评估](docs/03-evaluation.md) |
| 本人如何组织AI、设计判断与AI辅助范围 | [04 AI使用](docs/04-ai-usage.md) |
| 实际难点、学习和下一步 | [05 复盘](docs/05-retrospective.md) |
| 正常、缺输入、故障、重规划等实际输入/输出/Trace | [案例索引](examples/README.md) |

建议先看案例E04的“12→8”和E17的“保存失败→恢复”，再看方案与代码；它们分别展示约束反馈和失败反馈怎样改变模型下一步动作。

## 环境与安装

已验证环境：Windows、Python 3.10.8。项目声明Python >=3.10；其他Python版本及Linux未实测。依赖使用公开PyPI包，不依赖Codex、MCP、特定编辑器或宿主账户。

PowerShell，在项目根目录：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.lock
.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe -X utf8 -m pytest -q
```

POSIX对应命令（Linux未实测）：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m pip check
.venv/bin/python -X utf8 -m pytest -q
```

`pyproject.toml`声明直接依赖，`requirements.lock`锁运行依赖，`requirements-dev.lock`增加测试/构建依赖。首次安装需联网；业务离线演示和普通pytest无需密钥、默认禁网络。正式wheel及仓库外Windows运行验证见[安装记录](examples/tests/intake/clean-install.json)。

## 无密钥离线运行

以下使用固定Clock和显式Fake决策，执行相同业务工具、图和SQLite；用于复现流程与状态约束，不能证明模型决策效果。命令可重复执行，已有任务只读。

```powershell
# 正常完成，预期退出0、completed、费用8
.venv/Scripts/python.exe -m content_planner run --input examples/mock/A01/input.json --mock-scenario examples/mock/A01/scenario.json --db work/review/normal.db --output-dir work/review/normal

# 缺预算，预期退出2、needs_input、无业务任务
.venv/Scripts/python.exe -m content_planner run --input examples/mock/A02/input.json --mock-scenario examples/mock/A02/scenario.json --db work/review/missing.db --output-dir work/review/missing

# 持续脚本失败，预期退出3、incomplete/tool_failure、无已保存方案
.venv/Scripts/python.exe -m content_planner run --input examples/mock/A08/input.json --mock-scenario examples/mock/A08/scenario.json --db work/review/failure.db --output-dir work/review/failure
```

POSIX将上述解释器替换为`.venv/bin/python`，其余参数相同。案例的固定日期通过scenario注入的时钟重放，不能直接作为当前真实任务的截止时间。

输出目录包含`output.json`、`plan.md`和`trace.jsonl`。成功方案的四项未来活动仍为`planned`；真实尝试及失败历史在`execution_steps`中。退出码0=完成，2=需补充/修正输入，3=未完成，1=存储等基础设施错误。

查询与显式续跑：

```powershell
.venv/Scripts/python.exe -m content_planner show --request-id s5-A01 --db work/review/normal.db --output-dir work/review/show
# 第一条预期退出3；第二条从原数据库恢复
.venv/Scripts/python.exe -m content_planner run --input examples/mock/A12/input.json --mock-scenario examples/mock/A12/scenario.json --db work/review/resume.db --output-dir work/review/before
.venv/Scripts/python.exe -m content_planner resume --request-id s6-A12 --mock-scenario examples/mock/A12/continuation.json --db work/review/resume.db --output-dir work/review/after
```

## 真实模型与自然语言输入

真实后端固定为官方DeepSeek API、`deepseek-v4-pro`，thinking关闭，temperature=0。使用真实模型会产生API费用。

PowerShell在现有终端运行：

```powershell
.venv/Scripts/python.exe -X utf8 scripts/interactive_planner.py
```

POSIX对应`.venv/bin/python scripts/interactive_planner.py`。Windows如需独立窗口可加`--launch-window`。先在隐藏提示中输入自己的密钥，再输入：

```text
帮我做影芽剪辑字幕功能推广，预算10个模拟单位，明天下午六点前完成。
```

系统整理主题、预算和时间；可补充“预算改成8，其他不变”，核对后输入“确认”才启动业务。输入“取消/新建”清空草稿，`show <ID>`查询，`resume <ID>`显式续跑，`exit`退出。确认前的需求抽取也可能调用模型；草稿仅在当前进程内存，确认后的任务持久化。

当前自然入口是需求字段收集与确认，回应使用固定模板；尚未实现围绕运行中任务自由对话和自然语言意图路由。旧JSON交互可加`--input-mode json`。

原结构化CLI支持环境变量配置，字段见[.env.example](.env.example)；应用**不自动加载.env文件**。交互终端使用隐藏输入直接注入内存，无需配置环境变量。结构化请求需自行提供唯一request_id和未来、带时区的deadline_at，格式见[Request契约](contracts/request.schema.json)。

## 评测复核

普通自动测试为离线运行。20场景实际证据与所有历史失败已经保存，无需重新付费即可阅读[最终判定](examples/live/core20/20261031T110356Z-93ca1d21/final-assessment.json)。

```powershell
# 仅审计已提交产物与当时Git来源；需本地有该提交，零HTTP
git worktree add --detach ../xiaoying-evidence-29e 29e3a7163dd28ad8cc5c1e7f8f9e2c2c94d36a0f
.venv/Scripts/python.exe -X utf8 ../xiaoying-evidence-29e/examples/tests/core20/audit_artifacts.py ../xiaoying-evidence-29e/examples/live/core20/20261031T110356Z-93ca1d21

# 如需新的付费20例评测，在当前项目目录显式运行（将提示输入密钥）
.venv/Scripts/python.exe -X utf8 -m scripts.evaluate_core20 --live --key-stdin
```

POSIX同样替换解释器路径。历史审计命令在独立工作树核验原版本；当前树已合并旧来源文档，不能声称仍与冻结版本相同。新评测单独记录当前代码、数据、文档和契约的哈希及Git状态，不覆盖旧记录；新运行需要可用的Git工作树，来源或Git信息不可用时会在提示密钥前停止。最近一次新运行及其未提交修改的来源快照见[评估](docs/03-evaluation.md)。浅克隆缺少历史Git对象时需先取得历史。实际SQLite库是本地运行产物，不提交Git；仓库的`evidence.json`包含事件、请求及plan的可读快照。`--recheck <run目录>`需要原runtime.db才能重读物理数据库；仅克隆仓库时使用上方产物审计，或离线测试重新创建临时库。

## 项目结构与数据

```text
README.md
pyproject.toml / requirements*.lock / .env.example
src/content_planner/       应用、模型适配、工具、图、存储与导出
  data/                    唯一运行资料源：合成素材、报价、检索别名
contracts/                 JSON Schema与领域数据fixture
scripts/                   交互入口、真实评测、安装验证
tests/                     单元与CLI验收测试
examples/                  输入、实际输出、Trace、评测与测试结果
docs/                      仅五篇文档：需求、方案、评估、AI使用、复盘
AGENTS.md / HANDOFF.md      开发协作规则与接手记录，非运行依赖
```

Python包内`src/content_planner/data/`承担题目中的data目录职责，随wheel一起安装，使用`importlib.resources`读取，不依赖工作目录。数据说明见[包内资料](src/content_planner/data/README.md)。`.venv`、work、build、dist、真实密钥、缓存及SQLite工作库均不提交。

## 当前边界

仅支持合成产品“影芽剪辑”的有限素材、单素材/单脚本/两档制作方案，费用为模拟整数单位；不制作视频、不接真实发布/支付，不支持同一任务多进程并发。营销扩写在当前核心评测中单列质量备注，未新增独立语义审核；历史严格内容评估的失败记录保留。恢复结果未持久化的外部请求可能再次发出，不承诺API exactly-once。详细限制与首次异常复测记录统一见[评估](docs/03-evaluation.md)。
