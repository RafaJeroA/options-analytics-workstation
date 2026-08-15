from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.adapters.ibkr_runtime as runtime_module
from app.services.adapters.base import AdapterUnavailableError, AmbiguousContractError, UnknownSymbolError
from app.services.adapters.ibkr_compat import IBAPICompatibility
from app.services.adapters.ibkr_runtime import IBKRRuntime


class _FakeContract:
    pass


def _make_runtime(monkeypatch: pytest.MonkeyPatch) -> IBKRRuntime:
    compatibility = IBAPICompatibility(
        available=True,
        compatible=True,
        package_version="10.45.1",
        reason_code="compatible",
        detail="test fixture",
    )
    monkeypatch.setattr(runtime_module, "IBAPI_AVAILABLE", True)
    monkeypatch.setattr(runtime_module, "Contract", _FakeContract)
    monkeypatch.setattr(runtime_module, "require_compatible_ibapi", lambda: compatibility)
    runtime = IBKRRuntime("127.0.0.1", 4002, 31, use_delayed=True)
    monkeypatch.setattr(runtime, "ensure_connected", lambda timeout=8.0: None)
    return runtime


def _stock_contract_details(
    *,
    con_id: int,
    symbol: str = "SPY",
    exchange: str = "SMART",
    primary_exchange: str = "ARCA",
    currency: str = "USD",
) -> SimpleNamespace:
    return SimpleNamespace(
        contract=SimpleNamespace(
            conId=con_id,
            symbol=symbol,
            secType="STK",
            exchange=exchange,
            primaryExchange=primary_exchange,
            currency=currency,
            localSymbol=symbol,
            tradingClass=symbol,
            lastTradeDateOrContractMonth="",
            strike=None,
            right="",
            multiplier="",
        ),
        longName="SPDR S&P 500 ETF",
        marketName=symbol,
        minTick=0.01,
        validExchanges="SMART,ARCA",
        underConId=con_id,
        contractMonth="",
        timeZoneId="US/Eastern",
        tradingHours="",
        liquidHours="",
        stockType="ETF",
    )


def test_request_contract_details_completes_after_contract_callback_without_end(monkeypatch) -> None:
    runtime = _make_runtime(monkeypatch)

    class FakeApp:
        def reqContractDetails(self, req_id: int, contract: object) -> None:  # noqa: N802
            runtime._handle_contract_details(
                req_id,
                _stock_contract_details(con_id=756733),
            )

    runtime._next_request_id = 101
    runtime._app = FakeApp()

    details = runtime._request_contract_details(SimpleNamespace(symbol="SPY"), timeout=0.25)

    assert details == [
        {
            "con_id": 756733,
            "symbol": "SPY",
            "sec_type": "STK",
            "exchange": "SMART",
            "primary_exchange": "ARCA",
            "currency": "USD",
            "local_symbol": "SPY",
            "trading_class": "SPY",
            "last_trade_date_or_contract_month": "",
            "strike": None,
            "right": "",
            "multiplier": "",
            "long_name": "SPDR S&P 500 ETF",
            "market_name": "SPY",
            "min_tick": 0.01,
            "valid_exchanges": "SMART,ARCA",
            "under_con_id": 756733,
            "contract_month": "",
            "time_zone_id": "US/Eastern",
            "trading_hours": "",
            "liquid_hours": "",
            "stock_type": "ETF",
        }
    ]


def test_qualify_underlying_succeeds_when_contract_details_end_is_missing(monkeypatch) -> None:
    runtime = _make_runtime(monkeypatch)

    class FakeApp:
        def reqContractDetails(self, req_id: int, contract: object) -> None:  # noqa: N802
            runtime._handle_contract_details(
                req_id,
                _stock_contract_details(
                    con_id=1001,
                    exchange="NYSE",
                    primary_exchange="NYSE",
                ),
            )
            runtime._handle_contract_details(
                req_id,
                _stock_contract_details(con_id=756733),
            )

    runtime._next_request_id = 111
    runtime._app = FakeApp()

    qualified = runtime.qualify_underlying("SPY", timeout=0.25)

    assert qualified["con_id"] == 756733
    assert qualified["exchange"] == "SMART"
    assert qualified["primary_exchange"] == "ARCA"


def test_qualify_underlying_times_out_when_contract_details_never_arrive(monkeypatch) -> None:
    runtime = _make_runtime(monkeypatch)

    class FakeApp:
        def reqContractDetails(self, req_id: int, contract: object) -> None:  # noqa: N802
            return None

    runtime._next_request_id = 121
    runtime._app = FakeApp()

    with pytest.raises(AdapterUnavailableError, match="Timed out waiting for contract details"):
        runtime.qualify_underlying("SPY", timeout=0.05)


def test_qualify_underlying_rejects_ambiguous_equal_rank_contracts(monkeypatch) -> None:
    runtime = _make_runtime(monkeypatch)
    monkeypatch.setattr(
        runtime,
        "_request_contract_details",
        lambda contract, timeout: [
            runtime_module._contract_details_to_dict(_stock_contract_details(con_id=1001)),
            runtime_module._contract_details_to_dict(_stock_contract_details(con_id=1002)),
        ],
    )

    with pytest.raises(AmbiguousContractError, match="multiple equally plausible"):
        runtime.qualify_underlying("SPY")


def test_qualify_underlying_reports_genuine_unknown_symbol(monkeypatch) -> None:
    runtime = _make_runtime(monkeypatch)
    monkeypatch.setattr(runtime, "_request_contract_details", lambda contract, timeout: [])

    with pytest.raises(UnknownSymbolError, match="Unknown IBKR symbol"):
        runtime.qualify_underlying("NOPE")
