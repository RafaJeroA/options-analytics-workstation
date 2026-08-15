from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.strategy import StrategyDefinition

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
PanelSize = Annotated[int, Field(ge=10, le=50)]


class WatchlistItem(BaseModel):
    symbol: str
    note: str | None = None
    created_at: datetime


class RecentChainView(BaseModel):
    symbol: str
    viewed_at: datetime


class SavedStrategyRecord(BaseModel):
    strategy_id: str
    name: str
    strategy: StrategyDefinition
    updated_at: datetime


class UserSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: str = "dark"
    default_rate: FiniteFloat = 0.0425
    default_dividend_yield: FiniteFloat = 0.0
    watchlist_symbols: list[str] = Field(default_factory=list)
    recent_symbols: list[str] = Field(default_factory=list)
    selected_symbol: str | None = None
    left_panel_size: PanelSize = 18
    right_panel_size: PanelSize = 24
