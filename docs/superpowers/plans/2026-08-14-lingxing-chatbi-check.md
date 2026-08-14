# 领星 ChatBI 校验项目实施计划

> **给后续执行者：** 如果继续按 Superpowers 流程推进实现，使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans` 按任务执行。本文件中的复选框用于跟踪任务状态。

**目标：** 创建领星 MCP tool 出参和 Doris/MySQL ChatBI 表自动校验项目的初始 Python 骨架。

**架构：** 项目采用配置驱动：读取 YAML case，调用外部客户端，清洗为 pandas DataFrame，按维度和指标对比，并输出 Excel 报告。MCP 和 Doris/MySQL 都封装在客户端边界里，方便在没有真实凭证时先用样例和测试推进。

**技术栈：** Python 3.12、pytest、pandas、openpyxl、PyYAML、SQLAlchemy、PyMySQL、MCP Python SDK。

## 全局约束

- MCP 用户配置只保存 key 别名和 `x_mcp_key`，不维护店铺列表；店铺是 case 参数。
- 真实密钥放在 `configs/env.local.yml`，不要提交。
- case 配置放在 `configs/cases/*.yml`。
- tool 出参样例放在 `data/samples/mcp_outputs/*.json`。
- 生成的验证报告放在 `reports/`。

---

### 任务 1：case 和配置契约

**文件：**
- 创建：`tests/test_case_loader.py`
- 创建：`src/lingxing_chatbi_check/cases/models.py`
- 创建：`src/lingxing_chatbi_check/cases/loader.py`
- 创建：`src/lingxing_chatbi_check/config.py`

**接口：**
- 产出：`load_case(path: Path) -> CaseSpec`
- 产出：`load_cases(directory: Path) -> list[CaseSpec]`
- 产出：`load_env_config(path: Path) -> dict[str, Any]`
- 产出：`get_mcp_user_config(config: dict[str, Any], user_key: str) -> dict[str, str]`

- [x] **步骤 1：先写失败测试**

测试会创建一个临时 YAML case 文件，读取后断言 `tool.name`、`database.table`、`compare.dimensions`、`auth.user_key` 等字段。

- [x] **步骤 2：运行失败测试**

运行：`pytest tests/test_case_loader.py -v`

预期：生产模块还不存在时，导入失败。

- [x] **步骤 3：实现最小 loader 和 dataclass**

添加 `AuthSpec`、`ToolSpec`、`DatabaseSpec`、`CompareSpec`、`CaseSpec`，并实现 YAML 读取和缺失文件报错。

- [x] **步骤 4：运行测试**

运行：`pytest tests/test_case_loader.py -v`

预期：测试通过。

### 任务 2：DataFrame 对比

**文件：**
- 创建：`tests/test_dataframe_compare.py`
- 创建：`src/lingxing_chatbi_check/comparators/dataframe_compare.py`

**接口：**
- 产出：`ComparisonResult`
- 产出：`compare_dataframes(tool_df: pandas.DataFrame, db_df: pandas.DataFrame, dimensions: list[str], metrics: list[str], tolerance: float = 0.0) -> ComparisonResult`

- [x] **步骤 1：先写失败测试**

测试覆盖指标完全一致和指标值不一致两种场景。

- [x] **步骤 2：运行失败测试**

运行：`pytest tests/test_dataframe_compare.py -v`

预期：对比模块还不存在时，导入失败。

- [x] **步骤 3：实现对比逻辑**

按维度 outer join tool 和数据库结果。每个指标计算 tool 值、数据库值、绝对差异和是否通过。

- [x] **步骤 4：运行测试**

运行：`pytest tests/test_dataframe_compare.py -v`

预期：测试通过。

### 任务 3：客户端和 runner 骨架

**文件：**
- 创建：`src/lingxing_chatbi_check/clients/lingxing_mcp.py`
- 创建：`src/lingxing_chatbi_check/clients/doris_mysql.py`
- 创建：`src/lingxing_chatbi_check/clients/feishu_sheet.py`
- 创建：`src/lingxing_chatbi_check/cleaners/base.py`
- 创建：`src/lingxing_chatbi_check/cleaners/registry.py`
- 创建：`src/lingxing_chatbi_check/reports/excel_report.py`
- 创建：`src/lingxing_chatbi_check/runners/case_runner.py`
- 创建：`tests/test_smoke_imports.py`

**接口：**
- 产出：`LingxingMcpClient.call_tool(tool_name: str, arguments: dict[str, Any]) -> Any`
- 产出：`DorisMysqlClient.query(sql: str, params: Mapping[str, Any] | None = None) -> pandas.DataFrame`
- 产出：`write_excel_report(path: Path, result: ComparisonResult, context: Mapping[str, Any]) -> Path`
- 产出：`run_case(case: CaseSpec, env_config: dict[str, Any], output_dir: Path) -> Path`

- [x] **步骤 1：先写 smoke import 测试**

导入公开模块，确认类和函数存在。

- [x] **步骤 2：运行失败测试**

运行：`pytest tests/test_smoke_imports.py -v`

预期：文件不存在时导入失败。

- [x] **步骤 3：实现骨架**

添加客户端类、真实方法签名和保守的错误信息。外部 SDK 尽量放在方法内部导入，保证本地测试不需要真实连接。

- [x] **步骤 4：运行测试**

运行：`pytest -v`

预期：本地测试通过。

### 任务 4：项目文档和示例

**文件：**
- 创建：`pyproject.toml`
- 创建：`README.md`
- 创建：`docs/input-contract.md`
- 创建：`configs/env.example.yml`
- 创建：`configs/cases/example_tool__example_table.yml`
- 创建：`.gitignore`

**接口：**
- 产出：飞书导出、MCP 样例、数据库配置、case YAML、报告目录的明确说明。

- [x] **步骤 1：添加项目元数据和依赖**

创建 `pyproject.toml`，写入包信息和 pytest 配置。

- [x] **步骤 2：添加示例配置**

创建不包含真实密钥的安全模板。

- [x] **步骤 3：添加输入约定文档**

说明你需要提供什么，以及每类文件应该放在哪里。

- [x] **步骤 4：运行验证**

运行：`pytest -v`

预期：本地测试通过。

## 自检

- 规格覆盖：计划覆盖了配置、MCP 认证、Doris 查询、清洗、对比、报告、示例和用户输入位置。
- 占位检查：没有需要继续补全的占位说明。
- 类型一致性：公开函数名和类型签名前后一致。
