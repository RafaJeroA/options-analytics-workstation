from __future__ import annotations

from fastapi import APIRouter, Depends

from app.models.market import TermStructurePoint, VolSurfacePoint
from app.services.market_service import MarketService, get_market_service

router = APIRouter()


@router.get("/skew", response_model=list[VolSurfacePoint])
def skew(
    symbol: str,
    expiration: str | None = None,
    market_service: MarketService = Depends(get_market_service),
) -> list[VolSurfacePoint]:
    return market_service.get_volatility_skew(symbol, expiration)


@router.get("/term-structure", response_model=list[TermStructurePoint])
def term_structure(
    symbol: str,
    market_service: MarketService = Depends(get_market_service),
) -> list[TermStructurePoint]:
    return market_service.get_term_structure(symbol)
