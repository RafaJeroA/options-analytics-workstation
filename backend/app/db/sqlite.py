from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    symbol TEXT PRIMARY KEY,
                    note TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS recent_chains (
                    symbol TEXT PRIMARY KEY,
                    viewed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS saved_strategies (
                    strategy_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def list_watchlist(self) -> list[dict[str, str | None]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT symbol, note, created_at FROM watchlist ORDER BY symbol ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_watchlist(self, symbol: str, note: str | None = None) -> dict[str, str | None]:
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO watchlist(symbol, note, created_at)
                VALUES(?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                  note = excluded.note
                """,
                (symbol.upper(), note, created_at),
            )
            row = connection.execute(
                "SELECT symbol, note, created_at FROM watchlist WHERE symbol = ?",
                (symbol.upper(),),
            ).fetchone()
        return (
            dict(row)
            if row is not None
            else {"symbol": symbol.upper(), "note": note, "created_at": created_at}
        )

    def set_setting(self, key: str, value: dict[str, object]) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value_json, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                  value_json = excluded.value_json,
                  updated_at = excluded.updated_at
                """,
                (key, json.dumps(value), updated_at),
            )

    def get_setting(self, key: str) -> dict[str, object] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT value_json FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["value_json"])

    def touch_recent_chain(self, symbol: str) -> None:
        viewed_at = datetime.now(timezone.utc).isoformat()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO recent_chains(symbol, viewed_at)
                VALUES(?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                  viewed_at = excluded.viewed_at
                """,
                (symbol.upper(), viewed_at),
            )

    def list_recent_chains(self, limit: int = 20) -> list[dict[str, str]]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT symbol, viewed_at
                FROM recent_chains
                ORDER BY viewed_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_strategy(self, strategy_id: str, name: str, payload: dict[str, object]) -> dict[str, str]:
        updated_at = datetime.now(timezone.utc).isoformat()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO saved_strategies(strategy_id, name, payload_json, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(strategy_id) DO UPDATE SET
                  name = excluded.name,
                  payload_json = excluded.payload_json,
                  updated_at = excluded.updated_at
                """,
                (strategy_id, name, json.dumps(payload), updated_at),
            )
            row = connection.execute(
                """
                SELECT strategy_id, name, payload_json, updated_at
                FROM saved_strategies
                WHERE strategy_id = ?
                """,
                (strategy_id,),
            ).fetchone()
        return (
            dict(row)
            if row is not None
            else {
                "strategy_id": strategy_id,
                "name": name,
                "payload_json": json.dumps(payload),
                "updated_at": updated_at,
            }
        )

    def list_saved_strategies(self) -> list[dict[str, str]]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT strategy_id, name, payload_json, updated_at
                FROM saved_strategies
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_saved_strategy(self, strategy_id: str) -> bool:
        with self.connection() as connection:
            result = connection.execute(
                "DELETE FROM saved_strategies WHERE strategy_id = ?",
                (strategy_id,),
            )
        return result.rowcount > 0
