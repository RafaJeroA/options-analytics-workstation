from __future__ import annotations

from datetime import datetime

from app.db.sqlite import SQLiteStore
from app.models.user import WatchlistItem


class WatchlistRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def list_items(self) -> list[WatchlistItem]:
        items: list[WatchlistItem] = []
        for row in self.store.list_watchlist():
            row["created_at"] = datetime.fromisoformat(str(row["created_at"]))
            items.append(WatchlistItem(**row))
        return items

    def add_item(self, symbol: str, note: str | None = None) -> WatchlistItem:
        row = self.store.upsert_watchlist(symbol=symbol, note=note)
        row["created_at"] = datetime.fromisoformat(str(row["created_at"]))
        return WatchlistItem(**row)
