from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.db.sqlite import SQLiteStore
from app.models.strategy import StrategyDefinition
from app.models.user import RecentChainView, SavedStrategyRecord, UserSettings


class WorkspaceRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def list_recent_chains(self, limit: int = 20) -> list[RecentChainView]:
        return [
            RecentChainView(symbol=row["symbol"], viewed_at=datetime.fromisoformat(row["viewed_at"]))
            for row in self.store.list_recent_chains(limit=limit)
        ]

    def list_saved_strategies(self) -> list[SavedStrategyRecord]:
        records: list[SavedStrategyRecord] = []
        for row in self.store.list_saved_strategies():
            records.append(
                SavedStrategyRecord(
                    strategy_id=row["strategy_id"],
                    name=row["name"],
                    strategy=StrategyDefinition(**_decode_payload(row["payload_json"])),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
            )
        return records

    def save_strategy(
        self,
        *,
        strategy: StrategyDefinition,
        name: str,
        strategy_id: str | None = None,
    ) -> SavedStrategyRecord:
        persisted = self.store.save_strategy(
            strategy_id=strategy_id or str(uuid.uuid4()),
            name=name,
            payload=strategy.model_dump(mode="json"),
        )
        return SavedStrategyRecord(
            strategy_id=persisted["strategy_id"],
            name=persisted["name"],
            strategy=StrategyDefinition(**_decode_payload(persisted["payload_json"])),
            updated_at=datetime.fromisoformat(persisted["updated_at"]),
        )

    def delete_strategy(self, strategy_id: str) -> bool:
        return self.store.delete_saved_strategy(strategy_id)

    def load_settings(self) -> UserSettings:
        payload = self.store.get_setting("user_settings")
        if payload is None:
            return UserSettings()
        return UserSettings(**payload)

    def save_settings(self, settings: UserSettings) -> UserSettings:
        self.store.set_setting("user_settings", settings.model_dump(mode="json"))
        return self.load_settings()


def _decode_payload(payload_json: str) -> dict[str, Any]:
    import json

    return json.loads(payload_json)
