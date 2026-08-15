from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
PositiveFiniteFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegativeFiniteFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
PositiveInteger = Annotated[int, Field(gt=0)]
NonNegativeInteger = Annotated[int, Field(ge=0)]


class MarketDataMode(StrEnum):
    MOCK = "mock"
    UNCONFIRMED = "unconfirmed"
    DELAYED = "delayed"
    LIVE = "live"
    FROZEN = "frozen"
    DELAYED_FROZEN = "delayed_frozen"


class QuoteSource(StrEnum):
    BROKER = "broker"
    BROKER_MODEL = "broker_model"
    LOCAL_MODEL = "local_model"
    MOCK = "mock"


class TermStructureStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class DataQualityFlag(StrEnum):
    CROSSED_MARKET = "crossed_market"
    WIDE_SPREAD = "wide_spread"
    MISSING_BID = "missing_bid"
    MISSING_ASK = "missing_ask"
    MARKET_DATA_UNAVAILABLE = "market_data_unavailable"
    SUBSCRIPTION_MISSING = "subscription_missing"
    LOW_VOLUME = "low_volume"
    LOW_OPEN_INTEREST = "low_open_interest"
    STALE = "stale"
    UNUSABLE_MARK = "unusable_mark"
    SUSPICIOUS_MID = "suspicious_mid"
    INVALID_FOR_IV = "invalid_for_iv"
    DELAYED = "delayed"
    FROZEN = "frozen"
    REFERENCE_ONLY = "reference_only"
    LOCAL_GREEKS = "local_greeks"
    MISSING_BROKER_MODEL = "missing_broker_model"


class OptionRight(StrEnum):
    CALL = "call"
    PUT = "put"


class InstrumentType(StrEnum):
    OPTION = "option"
    STOCK = "stock"


class UnderlyingQuote(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str
    description: str
    exchange: str
    currency: str = "USD"
    con_id: int | None = None
    spot: PositiveFiniteFloat
    previous_close: PositiveFiniteFloat
    change: FiniteFloat
    change_percent: FiniteFloat
    timestamp: datetime
    exchange_timestamp: datetime | None = None
    received_at: datetime | None = None
    market_data_mode: MarketDataMode
    is_delayed: bool = False
    market_data_unavailable: bool = False
    subscription_missing: bool = False


class OptionContract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    contract_id: str
    con_id: int | None = None
    symbol: str
    exchange: str = "SMART"
    currency: str = "USD"
    expiration: date
    strike: PositiveFiniteFloat
    right: OptionRight
    multiplier: PositiveInteger = 100
    local_symbol: str | None = None
    trading_class: str | None = None


class OptionGreeks(BaseModel):
    delta: FiniteFloat | None = None
    gamma: FiniteFloat | None = None
    theta: FiniteFloat | None = None
    vega: FiniteFloat | None = None
    rho: FiniteFloat | None = None
    theoretical_price: NonNegativeFiniteFloat | None = None
    source: QuoteSource = QuoteSource.LOCAL_MODEL


class OptionQuote(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    contract: OptionContract
    bid: NonNegativeFiniteFloat | None = None
    ask: NonNegativeFiniteFloat | None = None
    last: NonNegativeFiniteFloat | None = None
    mark: NonNegativeFiniteFloat | None = None
    model_price: NonNegativeFiniteFloat | None = None
    volume: NonNegativeInteger | None = None
    open_interest: NonNegativeInteger | None = Field(default=None, alias="openInterest")
    market_data_unavailable: bool = False
    subscription_missing: bool = False
    implied_vol: PositiveFiniteFloat | None = None
    broker_implied_vol: PositiveFiniteFloat | None = None
    greeks: OptionGreeks | None = None
    intrinsic_value: NonNegativeFiniteFloat | None = None
    extrinsic_value: NonNegativeFiniteFloat | None = None
    data_flags: list[DataQualityFlag] = Field(default_factory=list)
    quote_source: QuoteSource = QuoteSource.MOCK
    model_source: QuoteSource = QuoteSource.LOCAL_MODEL
    market_data_mode: MarketDataMode = MarketDataMode.MOCK
    updated_at: datetime
    exchange_timestamp: datetime | None = None
    received_at: datetime | None = None
    is_delayed: bool = False


class ChainSnapshot(BaseModel):
    symbol: str
    underlying: UnderlyingQuote
    expirations: list[date]
    selected_expiration: date
    calls: list[OptionQuote]
    puts: list[OptionQuote]
    updated_at: datetime
    market_data_mode: MarketDataMode


class VolSurfacePoint(BaseModel):
    symbol: str
    expiration: date
    strike: PositiveFiniteFloat
    moneyness: PositiveFiniteFloat
    implied_vol: PositiveFiniteFloat
    option_right: OptionRight
    updated_at: datetime


class TermStructurePoint(BaseModel):
    symbol: str
    expiration: date
    days_to_expiry: int = Field(ge=0)
    atm_strike: PositiveFiniteFloat | None = None
    atm_iv: PositiveFiniteFloat | None = None
    method: str | None = None
    sample_size: int = Field(ge=0)
    status: TermStructureStatus
    updated_at: datetime
