from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd


class FeishuSheetClient:
    def __init__(
        self,
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
        spreadsheet_token: str | None = None,
        sheet_id: str | None = None,
        file_folder_token: str | None = None,
        file_url_prefix: str | None = None,
        base_url: str = "https://open.feishu.cn",
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.spreadsheet_token = spreadsheet_token
        self.sheet_id = sheet_id
        self.file_folder_token = file_folder_token
        self.file_url_prefix = file_url_prefix or "https://www.feishu.cn/file/"
        self.base_url = base_url.rstrip("/")
        self._tenant_access_token: str | None = None

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "FeishuSheetClient":
        return cls(
            app_id=str(config.get("app_id") or ""),
            app_secret=str(config.get("app_secret") or ""),
            spreadsheet_token=str(config.get("spreadsheet_token") or ""),
            sheet_id=str(config.get("sheet_id") or ""),
            file_folder_token=str(config.get("file_folder_token") or ""),
            file_url_prefix=(
                str(config["file_url_prefix"])
                if config.get("file_url_prefix")
                else None
            ),
            base_url=str(config.get("base_url") or "https://open.feishu.cn"),
        )

    def read_exported_excel(self, path: Path, sheet_name: str | int = 0) -> pd.DataFrame:
        if not path.exists():
            raise FileNotFoundError(f"Feishu export not found: {path}")
        return pd.read_excel(path, sheet_name=sheet_name)

    def read_remote_sheet(self) -> pd.DataFrame:
        raise NotImplementedError(
            "Remote Feishu access needs the final access method: API token, exported file, or connector."
        )

    def upload_file(self, path: Path, folder_token: str | None = None) -> str:
        folder = folder_token or self.file_folder_token
        if not folder:
            raise ValueError("Feishu file_folder_token is required to upload reports")
        if not path.exists():
            raise FileNotFoundError(f"Report file not found: {path}")

        response = self._request_multipart(
            "/open-apis/drive/v1/files/upload_all",
            fields={
                "file_name": path.name,
                "parent_type": "explorer",
                "parent_node": folder,
                "size": str(path.stat().st_size),
            },
            file_field="file",
            file_path=path,
        )
        data = response.get("data") or {}
        if data.get("url"):
            return str(data["url"])
        file_token = data.get("file_token") or data.get("token")
        if not file_token:
            raise ValueError(f"Feishu upload response missing file token: {response}")
        return f"{self.file_url_prefix.rstrip('/')}/{file_token}"

    def create_folder(self, name: str, parent_folder_token: str | None = None) -> str:
        parent = parent_folder_token or self.file_folder_token
        if not parent:
            raise ValueError("Feishu file_folder_token is required to create folders")

        response = self._request_json(
            "POST",
            "/open-apis/drive/v1/files/create_folder",
            {"name": name, "folder_token": parent},
        )
        data = response.get("data") or {}
        folder_token = (
            data.get("folder_token")
            or data.get("token")
            or data.get("file_token")
        )
        if not folder_token:
            raise ValueError(f"Feishu create folder response missing token: {response}")
        return str(folder_token)

    def write_values(self, cell_range: str, values: list[list[Any]]) -> None:
        if not self.spreadsheet_token:
            raise ValueError("Feishu spreadsheet_token is required to write values")
        self._request_json(
            "PUT",
            f"/open-apis/sheets/v2/spreadsheets/{self.spreadsheet_token}/values",
            {"valueRange": {"range": cell_range, "values": values}},
        )

    def read_values(self, cell_range: str) -> list[list[Any]]:
        if not self.spreadsheet_token:
            raise ValueError("Feishu spreadsheet_token is required to read values")
        encoded_range = quote(cell_range, safe="")
        response = self._request_json(
            "GET",
            f"/open-apis/sheets/v2/spreadsheets/{self.spreadsheet_token}/values/{encoded_range}",
            None,
        )
        value_range = response.get("data", {}).get("valueRange") or {}
        values = value_range.get("values") or []
        if not isinstance(values, list):
            raise ValueError(f"Feishu values response is not a list: {response}")
        return values

    def _tenant_token(self) -> str:
        if self._tenant_access_token:
            return self._tenant_access_token
        if not self.app_id or not self.app_secret:
            raise ValueError("Feishu app_id and app_secret are required")
        response = self._request_json(
            "POST",
            "/open-apis/auth/v3/tenant_access_token/internal",
            {"app_id": self.app_id, "app_secret": self.app_secret},
            authenticated=False,
        )
        token = response.get("tenant_access_token")
        if not token:
            raise ValueError(f"Feishu auth response missing tenant token: {response}")
        self._tenant_access_token = str(token)
        return self._tenant_access_token

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        *,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        body = (
            None
            if payload is None
            else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self._tenant_token()}"
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        return self._send(request)

    def _request_multipart(
        self,
        path: str,
        *,
        fields: dict[str, str],
        file_field: str,
        file_path: Path,
    ) -> dict[str, Any]:
        boundary = "----lingxing-chatbi-check-boundary"
        body = _multipart_body(
            boundary=boundary,
            fields=fields,
            file_field=file_field,
            file_path=file_path,
        )
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self._tenant_token()}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        return self._send(request)

    def _send(self, request: Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=120) as response:
                raw = response.read()
        except HTTPError as exc:
            raw = exc.read()
            raise RuntimeError(
                f"Feishu API request failed: {exc.code} {raw.decode('utf-8', 'replace')}"
            ) from exc
        payload = json.loads(raw.decode("utf-8"))
        code = payload.get("code", 0)
        if code not in (0, None):
            raise RuntimeError(f"Feishu API returned error: {payload}")
        return payload


def _multipart_body(
    *,
    boundary: str,
    fields: dict[str, str],
    file_field: str,
    file_path: Path,
) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks)
