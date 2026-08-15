from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.analytics import AnalyticsState, PricingAssumptions
from app.models.market import InstrumentType, OptionContract, OptionQuote

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
PositiveFiniteFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegativeFiniteFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
PositiveInteger = Annotated[int, Field(gt=0)]


class StrategyLeg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leg_id: str
    instrument_type: InstrumentType = InstrumentType.OPTION
    side: str
    quantity: PositiveInteger = 1
    contract: OptionContract | None = None
    quote: OptionQuote | None = None
    entry_price: NonNegativeFiniteFloat | None = None
    stock_price: PositiveFiniteFloat | None = None
    underlying_symbol: str | None = None

    @field_validator("side")
    @classmethod
    def validate_side(cls, value: str) -> str:
        lowered = value.lower()
        if lowered not in {"long", "short"}:
            raise ValueError("side must be either 'long' or 'short'")
        return lowered

    @model_validator(mode="after")
    def validate_instrument_fields(self) -> StrategyLeg:
        if self.instrument_type == InstrumentType.OPTION:
            if self.contract is None:
                raise ValueError("option legs require a contract")
            if self.quote is not None and self.quote.contract != self.contract:
                raise ValueError("option leg quote contract must match the leg contract")
        else:
            if self.contract is not None or self.quote is not None:
                raise ValueError("stock legs cannot include an option contract or option quote")
            if self.stock_price is None and (self.entry_price is None or self.entry_price <= 0.0):
                raise ValueError("stock legs require a positive stock_price or entry_price")
            if not self.underlying_symbol or not self.underlying_symbol.strip():
                raise ValueError("stock legs require an underlying_symbol")
        return self


class StrategyDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    template: str | None = None
    underlying_symbol: str
    underlying_price: PositiveFiniteFloat
    legs: list[StrategyLeg] = Field(default_factory=list)

    @field_validator("underlying_symbol")
    @classmethod
    def normalize_underlying_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("underlying_symbol must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_leg_symbols(self) -> StrategyDefinition:
        for leg in self.legs:
            leg_symbol = leg.contract.symbol if leg.contract is not None else leg.underlying_symbol
            if leg_symbol is not None and leg_symbol.strip().upper() != self.underlying_symbol:
                raise ValueError(
                    f"leg {leg.leg_id!r} symbol {leg_symbol!r} does not match strategy symbol {self.underlying_symbol!r}"
                )
        return self


class PayoffPoint(BaseModel):
    spot: NonNegativeFiniteFloat
    value: FiniteFloat


class PayoffMetricState(StrEnum):
    FINITE = "finite"
    UNLIMITED = "unlimited"
    UNAVAILABLE = "unavailable"


class BreakevenInterval(BaseModel):
    start: NonNegativeFiniteFloat
    end: NonNegativeFiniteFloat | None = None


class StrategyLegValuation(BaseModel):
    leg_id: str
    market_value: FiniteFloat | None = None
    theoretical_value: FiniteFloat | None = None
    entry_value: FiniteFloat | None = None
    pnl_open: FiniteFloat | None = None
    warnings: list[str] = Field(default_factory=list)


class StrategyValuation(BaseModel):
    strategy_name: str
    underlying_symbol: str
    assumptions: PricingAssumptions
    net_debit_credit: FiniteFloat | None = None
    entry_cost: FiniteFloat | None = None
    current_value: FiniteFloat | None = None
    theoretical_value: FiniteFloat | None = None
    pnl_open: FiniteFloat | None = None
    max_profit: FiniteFloat | None = None
    max_loss: FiniteFloat | None = None
    max_profit_state: PayoffMetricState = PayoffMetricState.UNAVAILABLE
    max_loss_state: PayoffMetricState = PayoffMetricState.UNAVAILABLE
    breakevens: list[NonNegativeFiniteFloat] = Field(default_factory=list)
    breakeven_intervals: list[BreakevenInterval] = Field(default_factory=list)
    payoff: list[PayoffPoint] = Field(default_factory=list)
    legs: list[StrategyLegValuation] = Field(default_factory=list)
    pricing_state: AnalyticsState = AnalyticsState.COMPLETE
    status_message: str | None = None
    warnings: list[str] = Field(default_factory=list)
