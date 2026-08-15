from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from app.models.market import (
    ChainSnapshot,
    DataQualityFlag,
    MarketDataMode,
    OptionContract,
    OptionGreeks,
    OptionQuote,
    OptionRight,
    QuoteSource,
    UnderlyingQuote,
)
from app.quant.black_scholes import black_scholes_greeks, extrinsic_value, intrinsic_value
from app.quant.implied_volatility import solve_implied_volatility

UNSET_DOUBLE = 1.7976931348623157e308


@dataclass(frozen=True, slots=True)
class NormalizationContext:
    valuation_datetime: datetime
    risk_free_rate: float
    dividend_yield: float


def _default_context() -> NormalizationContext:
    return NormalizationContext(
        valuation_datetime=datetime.now(timezone.utc),
        risk_free_rate=0.0425,
        dividend_yield=0.0,
    )


def _parse_datetime(value: Any, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    return fallback or datetime.now(timezone.utc)


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"Could not parse date from {value!r}")


def _is_finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value) and value != UNSET_DOUBLE


def _float_or_none(value: Any, *, allow_negative: bool = False) -> float | None:
    if value in {None, ""}:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not _is_finite(numeric):
        return None
    if not allow_negative and numeric < 0.0:
        return None
    return numeric


def _int_or_none(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric >= 0 else None


def _valid_broker_iv(value: Any) -> float | None:
    numeric = _float_or_none(value)
    return numeric if numeric is not None and numeric > 0.0 else None


def _valid_spot(value: Any) -> float | None:
    numeric = _float_or_none(value)
    return numeric if numeric is not None and numeric > 0.0 else None


def _time_to_expiry(expiration: date, valuation_datetime: datetime) -> float:
    expiration_close = datetime.combine(expiration, datetime.max.time(), tzinfo=timezone.utc)
    return max((expiration_close - valuation_datetime).total_seconds(), 0.0) / (365.0 * 24.0 * 3600.0)


def _has_valid_quote_pair(bid: float | None, ask: float | None) -> bool:
    return bid is not None and ask is not None and bid > 0.0 and ask > 0.0 and ask >= bid


def _build_broker_greeks(
    payload: dict[str, Any],
    *,
    broker_model_price: float | None,
) -> OptionGreeks | None:
    broker_greeks = payload.get("broker_greeks") or {}
    delta = _float_or_none(broker_greeks.get("delta"), allow_negative=True)
    gamma = _float_or_none(broker_greeks.get("gamma"))
    theta = _float_or_none(broker_greeks.get("theta"), allow_negative=True)
    vega = _float_or_none(broker_greeks.get("vega"), allow_negative=True)
    if None in {delta, gamma, theta, vega, broker_model_price}:
        return None
    return OptionGreeks(
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=None,
        theoretical_price=broker_model_price,
        source=QuoteSource.BROKER_MODEL,
    )


def normalize_underlying_quote(
    payload: dict[str, Any],
    *,
    context: NormalizationContext | None = None,
) -> UnderlyingQuote:
    context = context or _default_context()
    market_data_mode = MarketDataMode(payload.get("market_data_mode", MarketDataMode.MOCK.value))
    spot = float(payload["spot"])
    previous_close = float(payload.get("previous_close", spot))
    change = float(payload.get("change", spot - previous_close))
    change_percent = float(
        payload.get(
            "change_percent",
            (change / previous_close * 100.0) if previous_close else 0.0,
        )
    )
    exchange_timestamp = (
        _parse_datetime(payload["exchange_timestamp"])
        if payload.get("exchange_timestamp") is not None
        else None
    )
    received_at = _parse_datetime(payload["received_at"]) if payload.get("received_at") is not None else None
    timestamp = _parse_datetime(
        payload.get("timestamp"),
        fallback=exchange_timestamp or received_at or context.valuation_datetime,
    )
    return UnderlyingQuote(
        symbol=str(payload["symbol"]).upper(),
        description=str(payload.get("description", payload["symbol"])),
        exchange=str(payload.get("exchange", "SMART")),
        currency=str(payload.get("currency", "USD")),
        con_id=_int_or_none(payload.get("con_id")),
        spot=spot,
        previous_close=previous_close,
        change=change,
        change_percent=change_percent,
        timestamp=timestamp,
        exchange_timestamp=exchange_timestamp,
        received_at=received_at,
        market_data_mode=market_data_mode,
        is_delayed=bool(
            payload.get(
                "is_delayed",
                market_data_mode in {MarketDataMode.DELAYED, MarketDataMode.DELAYED_FROZEN},
            )
        ),
        market_data_unavailable=bool(payload.get("market_data_unavailable", False)),
        subscription_missing=bool(payload.get("subscription_missing", False)),
    )


def normalize_search_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": str(payload["symbol"]).upper(),
        "description": str(payload.get("description", payload["symbol"])),
        "exchange": str(payload.get("exchange", "SMART")),
        "currency": str(payload.get("currency", "USD")),
        "market_data_mode": payload.get("market_data_mode", MarketDataMode.MOCK.value),
    }


def normalize_option_quote(
    payload: dict[str, Any],
    underlying_price: float,
    *,
    context: NormalizationContext | None = None,
    expect_broker_model: bool = False,
) -> OptionQuote:
    context = context or _default_context()
    exchange_timestamp = (
        _parse_datetime(payload["exchange_timestamp"])
        if payload.get("exchange_timestamp") is not None
        else None
    )
    received_at = _parse_datetime(payload["received_at"]) if payload.get("received_at") is not None else None
    updated_at = _parse_datetime(
        payload.get("timestamp"),
        fallback=exchange_timestamp or received_at or context.valuation_datetime,
    )
    right = OptionRight(str(payload["right"]).lower())
    contract = OptionContract(
        contract_id=str(payload["contract_id"]),
        con_id=_int_or_none(payload.get("con_id")),
        symbol=str(payload["symbol"]).upper(),
        exchange=str(payload.get("exchange", "SMART")),
        currency=str(payload.get("currency", "USD")),
        expiration=_parse_date(payload["expiration"]),
        strike=float(payload["strike"]),
        right=right,
        multiplier=int(payload.get("multiplier", 100)),
        local_symbol=payload.get("local_symbol"),
        trading_class=payload.get("trading_class"),
    )

    bid = _float_or_none(payload.get("bid"))
    ask = _float_or_none(payload.get("ask"))
    last = _float_or_none(payload.get("last"))
    raw_model_price = _float_or_none(payload.get("broker_model_price")) or _float_or_none(
        payload.get("model_price")
    )
    volume = _int_or_none(payload.get("volume"))
    open_interest = _int_or_none(payload.get("open_interest"))
    is_delayed = bool(payload.get("is_delayed", False))
    market_data_mode = MarketDataMode(payload.get("market_data_mode", MarketDataMode.MOCK.value))
    market_data_unavailable = bool(payload.get("market_data_unavailable", False)) or (
        market_data_mode == MarketDataMode.UNCONFIRMED
    )
    subscription_missing = bool(payload.get("subscription_missing", False))

    flags: list[DataQualityFlag] = []
    if bid is None:
        flags.append(DataQualityFlag.MISSING_BID)
    if ask is None:
        flags.append(DataQualityFlag.MISSING_ASK)
    if market_data_unavailable:
        flags.append(DataQualityFlag.MARKET_DATA_UNAVAILABLE)
    if subscription_missing:
        flags.append(DataQualityFlag.SUBSCRIPTION_MISSING)
    if bid is not None and ask is not None and bid > ask:
        flags.append(DataQualityFlag.CROSSED_MARKET)
    if is_delayed:
        flags.append(DataQualityFlag.DELAYED)
    if market_data_mode in {MarketDataMode.FROZEN, MarketDataMode.DELAYED_FROZEN}:
        flags.append(DataQualityFlag.FROZEN)
    if market_data_mode in {
        MarketDataMode.DELAYED,
        MarketDataMode.FROZEN,
        MarketDataMode.DELAYED_FROZEN,
    }:
        flags.append(DataQualityFlag.REFERENCE_ONLY)
    if volume is not None and volume < 25:
        flags.append(DataQualityFlag.LOW_VOLUME)
    if open_interest is not None and open_interest < 100:
        flags.append(DataQualityFlag.LOW_OPEN_INTEREST)
    staleness_timestamp = exchange_timestamp
    if staleness_timestamp is None and (market_data_mode == MarketDataMode.MOCK or received_at is None):
        staleness_timestamp = updated_at
    if (
        staleness_timestamp is not None
        and (context.valuation_datetime - staleness_timestamp).total_seconds() > 900
    ):
        flags.append(DataQualityFlag.STALE)

    valid_quote_pair = not market_data_unavailable and _has_valid_quote_pair(bid, ask)
    mark: float | None = None
    if valid_quote_pair:
        mark = round((bid + ask) / 2.0, 6)
        if ask - bid > max(0.12, mark * 0.18):
            flags.append(DataQualityFlag.WIDE_SPREAD)
    else:
        flags.append(DataQualityFlag.UNUSABLE_MARK)

    intrinsic = intrinsic_value(underlying_price, contract.strike, contract.right)
    if mark is None or mark <= 0.0:
        flags.append(DataQualityFlag.INVALID_FOR_IV)
    elif mark + 1e-6 < intrinsic:
        flags.append(DataQualityFlag.SUSPICIOUS_MID)
        flags.append(DataQualityFlag.INVALID_FOR_IV)

    broker_implied_vol = _valid_broker_iv(payload.get("broker_implied_vol"))
    broker_model_price = _float_or_none(payload.get("broker_model_price"))
    broker_greeks = _build_broker_greeks(payload, broker_model_price=broker_model_price)

    implied_vol: float | None = None
    greeks: OptionGreeks | None = None
    model_price = raw_model_price
    model_source = QuoteSource.MOCK if market_data_mode == MarketDataMode.MOCK else QuoteSource.BROKER

    if broker_implied_vol is not None and broker_greeks is not None:
        implied_vol = broker_implied_vol
        greeks = broker_greeks
        model_price = broker_model_price
        model_source = QuoteSource.BROKER_MODEL
    else:
        if expect_broker_model and market_data_mode != MarketDataMode.MOCK:
            flags.append(DataQualityFlag.MISSING_BROKER_MODEL)

        time_to_expiry = _time_to_expiry(contract.expiration, context.valuation_datetime)
        can_estimate_locally = valid_quote_pair and mark is not None and mark > 0.0 and time_to_expiry > 0.0
        if can_estimate_locally and DataQualityFlag.INVALID_FOR_IV not in flags:
            implied_vol = solve_implied_volatility(
                premium=mark,
                spot=underlying_price,
                strike=contract.strike,
                time_to_expiry=time_to_expiry,
                risk_free_rate=context.risk_free_rate,
                option_right=contract.right,
                dividend_yield=context.dividend_yield,
            )
            if implied_vol is None:
                flags.append(DataQualityFlag.INVALID_FOR_IV)
            else:
                local_greeks = black_scholes_greeks(
                    spot=underlying_price,
                    strike=contract.strike,
                    time_to_expiry=time_to_expiry,
                    risk_free_rate=context.risk_free_rate,
                    volatility=implied_vol,
                    option_right=contract.right,
                    dividend_yield=context.dividend_yield,
                )
                greeks = OptionGreeks(**local_greeks, source=QuoteSource.LOCAL_MODEL)
                model_price = local_greeks["theoretical_price"]
                model_source = QuoteSource.LOCAL_MODEL
                flags.append(DataQualityFlag.LOCAL_GREEKS)
        elif DataQualityFlag.INVALID_FOR_IV not in flags:
            flags.append(DataQualityFlag.INVALID_FOR_IV)

    return OptionQuote(
        contract=contract,
        bid=bid,
        ask=ask,
        last=last,
        mark=mark,
        model_price=model_price,
        volume=volume,
        openInterest=open_interest,
        market_data_unavailable=market_data_unavailable,
        subscription_missing=subscription_missing,
        implied_vol=implied_vol,
        broker_implied_vol=broker_implied_vol,
        greeks=greeks,
        intrinsic_value=intrinsic if mark is not None else None,
        extrinsic_value=extrinsic_value(mark, underlying_price, contract.strike, contract.right),
        data_flags=list(dict.fromkeys(flags)),
        quote_source=QuoteSource.MOCK if market_data_mode == MarketDataMode.MOCK else QuoteSource.BROKER,
        model_source=model_source,
        market_data_mode=market_data_mode,
        updated_at=updated_at,
        exchange_timestamp=exchange_timestamp,
        received_at=received_at,
        is_delayed=is_delayed,
    )


def normalize_chain_payload(
    payload: dict[str, Any],
    *,
    context: NormalizationContext | None = None,
    expect_broker_model: bool = False,
) -> ChainSnapshot:
    context = context or _default_context()
    underlying = normalize_underlying_quote(payload["underlying"], context=context)
    option_quotes = [
        normalize_option_quote(
            option_payload,
            underlying_price=underlying.spot,
            context=context,
            expect_broker_model=expect_broker_model,
        )
        for option_payload in payload.get("options", [])
    ]
    calls = [quote for quote in option_quotes if quote.contract.right == OptionRight.CALL]
    puts = [quote for quote in option_quotes if quote.contract.right == OptionRight.PUT]
    return ChainSnapshot(
        symbol=underlying.symbol,
        underlying=underlying,
        expirations=[_parse_date(item) for item in payload.get("expirations", [])],
        selected_expiration=_parse_date(payload["selected_expiration"]),
        calls=sorted(calls, key=lambda item: item.contract.strike),
        puts=sorted(puts, key=lambda item: item.contract.strike),
        updated_at=_parse_datetime(payload.get("updated_at"), fallback=context.valuation_datetime),
        market_data_mode=MarketDataMode(payload.get("market_data_mode", MarketDataMode.MOCK.value)),
    )
