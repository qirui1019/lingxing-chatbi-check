from __future__ import annotations

import argparse
from pathlib import Path

from lingxing_chatbi_check.config import load_env_config
from lingxing_chatbi_check.feishu.case_generator import write_case_templates
from lingxing_chatbi_check.reports.feishu_uploader import (
    generate_feishu_mapping,
    upload_report_dir_to_feishu,
)
from lingxing_chatbi_check.runners.batch_runner import run_cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Lingxing MCP and ChatBI checker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run enabled cases")
    run_parser.add_argument("--cases", default="configs/cases")
    run_parser.add_argument("--env", default="configs/env.local.yml")
    run_parser.add_argument("--reports", default="reports")
    run_parser.add_argument(
        "--upload-feishu",
        action="store_true",
        help="upload generated report files and fill Feishu sheet result cells",
    )

    generate_parser = subparsers.add_parser(
        "generate-cases",
        help="generate case templates from exported Feishu Excel",
    )
    generate_parser.add_argument(
        "--source",
        default="data/feishu/lingxing_mcp_tools.xlsx",
    )
    generate_parser.add_argument("--output", default="configs/cases")

    upload_parser = subparsers.add_parser(
        "upload-feishu",
        help="upload existing report files and fill Feishu sheet result cells",
    )
    upload_parser.add_argument("--report-dir", required=True)
    upload_parser.add_argument("--env", default="configs/env.local.yml")

    mapping_parser = subparsers.add_parser(
        "generate-feishu-mapping",
        help="generate Feishu row mapping from existing reports without uploading",
    )
    mapping_parser.add_argument("--report-dir", required=True)
    mapping_parser.add_argument("--env", default="configs/env.local.yml")

    args = parser.parse_args()
    if args.command == "run":
        reports = run_cases(
            case_dir=Path(args.cases),
            env_config_path=Path(args.env),
            reports_root=Path(args.reports),
            upload_feishu=args.upload_feishu,
        )
        print(f"Generated {len(reports)} report files.")
        for report in reports:
            print(report)
    elif args.command == "generate-cases":
        paths = write_case_templates(Path(args.source), Path(args.output))
        print(f"Generated {len(paths)} case templates.")
        for path in paths:
            print(path)
    elif args.command == "upload-feishu":
        env_config = load_env_config(Path(args.env))
        summary = upload_report_dir_to_feishu(
            Path(args.report_dir),
            env_config.get("feishu") or {},
        )
        print(f"Filled {summary.matched_count} Feishu result cells.")
        if summary.mapping_path:
            print(f"Mapping file: {summary.mapping_path}")
        if summary.unmatched_reports:
            print("Unmatched reports:")
            for report in summary.unmatched_reports:
                print(report)
    elif args.command == "generate-feishu-mapping":
        env_config = load_env_config(Path(args.env))
        mapping_path = generate_feishu_mapping(
            Path(args.report_dir),
            env_config.get("feishu") or {},
        )
        print(f"Mapping file: {mapping_path}")


if __name__ == "__main__":
    main()
