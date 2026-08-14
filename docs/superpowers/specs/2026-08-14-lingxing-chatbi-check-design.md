# 领星 ChatBI 校验项目设计

## 目标

搭建一个 Python 自动化项目：自动调用领星 MCP tool，将 tool 出参清洗成表格数据；再用相同维度查询 Doris/MySQL 中的 ChatBI 表；最后对比指标并为每个 tool/table case 输出一份 Excel 验证报告。

## 架构

项目采用配置驱动。连接配置放在 `configs/`，测试用例放在 `configs/cases/`，tool 出参样例放在 `data/samples/`，生成的报告放在 `reports/`。

运行时拆成几个边界清楚的小模块：

- `clients/lingxing_mcp.py`：通过 `X-Mcp-Key` 连接领星 Streamable HTTP MCP 服务。
- `clients/doris_mysql.py`：通过 SQLAlchemy 查询 Doris/MySQL。
- `cases/loader.py`：读取 YAML case 文件，并转换成类型化对象。
- `cleaners/`：将 MCP 出参和数据库查询结果转换成可对比的 pandas DataFrame。
- `comparators/`：按维度对齐行，并比较指标值。
- `reports/`：输出包含汇总和明细的 Excel 报告。
- `runners/case_runner.py`：编排单个验证用例。
- `tests/test_cases.py`：pytest 中真实 case 的执行入口。

## 认证模型

MCP 用户配置只保存 key，不保存店铺。店铺和其他筛选条件来自飞书表格或 YAML case 参数。这样认证信息和测试范围是分开的，后续扩展多用户时也更轻。

示例：

```yaml
lingxing_mcp:
  url: "https://openmcp.lingxing.com/mcp-servers/lingxing-mcp"
  users:
    default:
      x_mcp_key: "..."
    user_a:
      x_mcp_key: "..."
```

每条 case 只选择使用哪个 key：

```yaml
auth:
  user_key: user_a
```

如果某个 case 请求了当前 key 无权访问的店铺，运行结果会在报告里记录 MCP 错误或空结果。

## 数据流

1. 读取本地环境配置。
2. 从 YAML 读取 case，后续也可以从飞书读取。
3. 根据 `auth.user_key` 找到对应的 MCP key。
4. 使用配置参数调用 MCP tool。
5. 将 MCP 响应清洗成 DataFrame。
6. 使用配置 SQL 查询 Doris/MySQL。
7. 将数据库结果清洗成 DataFrame。
8. 按配置的维度和指标对比。
9. 为该 case 输出 Excel 报告。

## 错误处理

连接失败、配置缺失、SQL 错误、MCP 调用失败、字段结构不匹配等问题，都应该让对应 case 失败，并给出可定位的信息。报告中需要包含 tool 名、表名、用户 key 别名、对比维度、对比指标和差异明细。

## 测试

初始测试覆盖：

- YAML case 读取。
- 多用户 MCP key 查找，并确认不绑定店铺。
- DataFrame 指标对比。

MCP 和 Doris 的真实调用属于外部系统集成测试，等真实密钥、样例和 case 配置齐全后再补充。
