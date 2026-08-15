from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.models.api import UnderlyingSearchResult
from app.models.market import ChainSnapshot, UnderlyingQuote
from app.services.market_service import MarketService, get_market_service, get_store

router = APIRouter()


@router.get("/search", response_model=list[UnderlyingSearchResult])
def search_underlyings(
    q: str = Query(min_length=1),
    market_service: MarketService = Depends(get_market_service),
) -> list[UnderlyingSearchResult]:
    return [UnderlyingSearchResult(**item) for item in market_service.search_underlyings(q)]


@router.get("/{symbol}/summary", response_model=UnderlyingQuote)
def underlying_summary(
    symbol: str,
    market_service: MarketService = Depends(get_market_service),
) -> UnderlyingQuote:
    return market_service.get_underlying_summary(symbol)


@router.get("/{symbol}/chains", response_model=ChainSnapshot)
def option_chain(
    symbol: str,
    expiration: str | None = Query(default=None),
    market_service: MarketService = Depends(get_market_service),
) -> ChainSnapshot:
    chain = market_service.get_chain(symbol, expiration)
    get_store().touch_recent_chain(symbol)
    return chain
