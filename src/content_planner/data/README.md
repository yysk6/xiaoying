# 合成资料与规则

本目录是应用的唯一运行资料源，承担交付规范中的data目录职责。Python通过importlib.resources读取，JSON随wheel一起安装，因此从仓库外运行也能找到资料；不依赖当前工作目录或开发机绝对路径。

| 文件 | 用途 |
|---|---|
| [materials.json](materials.json) | 合成产品影芽剪辑的素材ID、标签、事实、费用和准备耗时 |
| [pricing.json](pricing.json) | 脚本定稿、basic/premium剪辑、审核的费用和串行耗时 |
| [aliases.json](aliases.json) | 检索词别名规范化规则 |
| [mock-scenario.json](mock-scenario.json) | 默认离线演示的显式Fake响应与动作，不是真实模型 |

M01/M02素材费1；加脚本2、basic剪辑4、审核1，合计8。premium剪辑8，合计12。对应串行工期90/135分钟。预算和费用为模拟整数单位，不等同API账单。

contracts/fixtures中保留契约测试基线，由测试检查与包内JSON一致；业务读取本目录。修改资料版本/内容会改变manifest，旧任务resume须拒绝不一致，历史show仍可查看。业务实现不按case_id选择方案。
