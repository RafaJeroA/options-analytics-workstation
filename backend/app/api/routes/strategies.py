from __future__ import annotations

import json
from functools import lru_cache

from fastapi import APIRouter

from app.core.config import get_settings
from app.models.api import StrategyPricingRequest, StrategyScenarioRequest, StrategyScenarioResponse
from app.models.strategy import StrategyValuation
from app.quant.strategy import build_scenario_grid, value_strategy
from app.services.cache import KeyedLockPool, TTLCache

router = APIRouter()


@lru_cache
def _pricing_cache() -> TTLCache:
    return TTLCache(ttl_seconds=get_settings().strategy_pricing_cache_ttl_seconds)


@lru_cache
def _scenario_cache() -> TTLCache:
    return TTLCache(ttl_seconds=get_settings().strategy_scenario_cache_ttl_seconds)


@lru_cache
def _cache_locks() -> KeyedLockPool:
    return KeyedLockPool()


def _payload_key(payload: StrategyPricingRequest | StrategyScenarioRequest) -> tuple[str]:
    return (json.dumps(payload.model_dump(mode="json"), sort_keys=True),)


@router.post("/price", response_model=StrategyValuation)
def price_strategy(payload: StrategyPricingRequest) -> StrategyValuation:
    cache_key = _payload_key(payload)
    cached = _pricing_cache().get(cache_key)
    if cached is not None:
        return cached

    with _cache_locks().hold(("price", *cache_key)):
        cached = _pricing_cache().get(cache_key)
        if cached is not None:
            return cached

        valuation = value_strategy(payload.strategy, payload.assumptions)
        _pricing_cache().set(cache_key, valuation)
        return valuation


@router.post("/scenario-grid", response_model=StrategyScenarioResponse)
def scenario_grid(payload: StrategyScenarioRequest) -> StrategyScenarioResponse:
    cache_key = _payload_key(payload)
    cached = _scenario_cache().get(cache_key)
    if cached is not None:
        return cached

    with _cache_locks().hold(("scenario-grid", *cache_key)):
        cached = _scenario_cache().get(cache_key)
        if cached is not None:
            return cached

        result = StrategyScenarioResponse(
            **build_scenario_grid(payload.strategy, payload.scenario).model_dump()
        )
        _scenario_cache().set(cache_key, result)
        return result
