from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.config import BACKEND_ROOT, Settings
from app.models.market import DataQualityFlag, MarketDataMode, QuoteSource
from app.services.adapters.base import UnknownContractError
from app.services.adapters.ibkr_contracts import build_contract_id
from app.services.adapters.mock_ibkr import MockIBKRAdapter
from app.services.market_service import MarketService


def test_local_dotenv_does_not_silently_enable_ibkr(monkeypatch) -> None:
    monkeypatch.delenv("MODELLATOR_DATA_MODE", raising=False)
    monkeypatch.chdir(BACKEND_ROOT)

    assert Settings().data_mode == "mock"


def test_independent_adapters_produce_identical_fixed_snapshot() -> None:
    first = MockIBKRAdapter()
    second = MockIBKRAdapter()

    assert first.get_underlying_summary("SPY") == second.get_underlying_summary("SPY")
    assert first.get_option_chain("SPY") == second.get_option_chain("SPY")


def test_mock_payloads_are_explicitly_synthetic_not_delayed_broker_data() -> None:
    adapter = MockIBKRAdapter()
    service = MarketService(adapter, default_rate=0.0425, default_dividend_yield=0)

    search = service.search_underlyings("SPY")
    summary = service.get_underlying_summary("SPY")
    chain = service.get_chain("SPY")

    assert search[0]["market_data_mode"] == MarketDataMode.MOCK
    assert summary.market_data_mode == MarketDataMode.MOCK
    assert summary.is_delayed is False
    assert chain.market_data_mode == MarketDataMode.MOCK
    assert len(chain.expirations) == 5
    assert all(quote.quote_source == QuoteSource.MOCK for quote in chain.calls + chain.puts)
    assert all(quote.market_data_mode == MarketDataMode.MOCK for quote in chain.calls + chain.puts)
    assert all(not quote.is_delayed for quote in chain.calls + chain.puts)


def test_fresh_option_lookup_parses_hyphenated_expiration_without_chain_cache() -> None:
    adapter = MockIBKRAdapter()
    expiration = adapter._expirations()[0]
    strike = adapter._strikes(adapter.underlyings["SPY"].spot)[8]
    contract_id = build_contract_id("SPY", expiration, strike, "C")

    quote = adapter.get_option_quote(contract_id)

    assert quote["contract_id"] == contract_id
    assert quote["expiration"] == expiration.isoformat()


def test_fresh_option_lookup_rejects_unknown_mock_contract() -> None:
    adapter = MockIBKRAdapter()
    expiration = adapter._expirations()[0]

    with pytest.raises(UnknownContractError, match="Unknown mock option contract"):
        adapter.get_option_quote(build_contract_id("SPY", expiration, 123.45, "C"))


def test_mock_chain_contains_deterministic_quality_state_fixtures() -> None:
    valuation_datetime = datetime(2026, 7, 31, 15, 30, tzinfo=timezone.utc)
    adapter = MockIBKRAdapter(valuation_datetime=valuation_datetime)
    service = MarketService(
        adapter,
        default_rate=0.0425,
        default_dividend_yield=0,
        valuation_datetime=valuation_datetime,
    )

    chain = service.get_chain("SPY")
    flags = [set(quote.data_flags) for quote in chain.calls + chain.puts]

    assert any(DataQualityFlag.MISSING_BID in item for item in flags)
    assert any(DataQualityFlag.MARKET_DATA_UNAVAILABLE in item for item in flags)
    assert any(DataQualityFlag.STALE in item for item in flags)
    assert any(DataQualityFlag.CROSSED_MARKET in item for item in flags)
    assert any(DataQualityFlag.WIDE_SPREAD in item for item in flags)
