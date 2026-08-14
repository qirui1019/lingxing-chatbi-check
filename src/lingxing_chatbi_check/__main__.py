from __future__ import annotations

import argparse
from pathlib import Path

from lingxing_chatbi_check.feishu.case_generator import write_case_templates
from lingxing_chatbi_check.runners.batch_runner import run_cases


def main() -> None:
    parser = argparse.ArgumentParser(description="领星 MCP 和 ChatBI 自动校验工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="运行已启用的 case")
    run_parser.add_argument("--cases", default="configs/cases")
    run_parser.add_argument("--env", default="configs/env.local.yml")
    run_parser.add_argument("--reports", default="reports")

    generate_parser = subparsers.add_parser(
        "generate-cases",
        help="从飞书导出的 Excel 生成 case 模板",
    )
    generate_parser.add_argument(
        "--source",
        default="data/feishu/lingxing_mcp_tools.xlsx",
    )
    generate_parser.add_argument("--output", default="configs/cases")

    args = parser.parse_args()
    if args.command == "run":
        reports = run_cases(
            case_dir=Path(args.cases),
            env_config_path=Path(args.env),
            reports_root=Path(args.reports),
        )
        print(f"本次运行生成 {len(reports)} 份报告。")
        for report in reports:
            print(report)
    elif args.command == "generate-cases":
        paths = write_case_templates(Path(args.source), Path(args.output))
        print(f"已生成 {len(paths)} 个 case 模板。")
        for path in paths:
            print(path)


if __name__ == "__main__":
    main()
