from __future__ import annotations

from datetime import date, datetime, timezone

from app.services.normalization.market import NormalizationContext, normalize_option_quote

VALUATION_CONTEXT = NormalizationContext(
    valuation_datetime=datetime(2026, 3, 26, 15, 30, tzinfo=timezone.utc),
    risk_free_rate=0.041,
    dividend_yield=0.012,
)


def _base_payload() -> dict[str, object]:
    return {
        "contract_id": "TEST-2026-04-17-100.00-C",
        "symbol": "TEST",
        "exchange": "SMART",
        "currency": "USD",
        "expiration": date(2026, 4, 17).isoformat(),
        "strike": 100,
        "right": "call",
        "timestamp": "2026-03-26T15:30:00+00:00",
        "market_data_mode": "delayed",
        "is_delayed": True,
    }


def test_normalizer_prefers_broker_model_values_when_available() -> None:
    payload = {
        **_base_payload(),
        "bid": 5.1,
        "ask": 5.4,
        "last": 5.2,
        "broker_implied_vol": 0.24,
        "broker_model_price": 5.28,
        "broker_greeks": {
            "delta": 0.54,
            "gamma": 0.04,
            "theta": -0.09,
            "vega": 0.18,
        },
    }

    quote = normalize_option_quote(
        payload,
        underlying_price=101.0,
        context=VALUATION_CONTEXT,
        expect_broker_model=True,
    )

    assert quote.implied_vol == 0.24
    assert quote.model_price == 5.28
    assert quote.greeks is not None
    assert quote.greeks.source == "broker_model"
    assert quote.greeks.delta == 0.54
    assert quote.model_source == "broker_model"
    assert "local_greeks" not in {flag.value for flag in quote.data_flags}
    assert "missing_broker_model" not in {flag.value for flag in quote.data_flags}


def test_normalizer_falls_back_to_local_model_when_broker_values_missing() -> None:
    payload = {
        **_base_payload(),
        "bid": 5.1,
        "ask": 5.3,
        "last": 5.2,
    }

    quote = normalize_option_quote(
        payload,
        underlying_price=101.0,
        context=VALUATION_CONTEXT,
        expect_broker_model=True,
    )

    flag_names = {flag.value for flag in quote.data_flags}

    assert quote.implied_vol is not None
    assert quote.greeks is not None
    assert quote.greeks.source == "local_model"
    assert quote.model_source == "local_model"
    assert "local_greeks" in flag_names
    assert "missing_broker_model" in flag_names


def test_normalizer_flags_missing_bid_ask_and_unusable_mark() -> None:
    payload = {
        **_base_payload(),
        "contract_id": "TEST-2026-04-17-120.00-P",
        "strike": 120,
        "right": "put",
        "last": 20.5,
    }

    quote = normalize_option_quote(payload, underlying_price=100.0, context=VALUATION_CONTEXT)
    flag_names = {flag.value for flag in quote.data_flags}

    assert quote.mark is None
    assert quote.last == 20.5
    assert "missing_bid" in flag_names
    assert "missing_ask" in flag_names
    assert "unusable_mark" in flag_names
    assert "invalid_for_iv" in flag_names


def test_normalizer_preserves_quote_clocks_and_frozen_mode() -> None:
    payload = {
        **_base_payload(),
        "bid": 5.1,
        "ask": 5.3,
        "market_data_mode": "delayed_frozen",
        "exchange_timestamp": "2026-03-26T15:29:00+00:00",
        "received_at": "2026-03-26T15:30:00+00:00",
    }

    quote = normalize_option_quote(payload, underlying_price=101.0, context=VALUATION_CONTEXT)

    assert quote.market_data_mode == "delayed_frozen"
    assert quote.mark == 5.2
    assert quote.exchange_timestamp == datetime(2026, 3, 26, 15, 29, tzinfo=timezone.utc)
    assert quote.received_at == VALUATION_CONTEXT.valuation_datetime
    assert {"delayed", "frozen", "reference_only"}.issubset({flag.value for flag in quote.data_flags})


def test_delayed_frozen_missing_sides_retains_last_without_inventing_mark() -> None:
    payload = {
        **_base_payload(),
        "bid": None,
        "ask": None,
        "last": 5.2,
        "market_data_mode": "delayed_frozen",
    }

    quote = normalize_option_quote(payload, underlying_price=101.0, context=VALUATION_CONTEXT)
    flags = {flag.value for flag in quote.data_flags}

    assert quote.bid is None
    assert quote.ask is None
    assert quote.last == 5.2
    assert quote.mark is None
    assert {"missing_bid", "missing_ask", "unusable_mark", "frozen", "reference_only"}.issubset(flags)


def test_delayed_frozen_crossed_market_never_becomes_a_mark() -> None:
    payload = {
        **_base_payload(),
        "bid": 5.4,
        "ask": 5.1,
        "last": 5.2,
        "market_data_mode": "delayed_frozen",
    }

    quote = normalize_option_quote(payload, underlying_price=101.0, context=VALUATION_CONTEXT)
    flags = {flag.value for flag in quote.data_flags}

    assert quote.last == 5.2
    assert quote.mark is None
    assert {"crossed_market", "unusable_mark", "frozen", "reference_only"}.issubset(flags)


def test_unconfirmed_provenance_is_unavailable_even_with_bid_and_ask() -> None:
    payload = {
        **_base_payload(),
        "bid": 5.1,
        "ask": 5.3,
        "market_data_mode": "unconfirmed",
        "is_delayed": False,
    }

    quote = normalize_option_quote(payload, underlying_price=101.0, context=VALUATION_CONTEXT)

    assert quote.market_data_unavailable is True
    assert quote.mark is None
    assert "market_data_unavailable" in {flag.value for flag in quote.data_flags}


def test_broker_receipt_time_is_not_substituted_for_missing_exchange_time() -> None:
    payload = {
        **_base_payload(),
        "bid": 5.1,
        "ask": 5.3,
        "timestamp": VALUATION_CONTEXT.valuation_datetime.isoformat(),
        "exchange_timestamp": None,
        "received_at": VALUATION_CONTEXT.valuation_datetime.isoformat(),
        "market_data_mode": "delayed_frozen",
    }

    quote = normalize_option_quote(payload, underlying_price=101.0, context=VALUATION_CONTEXT)

    assert quote.exchange_timestamp is None
    assert quote.received_at == VALUATION_CONTEXT.valuation_datetime
    assert "stale" not in {flag.value for flag in quote.data_flags}


def test_normalizer_flags_crossed_and_wide_markets() -> None:
    crossed = {
        **_base_payload(),
        "bid": 5.4,
        "ask": 5.1,
        "last": 5.2,
    }
    wide = {
        **_base_payload(),
        "contract_id": "TEST-2026-04-17-110.00-C",
        "strike": 110,
        "bid": 1.0,
        "ask": 2.0,
        "last": 1.5,
    }

    crossed_quote = normalize_option_quote(crossed, underlying_price=100.0, context=VALUATION_CONTEXT)
    wide_quote = normalize_option_quote(wide, underlying_price=100.0, context=VALUATION_CONTEXT)

    crossed_flags = {flag.value for flag in crossed_quote.data_flags}
    wide_flags = {flag.value for flag in wide_quote.data_flags}

    assert "crossed_market" in crossed_flags
    assert "wide_spread" in wide_flags


def test_normalizer_preserves_permission_limited_quote_flags() -> None:
    payload = {
        **_base_payload(),
        "market_data_unavailable": True,
        "subscription_missing": True,
    }

    quote = normalize_option_quote(
        payload,
        underlying_price=100.0,
        context=VALUATION_CONTEXT,
        expect_broker_model=True,
    )
    flag_names = {flag.value for flag in quote.data_flags}

    assert quote.market_data_unavailable is True
    assert quote.subscription_missing is True
    assert "market_data_unavailable" in flag_names
    assert "subscription_missing" in flag_names
    assert "missing_broker_model" in flag_names
