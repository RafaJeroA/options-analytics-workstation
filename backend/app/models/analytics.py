from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
PositiveFiniteFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
SpotMove = Annotated[float, Field(gt=-1, allow_inf_nan=False)]
ForwardDays = Annotated[int, Field(ge=0)]


class AnalyticsState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class ScenarioExpirationState(StrEnum):
    PRE_EXPIRY = "pre_expiry"
    AT_OR_AFTER_EXPIRY = "at_or_after_expiry"
    MIXED = "mixed"
    NO_OPTION_LEGS = "no_option_legs"


class PricingAssumptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valuation_date: date = Field(default_factory=date.today)
    underlying_price: PositiveFiniteFloat
    risk_free_rate: FiniteFloat = 0.0425
    dividend_yield: FiniteFloat = 0.0
    volatility_shift: FiniteFloat = 0.0
    days_forward: ForwardDays = 0


class ScenarioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    underlying_moves_pct: list[SpotMove] = Field(
        default_factory=lambda: [-0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20],
        min_length=1,
    )
    implied_vol_shifts: list[FiniteFloat] = Field(
        default_factory=lambda: [-0.10, -0.05, 0.0, 0.05, 0.10], min_length=1
    )
    days_forward: list[ForwardDays] = Field(default_factory=lambda: [0, 7, 14, 30], min_length=1)
    valuation_date: date = Field(default_factory=date.today)
    risk_free_rate: FiniteFloat = 0.0425
    dividend_yield: FiniteFloat = 0.0

    @field_validator("underlying_moves_pct", "implied_vol_shifts", "days_forward")
    @classmethod
    def require_unique_dimensions(cls, values: list[float] | list[int]) -> list[float] | list[int]:
        if len(values) != len(set(values)):
            raise ValueError("scenario dimensions must contain unique values")
        return values


class ScenarioPoint(BaseModel):
    underlying_price: PositiveFiniteFloat
    move_pct: SpotMove
    vol_shift: FiniteFloat
    days_forward: ForwardDays
    current_value: FiniteFloat | None = None
    theoretical_value: FiniteFloat | None = None
    pnl_open: FiniteFloat | None = None


class ScenarioDayState(BaseModel):
    days_forward: ForwardDays
    expiration_state: ScenarioExpirationState
    volatility_shift_effective: bool | None = None
    message: str | None = None


class ScenarioGridResult(BaseModel):
    strategy_name: str
    underlying_symbol: str
    base_underlying_price: PositiveFiniteFloat
    points: list[ScenarioPoint]
    pricing_state: AnalyticsState = AnalyticsState.COMPLETE
    status_message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    volatility_shift_effective: bool | None = None
    day_states: list[ScenarioDayState] = Field(default_factory=list)
