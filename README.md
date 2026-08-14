# 领星 ChatBI 校验项目

这个项目用于自动校验领星 MCP tool 出参和 Doris/MySQL 中的 ChatBI 数据是否一致。

## 项目会做什么

1. 从 `configs/cases/*.yml` 读取验证用例。
2. 通过 Streamable HTTP 调用配置好的领星 MCP tool。
3. 将 MCP 出参清洗成 pandas DataFrame。
4. 查询 Doris/MySQL 中对应的 ChatBI 数据。
5. 按配置的维度和指标进行对比。
6. 每个 tool/table 用例在 `reports/` 下输出一份 Excel 验证报告。

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pytest -v
```

默认测试只跑本地单元测试，不会连接领星 MCP 或 Doris/MySQL。需要执行真实集成校验时，再设置：

```powershell
python -m lingxing_chatbi_check run --cases configs/cases --env configs/env.local.yml --reports reports
```

一次运行会在 `reports/` 下创建一个时间命名的文件夹，例如：

```text
reports/2026-08-14_14-35-20/
```

每个启用的 case 输出一份 Excel，文件名格式为：

```text
<tool名>__<ChatBI表名>.xlsx
```

## 从飞书导出生成 case 模板

飞书导出的 Excel 放在 `data/feishu/lingxing_mcp_tools.xlsx` 后，可以运行：

```powershell
python -m lingxing_chatbi_check generate-cases --source data/feishu/lingxing_mcp_tools.xlsx --output configs/cases
```

生成的 case 默认是：

```yaml
enabled: false
```

检查 SQL、字段映射和口径后，再改成 `enabled: true`。

字段映射规则：

```yaml
compare:
  metric_mappings:
    spends: cost
```

左边是 tool 出参字段，右边是 ChatBI 字段。对比报告会保留 `tool.spends` 和 `db.cost`，不会把原字段名提前抹掉。

## 输入内容放哪里

具体文件位置和格式见 [docs/input-contract.md](docs/input-contract.md)。

真实密钥、数据库密码等敏感信息放在 `configs/env.local.yml`，这个文件已被 git 忽略。
