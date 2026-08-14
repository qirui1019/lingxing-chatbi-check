from pathlib import Path
import os

import pytest

from lingxing_chatbi_check.cases.loader import load_case
from lingxing_chatbi_check.config import load_env_config
from lingxing_chatbi_check.runners.case_runner import run_case


CASE_DIR = Path("configs/cases")
ENV_CONFIG = Path("configs/env.local.yml")

if os.environ.get("LINGXING_RUN_INTEGRATION") != "1":
    pytest.skip(
        "未设置 LINGXING_RUN_INTEGRATION=1，跳过真实 MCP/Doris 集成用例。",
        allow_module_level=True,
    )

if not ENV_CONFIG.exists():
    pytest.skip(
        "未找到 configs/env.local.yml，跳过真实 MCP/Doris 集成用例。",
        allow_module_level=True,
    )


@pytest.mark.parametrize("case_path", sorted(CASE_DIR.glob("*.yml")))
def test_configured_case(case_path: Path) -> None:
    env_config = load_env_config(ENV_CONFIG)
    case = load_case(case_path)
    if not case.enabled:
        pytest.skip(f"case 未启用：{case_path}")
    run_case(case, env_config, Path("reports"))
