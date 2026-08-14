# 飞书表格来源

## 当前表格

飞书链接：

```text
https://u1veu0gombm.feishu.cn/wiki/QlOawEX8Aim10xkNTgIcIZeRnDf?from=from_copylink&sheet=APRmoj
```

## 使用约定

- `mcp_tool_list` 表格：列举所有 tool list，只作为参考。
- `可用tool` 表格：作为后续自动化校验的主要来源。

`可用tool` 表格需要重点读取这些信息：

- 调用哪个 MCP tool。
- 对应哪个 ChatBI 数据库表。
- 需要查询哪些指标。
- 使用哪些筛选维度。
- tool 参数和数据库查询条件之间的对应关系。
- 指标别名、单位换算和口径说明。

## 本地导出文件位置

如果飞书页面无法通过接口或浏览器直接读取，请将表格导出为 Excel 或 CSV 后放到：

```text
data/feishu/
```

建议命名：

```text
data/feishu/lingxing_tool_mapping.xlsx
data/feishu/lingxing_tool_mapping.csv
```
