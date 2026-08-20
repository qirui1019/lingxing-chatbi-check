# 领星 ChatBI 数据校验

这个项目用于对比领星 MCP tool 返回结果和 ChatBI 数据库表结果，生成按指标拆分的 Excel 报告，并可选自动上传报告到飞书表格。

## 功能

- 从 `configs/cases/` 读取启用的 case，支持 `.yml` 和 `.yaml`。
- 调用领星 MCP tool，支持多用户、分页、重试、批次超时和分页汇总日志。
- 查询 Doris/MySQL 中的 ChatBI 表。
- 按 case 配置的维度和指标聚合后对比。
- 每个指标生成一个独立 Excel 文件，并生成 `run_log.xlsx`。
- 可选上传报告到飞书，并按飞书表里的 case、字段、月份自动填写查询结果。

## 本地初始化

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pytest
```

单元测试只使用本地样例和 mock，不会连接真实 MCP、数据库或飞书。

## 环境配置

复制示例配置：

```powershell
Copy-Item configs\env.example.yml configs\env.local.yml
```

然后在 `configs/env.local.yml` 中填写：

- `lingxing_mcp.users.*.x_mcp_key`
- Doris/MySQL 连接信息
- 飞书应用、表格和上传目录信息

`configs/env.local.yml` 已加入 `.gitignore`，不要提交真实密钥。

## 运行校验

运行所有 `enabled: true` 的 case：

```powershell
python -m lingxing_chatbi_check run
```

等价完整写法：

```powershell
python -m lingxing_chatbi_check run --cases configs/cases --env configs/env.local.yml --reports reports
```

运行后会在 `reports/<运行时间>/` 下生成：

- 每个指标一个 Excel 报告
- `run_log.xlsx`
- 如启用飞书上传，还会生成 `feishu_mapping.xlsx`

## 自动上传飞书

生成报告并自动上传、填写飞书：

```powershell
python -m lingxing_chatbi_check run --upload-feishu
```

仅对已有报告目录生成飞书位置映射，不上传：

```powershell
python -m lingxing_chatbi_check generate-feishu-mapping --report-dir reports\<运行时间>
```

仅上传已有报告目录：

```powershell
python -m lingxing_chatbi_check upload-feishu --report-dir reports\<运行时间>
```

飞书匹配依据主要是：

- tool 名称
- ChatBI 表名
- tool 字段
- DB 字段
- 报告文件名中的月份

未匹配到的报告会记录在 `feishu_mapping.xlsx` 中，`matched` 为 `false`。

## case 配置

case 文件放在 `configs/cases/`。常用字段：

- `enabled`: 是否运行该 case
- `tool.arguments`: 固定 tool 入参
- `tool.dynamic_arguments`: 是否按 sid/profile_id 动态分批传参
- `tool.pagination`: 分页参数、页大小、最大页数、批次超时
- `database.sql`: DB 查询 SQL
- `compare.dimensions`: 对比维度
- `compare.metric_mappings`: tool 指标到 DB 指标的映射

示例：

```yaml
compare:
  dimensions:
    - sid
    - report_date
  metric_mappings:
    spends: cost
```

左侧是 tool 字段，右侧是 DB 字段。

## 分页日志

运行时会打印每次 tool 调用的分页汇总：

```text
pagination_summary tool=... pages=... records=... total=... seconds=... max_pages_reached=False
```

如果出现：

```text
max_pages_reached=True
```

说明达到 `max_pages` 后停止，可能没有取完数据，需要提高 `max_pages` 或检查分页参数。
