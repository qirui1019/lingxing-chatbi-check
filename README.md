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
$env:LINGXING_RUN_INTEGRATION = "1"
python -m pytest tests/test_cases.py -v
```

## 输入内容放哪里

具体文件位置和格式见 [docs/input-contract.md](docs/input-contract.md)。

真实密钥、数据库密码等敏感信息放在 `configs/env.local.yml`，这个文件已被 git 忽略。
