from pathlib import Path

import pandas as pd

from lingxing_chatbi_check.reports.feishu_uploader import (
    generate_feishu_mapping,
    load_remote_template_rows,
    upload_report_dir_to_feishu,
)


class RecordingFeishuClient:
    def __init__(self) -> None:
        self.folders: list[tuple[str, str]] = []
        self.uploads: list[tuple[Path, str]] = []
        self.read_ranges: list[str] = []
        self.writes: list[tuple[str, list[list[str]]]] = []

    def read_values(self, cell_range: str) -> list[list[object]]:
        self.read_ranges.append(cell_range)
        return [
            [
                "tool vs chatbi表",
                "tool字段",
                "chatbi表字段",
                "聚合维度",
                "抽样对象",
                "抽样日期",
                "查询结果（异常数据：误差大于等于1%）",
            ],
            [
                "case5\n\nad_campaign_search_term_report\nvs\ncahtbi.sp_search_term_report",
                "spends",
                "cost",
                "sid",
                "用户授权sid",
                "2026-06-28",
                "",
            ],
        ]

    def create_folder(self, name: str, parent_folder_token: str) -> str:
        self.folders.append((name, parent_folder_token))
        return f"token-{name}"

    def upload_file(self, path: Path, folder_token: str) -> str:
        self.uploads.append((path, folder_token))
        return f"https://tenant.feishu.cn/file/{path.stem}"

    def write_values(self, cell_range: str, values: list[list[str]]) -> None:
        self.writes.append((cell_range, values))


def test_upload_report_dir_reads_remote_sheet_and_writes_matching_result_cell(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    report_file = report_dir / "search_term_cost_2026年6月.xlsx"
    pd.DataFrame([{"sid": "101", "tool.spends": 10}]).to_excel(
        report_file,
        index=False,
    )
    pd.DataFrame(
        [
            {
                "tool_name": "ad_campaign_search_term_report",
                "table_name": "chatbi.sp_search_term_report",
                "tool_field": "spends",
                "db_field": "cost",
                "report_file": report_file.name,
                "query_time": "2026.08.18",
                "result_count": 104,
                "exception_count": 4,
            }
        ]
    ).to_excel(report_dir / "run_log.xlsx", index=False)

    client = RecordingFeishuClient()

    summary = upload_report_dir_to_feishu(
        report_dir,
        {
            "sheet_id": "sheet123",
            "file_folder_token": "folder123",
            "upload_time_label": "2026.08.18_15-30-00",
        },
        client=client,
    )

    assert client.read_ranges == ["sheet123!A1:ZZ1000"]
    assert client.folders == [("search_term_2026.08.18_15-30-00", "folder123")]
    assert client.uploads == [(report_file, "token-search_term_2026.08.18_15-30-00")]
    assert client.writes == [
        (
            "sheet123!G2:G2",
            [
                [
                    "查询时间：2026.08.18\n"
                    "查询结果数量：104\n"
                    "异常数量：4\n"
                    "search_term_cost_2026年6月\n"
                    "https://tenant.feishu.cn/file/search_term_cost_2026年6月"
                ]
            ],
        )
    ]
    assert summary.matched_count == 1
    assert summary.unmatched_reports == []
    assert summary.mapping_path == report_dir / "feishu_mapping.xlsx"

    mapping = pd.read_excel(summary.mapping_path)
    record = mapping.to_dict("records")[0]
    assert record["report_file"] == "search_term_cost_2026年6月.xlsx"
    assert record["matched"] is True
    assert record["feishu_cell"] == "G2"
    assert record["upload_folder_name"] == "search_term_2026.08.18_15-30-00"
    assert record["upload_folder_token"] == "token-search_term_2026.08.18_15-30-00"
    assert record["report_link"] == "https://tenant.feishu.cn/file/search_term_cost_2026年6月"


def test_generate_feishu_mapping_does_not_upload_or_write_remote_sheet(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    report_file = report_dir / "search_term_cost_2026年6月.xlsx"
    pd.DataFrame([{"sid": "101", "tool.spends": 10}]).to_excel(
        report_file,
        index=False,
    )
    pd.DataFrame(
        [
            {
                "tool_name": "ad_campaign_search_term_report",
                "table_name": "chatbi.sp_search_term_report",
                "tool_field": "spends",
                "db_field": "cost",
                "report_file": report_file.name,
                "query_time": "2026.08.18",
                "result_count": 104,
                "exception_count": 4,
            }
        ]
    ).to_excel(report_dir / "run_log.xlsx", index=False)

    client = RecordingFeishuClient()

    mapping_path = generate_feishu_mapping(
        report_dir,
        {"sheet_id": "sheet123"},
        client=client,
    )

    assert client.read_ranges == ["sheet123!A1:ZZ1000"]
    assert client.folders == []
    assert client.uploads == []
    assert client.writes == []
    assert mapping_path == report_dir / "feishu_mapping.xlsx"

    mapping = pd.read_excel(mapping_path)
    assert mapping.to_dict("records")[0]["matched"] is True
    assert mapping.to_dict("records")[0]["feishu_cell"] == "G2"
    assert pd.isna(mapping.to_dict("records")[0]["report_link"])


def test_upload_report_dir_uses_result_column_for_report_month(tmp_path: Path) -> None:
    class MonthGroupedFeishuClient(RecordingFeishuClient):
        def read_values(self, cell_range: str) -> list[list[object]]:
            self.read_ranges.append(cell_range)
            return [
                [
                    "tool vs chatbi表",
                    "tool字段",
                    "chatbi表字段",
                    "聚合维度",
                    "抽样对象",
                    "2026年6月",
                    "",
                    "2026年7月",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "",
                    "",
                    "抽样日期",
                    "查询结果",
                    "抽样日期",
                    "查询结果",
                ],
                [
                    "case5\n\nad_campaign_search_term_report\nvs\nchatbi.sp_search_term_report",
                    "spends",
                    "cost",
                    "sid",
                    "用户授权sid",
                    "2026-06-28",
                    "",
                    "2026-07-28",
                    "",
                ],
            ]

    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    report_file = report_dir / "search_term_cost_2026年7月.xlsx"
    pd.DataFrame([{"sid": "101", "tool.spends": 10}]).to_excel(
        report_file,
        index=False,
    )
    pd.DataFrame(
        [
            {
                "tool_name": "ad_campaign_search_term_report",
                "table_name": "chatbi.sp_search_term_report",
                "tool_field": "spends",
                "db_field": "cost",
                "report_file": report_file.name,
                "query_time": "2026.08.19",
                "result_count": 104,
                "exception_count": 4,
            }
        ]
    ).to_excel(report_dir / "run_log.xlsx", index=False)

    client = MonthGroupedFeishuClient()

    summary = upload_report_dir_to_feishu(
        report_dir,
        {
            "sheet_id": "sheet123",
            "file_folder_token": "folder123",
            "upload_time_label": "2026.08.19_10-00-00",
        },
        client=client,
    )

    assert client.writes[0][0] == "sheet123!I3:I3"
    assert summary.matched_count == 1
    mapping = pd.read_excel(summary.mapping_path)
    assert mapping.to_dict("records")[0]["period"] == "2026-07"
    assert mapping.to_dict("records")[0]["feishu_cell"] == "I3"


def test_load_remote_template_rows_keeps_month_specific_result_columns() -> None:
    class MonthGroupedFeishuClient:
        def read_values(self, _cell_range: str) -> list[list[object]]:
            return [
                [
                    "tool vs chatbi表",
                    "tool字段",
                    "chatbi表字段",
                    "2026年6月",
                    "",
                    "2026年7月",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "抽样日期",
                    "查询结果",
                    "抽样日期",
                    "查询结果",
                ],
                [
                    "case5\n\nad_campaign_search_term_report\nvs\nchatbi.sp_search_term_report",
                    "spends",
                    "cost",
                    "2026-06-28",
                    "",
                    "2026-07-28",
                    "",
                ],
            ]

    rows = load_remote_template_rows(
        MonthGroupedFeishuClient(),
        sheet_id="sheet123",
        result_header="查询结果",
        read_range="A1:Z1000",
    )

    assert [(row.period, row.result_column) for row in rows] == [
        ("2026-06", "E"),
        ("2026-07", "G"),
    ]


def test_upload_report_dir_matches_continuation_row_for_report_month(
    tmp_path: Path,
) -> None:
    class ContinuationRowFeishuClient(RecordingFeishuClient):
        def read_values(self, cell_range: str) -> list[list[object]]:
            self.read_ranges.append(cell_range)
            return [
                [
                    "tool vs chatbi表",
                    "tool字段",
                    "chatbi表字段",
                    "聚合维度",
                    "抽样对象",
                    "抽样日期",
                    "查询结果（异常数据：误差大于0.1%）",
                ],
                [
                    "case5\n\nad_campaign_search_term_report\nvs\nchatbi.sp_search_term_report",
                    "spends",
                    "cost",
                    "sid",
                    "用户授权sid",
                    46174,
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "",
                    "",
                    46204,
                    "",
                ],
            ]

    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    report_file = report_dir / "search_term_cost_2026年7月.xlsx"
    pd.DataFrame([{"sid": "101", "tool.spends": 10}]).to_excel(
        report_file,
        index=False,
    )
    pd.DataFrame(
        [
            {
                "tool_name": "ad_campaign_search_term_report",
                "table_name": "chatbi.sp_search_term_report",
                "tool_field": "spends",
                "db_field": "cost",
                "report_file": report_file.name,
                "query_time": "2026.08.19",
                "result_count": 104,
                "exception_count": 4,
            }
        ]
    ).to_excel(report_dir / "run_log.xlsx", index=False)

    client = ContinuationRowFeishuClient()

    summary = upload_report_dir_to_feishu(
        report_dir,
        {
            "sheet_id": "sheet123",
            "file_folder_token": "folder123",
            "upload_time_label": "2026.08.19_10-00-00",
        },
        client=client,
    )

    assert client.writes[0][0] == "sheet123!G3:G3"
    assert summary.matched_count == 1
    mapping = pd.read_excel(summary.mapping_path)
    assert mapping.to_dict("records")[0]["period"] == "2026-07"
    assert mapping.to_dict("records")[0]["feishu_cell"] == "G3"
