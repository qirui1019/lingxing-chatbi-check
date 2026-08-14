def test_public_scaffold_imports() -> None:
    from lingxing_chatbi_check.cases.loader import load_case, load_cases
    from lingxing_chatbi_check.clients.doris_mysql import DorisMysqlClient
    from lingxing_chatbi_check.clients.lingxing_mcp import LingxingMcpClient
    from lingxing_chatbi_check.comparators.dataframe_compare import compare_dataframes
    from lingxing_chatbi_check.reports.excel_report import write_excel_report
    from lingxing_chatbi_check.runners.case_runner import run_case

    assert load_case is not None
    assert load_cases is not None
    assert DorisMysqlClient is not None
    assert LingxingMcpClient is not None
    assert compare_dataframes is not None
    assert write_excel_report is not None
    assert run_case is not None
