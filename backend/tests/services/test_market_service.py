from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.sqlite import SQLiteStore
from app.models.market import ChainSnapshot
from app.services.adapters.mock_ibkr import MockIBKRAdapter
from app.services.market_service import MarketService


def _chain_payload(
    selected_expiration: str,
    call_ivs: list[float | None],
    put_ivs: list[float | None] | None = None,
) -> ChainSnapshot:
    timestamp = datetime(2026, 3, 26, 18, 0, tzinfo=timezone.utc).isoformat()
    options: list[dict[str, object]] = []
    for offset, implied_vol in enumerate(call_ivs):
        strike = 500 + offset * 5
        options.append(
            {
                "contract": {
                    "contract_id": f"SPY-{selected_expiration}-{strike:.2f}-C",
                    "symbol": "SPY",
                    "exchange": "SMART",
                    "currency": "USD",
                    "expiration": selected_expiration,
                    "strike": strike,
                    "right": "call",
                    "multiplier": 100,
                },
                "bid": 5.0,
                "ask": 5.2,
                "last": 5.1,
                "mark": 5.1,
                "model_price": 5.05,
                "quote_source": "broker",
                "model_source": "broker_model" if implied_vol is not None else "broker",
                "implied_vol": implied_vol,
                "broker_implied_vol": implied_vol,
                "updated_at": timestamp,
                "market_data_mode": "delayed",
                "is_delayed": True,
            }
        )
    puts: list[dict[str, object]] = []
    for offset, implied_vol in enumerate(put_ivs or []):
        strike = 500 + offset * 5
        puts.append(
            {
                "contract": {
                    "contract_id": f"SPY-{selected_expiration}-{strike:.2f}-P",
                    "symbol": "SPY",
                    "exchange": "SMART",
                    "currency": "USD",
                    "expiration": selected_expiration,
                    "strike": strike,
                    "right": "put",
                    "multiplier": 100,
                },
                "bid": 5.0,
                "ask": 5.2,
                "last": 5.1,
                "mark": 5.1,
                "model_price": 5.05,
                "quote_source": "broker",
                "model_source": "broker_model" if implied_vol is not None else "broker",
                "implied_vol": implied_vol,
                "broker_implied_vol": implied_vol,
                "updated_at": timestamp,
                "market_data_mode": "delayed",
                "is_delayed": True,
            }
        )
    return ChainSnapshot.model_validate(
        {
            "symbol": "SPY",
            "underlying": {
                "symbol": "SPY",
                "description": "SPDR S&P 500 ETF",
                "exchange": "ARCA",
                "currency": "USD",
                "spot": 500,
                "previous_close": 498,
                "change": 2,
                "change_percent": 0.4,
                "timestamp": timestamp,
                "market_data_mode": "delayed",
                "is_delayed": True,
            },
            "expirations": ["2026-04-17", "2026-05-15", "2026-06-19"],
            "selected_expiration": selected_expiration,
            "calls": options,
            "puts": puts,
            "updated_at": timestamp,
            "market_data_mode": "delayed",
        }
    )


def test_term_structure_preserves_unavailable_expiries(monkeypatch) -> None:
    service = MarketService(
        MockIBKRAdapter(default_rate=0.0425),
        default_rate=0.0425,
        default_dividend_yield=0.0,
    )

    chains = {
        None: _chain_payload("2026-04-17", [0.22]),
        "2026-04-17": _chain_payload("2026-04-17", [0.22]),
        "2026-05-15": _chain_payload("2026-05-15", [None]),
        "2026-06-19": _chain_payload("2026-06-19", [0.27]),
    }
    monkeypatch.setattr(service, "get_chain", lambda symbol, expiration=None: chains[expiration])

    structure = service.get_term_structure("SPY")

    assert [point.expiration.isoformat() for point in structure] == [
        "2026-04-17",
        "2026-05-15",
        "2026-06-19",
    ]
    assert [point.status.value for point in structure] == ["available", "unavailable", "available"]
    assert structure[0].atm_iv == 0.22
    assert structure[1].atm_iv is None
    assert structure[2].atm_iv == 0.27


def test_term_structure_uses_nearest_strike_call_put_mean(monkeypatch) -> None:
    service = MarketService(
        MockIBKRAdapter(default_rate=0.0425),
        default_rate=0.0425,
        default_dividend_yield=0.0,
    )
    chain = _chain_payload("2026-04-17", [0.22, 0.30], [0.24, 0.32])
    monkeypatch.setattr(service, "get_chain", lambda symbol, expiration=None: chain)

    structure = service.get_term_structure("SPY")

    assert [point.expiration.isoformat() for point in structure] == [
        "2026-04-17",
        "2026-05-15",
        "2026-06-19",
    ]
    assert structure[0].atm_strike == 500
    assert structure[0].atm_iv == pytest.approx(0.23)
    assert structure[0].sample_size == 2
    assert structure[0].method == "nearest-strike call/put mean"


def test_term_structure_uses_put_iv_when_calls_are_unusable(monkeypatch) -> None:
    service = MarketService(
        MockIBKRAdapter(default_rate=0.0425),
        default_rate=0.0425,
        default_dividend_yield=0.0,
    )

    timestamp = datetime(2026, 3, 26, 18, 0, tzinfo=timezone.utc).isoformat()
    chains = {
        None: ChainSnapshot.model_validate(
            {
                "symbol": "SPY",
                "underlying": {
                    "symbol": "SPY",
                    "description": "SPDR S&P 500 ETF",
                    "exchange": "ARCA",
                    "currency": "USD",
                    "spot": 500,
                    "previous_close": 498,
                    "change": 2,
                    "change_percent": 0.4,
                    "timestamp": timestamp,
                    "market_data_mode": "delayed",
                    "is_delayed": True,
                },
                "expirations": ["2026-04-17", "2026-05-15"],
                "selected_expiration": "2026-04-17",
                "calls": [],
                "puts": [],
                "updated_at": timestamp,
                "market_data_mode": "delayed",
            }
        ),
        "2026-04-17": ChainSnapshot.model_validate(
            {
                "symbol": "SPY",
                "underlying": {
                    "symbol": "SPY",
                    "description": "SPDR S&P 500 ETF",
                    "exchange": "ARCA",
                    "currency": "USD",
                    "spot": 500,
                    "previous_close": 498,
                    "change": 2,
                    "change_percent": 0.4,
                    "timestamp": timestamp,
                    "market_data_mode": "delayed",
                    "is_delayed": True,
                },
                "expirations": ["2026-04-17", "2026-05-15"],
                "selected_expiration": "2026-04-17",
                "calls": [
                    {
                        "contract": {
                            "contract_id": "SPY-2026-04-17-500.00-C",
                            "symbol": "SPY",
                            "exchange": "SMART",
                            "currency": "USD",
                            "expiration": "2026-04-17",
                            "strike": 500,
                            "right": "call",
                            "multiplier": 100,
                        },
                        "bid": 5.0,
                        "ask": 5.2,
                        "last": 5.1,
                        "mark": 5.1,
                        "implied_vol": None,
                        "updated_at": timestamp,
                        "market_data_mode": "delayed",
                        "is_delayed": True,
                    }
                ],
                "puts": [
                    {
                        "contract": {
                            "contract_id": "SPY-2026-04-17-500.00-P",
                            "symbol": "SPY",
                            "exchange": "SMART",
                            "currency": "USD",
                            "expiration": "2026-04-17",
                            "strike": 500,
                            "right": "put",
                            "multiplier": 100,
                        },
                        "bid": 5.3,
                        "ask": 5.5,
                        "last": 5.4,
                        "mark": 5.4,
                        "implied_vol": 0.24,
                        "updated_at": timestamp,
                        "market_data_mode": "delayed",
                        "is_delayed": True,
                    }
                ],
                "updated_at": timestamp,
                "market_data_mode": "delayed",
            }
        ),
        "2026-05-15": _chain_payload("2026-05-15", [0.27]),
    }
    monkeypatch.setattr(service, "get_chain", lambda symbol, expiration=None: chains[expiration])

    structure = service.get_term_structure("SPY")

    assert [point.expiration.isoformat() for point in structure] == ["2026-04-17", "2026-05-15"]
    assert structure[0].atm_iv == 0.24
    assert structure[0].sample_size == 1


def test_term_structure_marks_missing_expiry_chain_lookups_unavailable(monkeypatch) -> None:
    service = MarketService(
        MockIBKRAdapter(default_rate=0.0425),
        default_rate=0.0425,
        default_dividend_yield=0.0,
    )

    chains = {
        None: _chain_payload("2026-04-17", [0.22]),
        "2026-04-17": _chain_payload("2026-04-17", [0.22]),
    }
    monkeypatch.setattr(service, "get_chain", lambda symbol, expiration=None: chains[expiration])

    structure = service.get_term_structure("SPY")

    assert [point.expiration.isoformat() for point in structure] == [
        "2026-04-17",
        "2026-05-15",
        "2026-06-19",
    ]
    assert [point.status.value for point in structure] == ["available", "unavailable", "unavailable"]


def test_market_service_mock_mode_reads_persisted_defaults_and_returns_data(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "modellator.db")
    store.set_setting(
        "user_settings",
        {
            "default_rate": 0.015,
            "default_dividend_yield": 0.02,
        },
    )

    service = MarketService(
        MockIBKRAdapter(default_rate=0.0425),
        default_rate=0.0425,
        default_dividend_yield=0.0,
        store=store,
    )

    context = service._normalization_context()
    summary = service.get_underlying_summary("SPY")
    chain = service.get_chain("SPY")
    quote = service.get_option_quote(chain.calls[0].contract.contract_id)

    assert context.risk_free_rate == 0.015
    assert context.dividend_yield == 0.02
    assert summary.symbol == "SPY"
    assert summary.market_data_mode.value == "mock"
    assert len(chain.calls) > 0
    assert len(chain.puts) > 0
    assert quote.contract.symbol == "SPY"


def test_market_service_preserves_subscription_limited_underlying_flags() -> None:
    timestamp = datetime(2026, 3, 26, 18, 0, tzinfo=timezone.utc).isoformat()

    class StubAdapter:
        mode = "ibkr"

        def status(self) -> str:
            return "ready"

        def search_underlyings(self, query: str) -> list[dict[str, object]]:
            return []

        def get_underlying_summary(self, symbol: str) -> dict[str, object]:
            return {
                "symbol": "SPCE",
                "description": "Virgin Galactic Holdings",
                "exchange": "NYSE",
                "currency": "USD",
                "spot": 4.25,
                "previous_close": 4.1,
                "change": 0.15,
                "change_percent": 3.66,
                "timestamp": timestamp,
                "market_data_mode": "delayed",
                "is_delayed": True,
                "market_data_unavailable": False,
                "subscription_missing": True,
            }

        def get_option_chain(self, symbol: str, expiration: str | None = None) -> dict[str, object]:
            raise AssertionError("not used in this test")

        def get_option_quote(self, contract_id: str) -> dict[str, object]:
            raise AssertionError("not used in this test")

    service = MarketService(
        StubAdapter(),
        default_rate=0.0425,
        default_dividend_yield=0.0,
    )

    summary = service.get_underlying_summary("SPCE")

    assert summary.symbol == "SPCE"
    assert summary.subscription_missing is True
    assert summary.market_data_unavailable is False
    assert summary.is_delayed is True


def test_market_service_preserves_permission_limited_option_flags() -> None:
    timestamp = datetime(2026, 3, 26, 18, 0, tzinfo=timezone.utc).isoformat()

    class StubAdapter:
        mode = "ibkr"

        def status(self) -> str:
            return "ready"

        def search_underlyings(self, query: str) -> list[dict[str, object]]:
            return []

        def get_underlying_summary(self, symbol: str) -> dict[str, object]:
            raise AssertionError("not used in this test")

        def get_option_chain(self, symbol: str, expiration: str | None = None) -> dict[str, object]:
            return {
                "symbol": "SPY",
                "underlying": {
                    "symbol": "SPY",
                    "description": "SPDR S&P 500 ETF",
                    "exchange": "ARCA",
                    "currency": "USD",
                    "spot": 530,
                    "previous_close": 528.5,
                    "change": 1.5,
                    "change_percent": 0.28,
                    "timestamp": timestamp,
                    "market_data_mode": "delayed",
                    "is_delayed": True,
                },
                "expirations": ["2026-04-17"],
                "selected_expiration": "2026-04-17",
                "options": [
                    {
                        "contract_id": "SPY-2026-04-17-530.00-C",
                        "symbol": "SPY",
                        "exchange": "SMART",
                        "currency": "USD",
                        "expiration": "2026-04-17",
                        "strike": 530,
                        "right": "call",
                        "multiplier": 100,
                        "timestamp": timestamp,
                        "market_data_mode": "delayed",
                        "is_delayed": True,
                        "market_data_unavailable": True,
                        "subscription_missing": True,
                    },
                    {
                        "contract_id": "SPY-2026-04-17-530.00-P",
                        "symbol": "SPY",
                        "exchange": "SMART",
                        "currency": "USD",
                        "expiration": "2026-04-17",
                        "strike": 530,
                        "right": "put",
                        "multiplier": 100,
                        "bid": 5.0,
                        "ask": 5.2,
                        "last": 5.1,
                        "timestamp": timestamp,
                        "market_data_mode": "delayed",
                        "is_delayed": True,
                    },
                ],
                "updated_at": timestamp,
                "market_data_mode": "delayed",
            }

        def get_option_quote(self, contract_id: str) -> dict[str, object]:
            raise AssertionError("not used in this test")

    service = MarketService(
        StubAdapter(),
        default_rate=0.0425,
        default_dividend_yield=0.0,
    )

    chain = service.get_chain("SPY")
    call = chain.calls[0]
    put = chain.puts[0]

    assert call.market_data_unavailable is True
    assert call.subscription_missing is True
    assert {"market_data_unavailable", "subscription_missing"} <= {flag.value for flag in call.data_flags}
    assert put.market_data_unavailable is False
    assert put.subscription_missing is False


def test_market_service_invalidate_market_caches_forces_chain_reload(tmp_path) -> None:
    timestamp = datetime(2026, 3, 26, 18, 0, tzinfo=timezone.utc).isoformat()
    store = SQLiteStore(tmp_path / "modellator.db")

    class StubAdapter:
        mode = "mock"

        def __init__(self) -> None:
            self.chain_calls = 0

        def status(self) -> str:
            return "healthy"

        def search_underlyings(self, query: str) -> list[dict[str, object]]:
            return []

        def get_underlying_summary(self, symbol: str) -> dict[str, object]:
            return {
                "symbol": "SPY",
                "description": "SPDR S&P 500 ETF",
                "exchange": "ARCA",
                "currency": "USD",
                "spot": 530,
                "previous_close": 528.5,
                "change": 1.5,
                "change_percent": 0.28,
                "timestamp": timestamp,
                "market_data_mode": "delayed",
                "is_delayed": True,
            }

        def get_option_chain(self, symbol: str, expiration: str | None = None) -> dict[str, object]:
            self.chain_calls += 1
            return {
                "symbol": "SPY",
                "underlying": self.get_underlying_summary(symbol),
                "expirations": ["2026-04-17"],
                "selected_expiration": "2026-04-17",
                "options": [
                    {
                        "contract_id": "SPY-2026-04-17-530.00-C",
                        "symbol": "SPY",
                        "exchange": "SMART",
                        "currency": "USD",
                        "expiration": "2026-04-17",
                        "strike": 530,
                        "right": "call",
                        "multiplier": 100,
                        "bid": 5.0,
                        "ask": 5.2,
                        "last": 5.1,
                        "timestamp": timestamp,
                        "market_data_mode": "delayed",
                        "is_delayed": True,
                    }
                ],
                "updated_at": timestamp,
                "market_data_mode": "delayed",
            }

        def get_option_quote(self, contract_id: str) -> dict[str, object]:
            raise AssertionError("not used in this test")

    adapter = StubAdapter()
    service = MarketService(
        adapter,
        default_rate=0.0425,
        default_dividend_yield=0.0,
        store=store,
        chain_cache_ttl_seconds=60.0,
        settings_cache_ttl_seconds=60.0,
    )

    first = service.get_chain("SPY")
    store.set_setting("user_settings", {"default_rate": 0.01})
    second = service.get_chain("SPY")

    assert adapter.chain_calls == 1
    assert second is first

    service.invalidate_market_caches()
    third = service.get_chain("SPY")

    assert adapter.chain_calls == 2
    assert third is not first


def test_market_service_caches_volatility_skew(monkeypatch) -> None:
    service = MarketService(
        MockIBKRAdapter(default_rate=0.0425),
        default_rate=0.0425,
        default_dividend_yield=0.0,
        skew_cache_ttl_seconds=60.0,
    )
    chain_calls = {"count": 0}

    def stub_chain(symbol: str, expiration: str | None = None) -> ChainSnapshot:
        chain_calls["count"] += 1
        return _chain_payload("2026-04-17", [0.22, 0.24])

    monkeypatch.setattr(service, "get_chain", stub_chain)

    first = service.get_volatility_skew("SPY", "2026-04-17")
    second = service.get_volatility_skew("SPY", "2026-04-17")

    assert chain_calls["count"] == 1
    assert first == second


def test_market_service_falls_back_to_current_expiration_when_requested_expiration_is_unavailable(
    monkeypatch,
) -> None:
    service = MarketService(
        MockIBKRAdapter(default_rate=0.0425),
        default_rate=0.0425,
        default_dividend_yield=0.0,
    )
    requested_expirations: list[str | None] = []

    def stub_get_option_chain(symbol: str, expiration: str | None = None):
        requested_expirations.append(expiration)
        if expiration == "2026-01-16":
            from app.services.adapters.base import AdapterUnavailableError

            raise AdapterUnavailableError("Requested expiration 2026-01-16 is not available.")
        return {
            "symbol": "SPY",
            "underlying": {
                "symbol": "SPY",
                "description": "SPDR S&P 500 ETF",
                "exchange": "ARCA",
                "currency": "USD",
                "spot": 500,
                "previous_close": 498,
                "change": 2,
                "change_percent": 0.4,
                "timestamp": datetime(2026, 3, 26, 18, 0, tzinfo=timezone.utc).isoformat(),
                "market_data_mode": "delayed",
                "is_delayed": True,
            },
            "expirations": ["2026-04-17", "2026-05-15"],
            "selected_expiration": "2026-04-17",
            "options": [
                {
                    "contract_id": "SPY-2026-04-17-500.00-C",
                    "symbol": "SPY",
                    "exchange": "SMART",
                    "currency": "USD",
                    "expiration": "2026-04-17",
                    "strike": 500,
                    "right": "call",
                    "multiplier": 100,
                    "bid": 5.0,
                    "ask": 5.2,
                    "last": 5.1,
                    "broker_implied_vol": 0.24,
                    "broker_model_price": 5.05,
                    "broker_greeks": {
                        "delta": 0.5,
                        "gamma": 0.02,
                        "theta": -0.03,
                        "vega": 0.12,
                    },
                    "timestamp": datetime(2026, 3, 26, 18, 0, tzinfo=timezone.utc).isoformat(),
                    "market_data_mode": "delayed",
                    "is_delayed": True,
                }
            ],
            "updated_at": datetime(2026, 3, 26, 18, 0, tzinfo=timezone.utc).isoformat(),
            "market_data_mode": "delayed",
        }

    monkeypatch.setattr(service.adapter, "get_option_chain", stub_get_option_chain)

    chain = service.get_chain("SPY", "2026-01-16")
    skew = service.get_volatility_skew("SPY", "2026-01-16")

    assert requested_expirations[:2] == ["2026-01-16", None]
    assert chain.selected_expiration.isoformat() == "2026-04-17"
    assert skew
    assert all(point.expiration.isoformat() == "2026-04-17" for point in skew)
