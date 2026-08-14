from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote_plus

import pandas as pd


class DorisMysqlClient:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        charset: str = "utf8mb4",
    ) -> None:
        self.host = host
        self.port = int(port)
        self.user = user
        self.password = password
        self.database = database
        self.charset = charset

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "DorisMysqlClient":
        return cls(
            host=str(config["host"]),
            port=int(config.get("port", 9030)),
            user=str(config["user"]),
            password=str(config["password"]),
            database=str(config["database"]),
            charset=str(config.get("charset", "utf8mb4")),
        )

    def query(
        self,
        sql: str,
        params: Mapping[str, Any] | None = None,
    ) -> pd.DataFrame:
        try:
            from sqlalchemy import bindparam, create_engine, text
        except ImportError as exc:
            raise RuntimeError(
                "Database dependencies are not installed. Run `python -m pip install -e .`."
            ) from exc

        statement = text(sql)
        for key, value in dict(params or {}).items():
            if isinstance(value, (list, tuple, set)):
                statement = statement.bindparams(bindparam(key, expanding=True))

        engine = create_engine(self._sqlalchemy_url())
        with engine.connect() as connection:
            return pd.read_sql_query(statement, connection, params=dict(params or {}))

    def _sqlalchemy_url(self) -> str:
        user = quote_plus(self.user)
        password = quote_plus(self.password)
        return (
            f"mysql+pymysql://{user}:{password}@{self.host}:{self.port}/"
            f"{self.database}?charset={self.charset}"
        )
