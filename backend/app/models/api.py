from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.analytics import PricingAssumptions, ScenarioGridResult, ScenarioInput
from app.models.market import MarketDataMode
from app.models.strategy import StrategyDefinition
from app.models.user import UserSettings


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    data_mode: str
    database_ready: bool
    adapter_status: str


class UnderlyingSearchResult(BaseModel):
    symbol: str
    description: str
    exchange: str
    currency: str
    market_data_mode: MarketDataMode


class StrategyPricingRequest(BaseModel):
    strategy: StrategyDefinition
    assumptions: PricingAssumptions


class StrategyScenarioRequest(BaseModel):
    strategy: StrategyDefinition
    scenario: ScenarioInput


class StrategyScenarioResponse(ScenarioGridResult):
    pass


class SaveStrategyRequest(BaseModel):
    strategy_id: str | None = None
    name: str
    strategy: StrategyDefinition


class SaveSettingsRequest(BaseModel):
    settings: UserSettings
