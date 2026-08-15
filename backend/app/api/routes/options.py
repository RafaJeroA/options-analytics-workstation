from __future__ import annotations

from fastapi import APIRouter, Depends

from app.models.market import OptionQuote
from app.services.market_service import MarketService, get_market_service

router = APIRouter()


@router.get("/{contract_id}/quote", response_model=OptionQuote)
def option_quote(
    contract_id: str,
    market_service: MarketService = Depends(get_market_service),
) -> OptionQuote:
    return market_service.get_option_quote(contract_id)
