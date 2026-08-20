from typing import Any

from lingxing_chatbi_check.clients.feishu_sheet import FeishuSheetClient


class RecordingFeishuSheetClient(FeishuSheetClient):
    def __init__(self) -> None:
        super().__init__(
            app_id="app",
            app_secret="secret",
            spreadsheet_token="spreadsheet123",
        )
        self.requests: list[dict[str, Any]] = []

    def _tenant_token(self) -> str:
        return "tenant-token"

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        *,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        self.requests.append(
            {
                "method": method,
                "path": path,
                "payload": payload,
                "authenticated": authenticated,
            }
        )
        if path == "/open-apis/drive/v1/files/create_folder":
            return {"code": 0, "data": {"token": "created-folder-token"}}
        return {"code": 0}


def test_write_values_uses_feishu_update_values_endpoint_without_range_path() -> None:
    client = RecordingFeishuSheetClient()

    client.write_values("sheet123!G2:G2", [["value"]])

    assert client.requests == [
        {
            "method": "PUT",
            "path": "/open-apis/sheets/v2/spreadsheets/spreadsheet123/values",
            "payload": {
                "valueRange": {
                    "range": "sheet123!G2:G2",
                    "values": [["value"]],
                }
            },
            "authenticated": True,
        }
    ]


def test_create_folder_uses_feishu_drive_create_folder_endpoint() -> None:
    client = RecordingFeishuSheetClient()

    token = client.create_folder("search_term_2026.08.18_15-30-00", "folder123")

    assert token == "created-folder-token"
    assert client.requests == [
        {
            "method": "POST",
            "path": "/open-apis/drive/v1/files/create_folder",
            "payload": {
                "name": "search_term_2026.08.18_15-30-00",
                "folder_token": "folder123",
            },
            "authenticated": True,
        }
    ]
