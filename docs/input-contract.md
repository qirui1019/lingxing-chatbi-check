# 输入内容约定

这份文档说明你需要提供哪些内容，以及这些内容应该放在哪里。

## 1. 本地环境配置

在本地创建这个文件：

```text
configs/env.local.yml
```

可以参考 `configs/env.example.yml` 里的模板。

MCP 多用户配置只保存 key 的别名和 `x_mcp_key`：

```yaml
lingxing_mcp:
  url: "https://openmcp.lingxing.com/mcp-servers/lingxing-mcp"
  users:
    default:
      x_mcp_key: "你的当前 MCP key"
    user_a:
      x_mcp_key: "另一个用户的 MCP key"
```

不要在用户配置下维护店铺列表。店铺、日期、SKU、站点、市场等筛选条件，都放到具体 case 的参数里。

Doris/MySQL 配置示例：

```yaml
doris_mysql:
  host: "你的 Doris 地址"
  port: 9030
  user: "你的数据库用户名"
  password: "你的数据库密码"
  database: "你的数据库名"
  charset: "utf8mb4"
```

## 2. 验证用例配置

每个验证用例放一个 YAML 文件：

```text
configs/cases/<tool_name>__<chatbi_table>.yml
```

示例：

```yaml
enabled: false
name: "销售汇总 vs chatbi.sale_report_msku_order"

auth:
  mode: all_users

scope:
  shop_discovery: get_my_sids
  listing_mapping: erp_listing

tool:
  name: "query_product_performance_asin_lists"
  arguments:
    start_date: "2026-08-01"
    end_date: "2026-08-07"
    date_type: "purchase"
    summary_field: "asin"
    turn_on_summary: 1
  dynamic_arguments:
    shop_argument: sids
    shop_batch_mode: list
    source_field: sid
    batch_size: 50
    database_param: sid_values

database:
  table: "chatbi.sale_report_msku_order"
  sql: |
    select
      sid,
      asin,
      report_date,
      order_units,
      order_sales_amount
    from chatbi.sale_report_msku_order
    where sid in :sid_values
      and report_date between :start_date and :end_date
  params:
    start_date: "2026-08-01"
    end_date: "2026-08-07"

compare:
  dimensions:
    - sid
    - asin
    - report_date
  metrics:
    - order_units
    - order_sales_amount
  dimension_mappings:
    sid: sid
    asin: asin
    report_date: report_date
  metric_mappings:
    volume: order_units
    amount: order_sales_amount
  tolerance: 0.01
```

这里的 `auth.mode: all_users` 表示运行时遍历 `configs/env.local.yml` 里的所有 MCP key。case 不需要写具体店铺。

`scope.shop_discovery` 决定用哪个辅助 tool 获取授权店铺：

- 销售、库存类通常用 `get_my_sids`，返回 `sid`。
- 广告类通常用 `ad_auth_shops`，返回 `profile_id` 和 `sid`。

`tool.dynamic_arguments` 决定如何把授权店铺注入目标 tool：

- `shop_argument`：目标 tool 的店铺入参字段，例如 `sids`、`sid`、`profile_ids`。
- `shop_batch_mode`：`single` 表示一次查一个店铺；`list` 表示一次传一批店铺。
- `source_field`：从授权店铺结果里取哪个字段，例如 `sid` 或 `profile_id`。
- `database_param`：注入 SQL 参数的名称，例如 `sid_values` 或 `profile_id_values`。

`compare.dimension_mappings` 和 `compare.metric_mappings` 决定 tool 出参字段和数据库字段的对应关系：

```yaml
compare:
  dimension_mappings:
    profile_id: sid
    report_date: report_date
  metric_mappings:
    spends: cost
    direct_orders: same_orders
```

左边是领星 tool 出参字段，右边是 ChatBI 数据库字段。程序不会在清洗阶段强行改名，而是在对比前按这个映射统一比较；报告明细里会保留 `tool.<字段>` 和 `db.<字段>`，方便排查。

从飞书生成 case 时，`metric_mappings` 会按“出参字段”和“对应数据库字段”的顺序一一生成。比如：

```text
spends -> cost
sales -> sales
impressions -> impressions
```

## 3. MCP tool 出参样例

tool 原始出参样例放这里：

```text
data/samples/mcp_outputs/
```

建议命名：

```text
data/samples/mcp_outputs/get_sales_summary.json
data/samples/mcp_outputs/get_inventory_detail.json
```

每个文件保存领星 MCP tool 返回的原始结果。如果 MCP Inspector 同时展示 structured response 和 text response，优先保留完整 JSON 外壳，后续清洗器会按实际结构处理。

## 4. 可选的数据库结果样例

如果暂时不连 Doris/MySQL，也可以先放数据库查询结果样例：

```text
data/samples/db_outputs/
```

建议命名：

```text
data/samples/db_outputs/ads_sales_day.json
```

内容使用对象数组：

```json
[
  {
    "shop_id": "shop_001",
    "date": "2026-08-01",
    "sku": "SKU001",
    "sales_amount": 12.34,
    "order_count": 2
  }
]
```

## 5. 飞书表格

当前飞书来源记录在 [docs/feishu-source.md](feishu-source.md)。

现阶段你可以直接把飞书表格链接或导出文件给我。项目里已经预留了 `feishu_sheet.py` 适配层，但最终实现方式要看我们后面选择 API token、导出的 Excel/CSV，还是连接器。

当前约定：

- `mcp_tool_list` 表格只作为所有 tool 的参考清单。
- `可用tool` 表格作为自动生成校验 case 的主要来源。

飞书表格至少需要包含：

- MCP tool 名称。
- ChatBI 数据库表名。
- tool 参数字段和示例值。
- 数据库筛选维度。
- 对比维度。
- 对比指标。
- 指标别名、单位换算、口径说明。

从飞书导出的 Excel 生成 case 模板：

```powershell
python -m lingxing_chatbi_check generate-cases --source data/feishu/lingxing_mcp_tools.xlsx --output configs/cases
```

生成规则：

- 一个 case 对应一个 MCP tool 和一张 ChatBI 表。
- `mcp_tool_list` 只作为参考。
- `可用tool` 是生成 case 的主要来源。
- 生成的 case 默认 `enabled: false`，确认 SQL 和字段口径后再启用。

## 6. 验证报告

生成的 Excel 验证报告会写到这里：

```text
reports/
```

每个 case 输出一份报告，文件名由 tool 名和 ChatBI 表名组成。

## 7. 执行真实集成校验

默认执行 `python -m pytest -v` 时只跑本地单元测试，不会连接领星 MCP 或 Doris/MySQL。

确认 `configs/env.local.yml` 和 `configs/cases/*.yml` 都已经配置好后，再手动开启真实集成校验：

```powershell
python -m lingxing_chatbi_check run --cases configs/cases --env configs/env.local.yml --reports reports
```

一次运行会创建一个时间命名的报告目录，例如：

```text
reports/2026-08-14_14-35-20/
```

每个启用 case 输出一份报告：

```text
<tool名>__<ChatBI表名>.xlsx
```

同一次运行里，店铺发现结果会缓存在该报告目录的 `_runtime/` 下，多个 case 使用相同辅助 tool 时不会重复查询。
