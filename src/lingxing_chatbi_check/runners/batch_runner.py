from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lingxing_chatbi_check.cases.loader import load_cases
from lingxing_chatbi_check.cases.models import CaseSpec
from lingxing_chatbi_check.config import load_env_config
from lingxing_chatbi_check.reports.excel_report import write_run_log
from lingxing_chatbi_check.reports.feishu_uploader import upload_report_dir_to_feishu
from lingxing_chatbi_check.runners.case_runner import _safe_filename, run_case


def create_run_output_dir(
    reports_root: Path,
    now: datetime | None = None,
) -> Path:
    run_time = now or datetime.now()
    output_dir = reports_root / run_time.strftime("%Y-%m-%d_%H-%M-%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def report_filename_for_case(case: CaseSpec) -> str:
    return _safe_filename(f"{case.tool.name}__{case.database.table}.xlsx")


def run_cases(
    case_dir: Path,
    env_config_path: Path,
    reports_root: Path,
    *,
    upload_feishu: bool = False,
) -> list[Path]:
    env_config = load_env_config(env_config_path)
    output_dir = create_run_output_dir(reports_root)
    reports: list[Path] = []
    log_rows: list[dict] = []
    for case in load_cases(case_dir):
        if not case.enabled:
            continue
        case_report = run_case(case, env_config, output_dir)
        reports.extend(case_report.paths)
        log_rows.extend(case_report.log_rows)
    if log_rows:
        reports.append(write_run_log(output_dir / "run_log.xlsx", log_rows))
    if upload_feishu:
        upload_summary = upload_report_dir_to_feishu(
            output_dir,
            env_config.get("feishu") or {},
        )
        if upload_summary.mapping_path:
            reports.append(upload_summary.mapping_path)
    return reports
