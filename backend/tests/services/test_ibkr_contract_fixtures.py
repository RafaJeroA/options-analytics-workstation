from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.normalization.market import NormalizationContext, normalize_option_quote

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "ibkr_market_data.json"
VALUATION_TIME = datetime(2026, 7, 31, 15, 30, tzinfo=timezone.utc)
CONTEXT = NormalizationContext(
    valuation_datetime=VALUATION_TIME,
    risk_free_rate=0.04,
    dividend_yield=0.01,
)
BASE_QUOTE = {
    "contract_id": "SPY-2026-08-21-530.00-C",
    "con_id": 987654321,
    "local_symbol": "SPY   260821C00530000",
    "trading_class": "SPY",
    "symbol": "SPY",
    "exchange": "SMART",
    "currency": "USD",
    "expiration": "2026-08-21",
    "strike": 530.0,
    "right": "call",
    "multiplier": 100,
    "bid": 5.1,
    "ask": 5.3,
    "last": 5.2,
    "market_data_mode": "live",
    "is_delayed": False,
    "timestamp": "2026-07-31T15:29:00+00:00",
    "exchange_timestamp": "2026-07-31T15:29:00+00:00",
    "received_at": "2026-07-31T15:30:00+00:00",
}


def _cases() -> list[dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _cases(), ids=lambda case: str(case["name"]))
def test_ibkr_quote_contract_fixtures_normalize_deterministically(case: dict[str, object]) -> None:
    payload = {**BASE_QUOTE, **case["patch"]}

    first = normalize_option_quote(
        payload,
        underlying_price=531.42,
        context=CONTEXT,
        expect_broker_model=True,
    )
    second = normalize_option_quote(
        payload,
        underlying_price=531.42,
        context=CONTEXT,
        expect_broker_model=True,
    )
    flags = {flag.value for flag in first.data_flags}

    assert first == second
    assert first.market_data_mode == case["expected_mode"]
    assert first.mark == case["expected_mark"]
    assert set(case.get("expected_flags_present", [])).issubset(flags)
    assert set(case.get("expected_flags_absent", [])).isdisjoint(flags)
    assert first.contract.con_id == 987654321
    assert first.contract.local_symbol == "SPY   260821C00530000"
    assert first.contract.trading_class == "SPY"
    expected_exchange_time = (
        datetime(2026, 7, 31, 14, 0, tzinfo=timezone.utc)
        if case["name"] == "stale_exchange_timestamp"
        else datetime(2026, 7, 31, 15, 29, tzinfo=timezone.utc)
    )
    assert first.exchange_timestamp == expected_exchange_time
    assert first.received_at == VALUATION_TIME
