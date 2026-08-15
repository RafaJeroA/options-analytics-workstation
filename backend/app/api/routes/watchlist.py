from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from app.models.user import WatchlistItem
from app.services.market_service import get_watchlist_repository
from app.services.repositories.watchlist import WatchlistRepository

router = APIRouter()


@router.get("", response_model=list[WatchlistItem])
def list_watchlist(
    repository: WatchlistRepository = Depends(get_watchlist_repository),
) -> list[WatchlistItem]:
    return repository.list_items()


@router.post("", response_model=WatchlistItem)
def add_watchlist_item(
    symbol: str = Body(embed=True),
    note: str | None = Body(default=None, embed=True),
    repository: WatchlistRepository = Depends(get_watchlist_repository),
) -> WatchlistItem:
    return repository.add_item(symbol=symbol, note=note)
