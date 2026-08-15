from __future__ import annotations

import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import app.services.adapters.ibkr as ibkr_module
from app.services.adapters.base import AdapterUnavailableError
from app.services.adapters.ibkr import IBKRAdapter
from app.services.adapters.ibkr_compat import IBAPICompatibility

TIMESTAMP = datetime(2026, 3, 26, 18, 0, tzinfo=timezone.utc).isoformat()


@pytest.fixture(autouse=True)
def _compatible_official_client(monkeypatch: pytest.MonkeyPatch) -> None:
    compatibility = IBAPICompatibility(
        available=True,
        compatible=True,
        package_version="10.45.1",
        reason_code="compatible",
        detail="test fixture",
    )
    monkeypatch.setattr(ibkr_module, "require_compatible_ibapi", lambda: compatibility)


class _FakeRuntime:
    def __init__(self) -> None:
        self.option_requests: list[tuple[str, str, bool]] = []
        self.batch_requests: list[list[str]] = []
        self.qualify_calls = 0
        self.option_param_calls = 0

    def qualify_underlying(self, symbol: str) -> dict[str, object]:
        self.qualify_calls += 1
        return {
            "symbol": symbol.upper(),
            "long_name": "SPDR S&P 500 ETF",
            "primary_exchange": "ARCA",
            "exchange": "SMART",
            "currency": "USD",
            "con_id": 756733,
        }

    def option_chain_params(self, symbol: str, underlying_conid: int) -> list[dict[str, object]]:
        self.option_param_calls += 1
        assert symbol == "SPY"
        assert underlying_conid == 756733
        return [
            {
                "exchange": "SMART",
                "trading_class": "SPY",
                "multiplier": "100",
                "expirations": ["20260417"],
                "strikes": [530.0],
            }
        ]

    def quote_contract(
        self,
        contract: object,
        generic_tick_list: str = "",
        wait_seconds: float = 1.5,
        allow_partial: bool = False,
    ) -> dict[str, object]:
        if getattr(contract, "secType", "") == "STK":
            return {
                "last": 530.0,
                "close": 528.5,
                "timestamp": TIMESTAMP,
                "market_data_mode": "delayed",
                "is_delayed": True,
            }

        right = getattr(contract, "right", "")
        self.option_requests.append((right, generic_tick_list, allow_partial))
        if right == "C":
            return {
                "timestamp": TIMESTAMP,
                "market_data_mode": "delayed",
                "is_delayed": True,
                "market_data_unavailable": True,
                "subscription_missing": True,
            }

        return {
            "bid": 4.9,
            "ask": 5.1,
            "last": 5.0,
            "timestamp": TIMESTAMP,
            "market_data_mode": "delayed",
            "is_delayed": True,
            "market_data_unavailable": False,
            "subscription_missing": False,
        }

    def quote_contracts(
        self,
        contracts: list[tuple[str, object]],
        generic_tick_list: str = "",
        wait_seconds: float = 1.5,
        allow_partial: bool = False,
    ) -> dict[str, dict[str, object]]:
        self.batch_requests.append([contract_id for contract_id, _ in contracts])
        payloads: dict[str, dict[str, object]] = {}
        for contract_id, contract in contracts:
            payloads[contract_id] = self.quote_contract(
                contract,
                generic_tick_list=generic_tick_list,
                wait_seconds=wait_seconds,
                allow_partial=allow_partial,
            )
        return payloads


def test_adapter_returns_chain_when_some_option_quotes_are_permission_limited(monkeypatch) -> None:
    adapter = IBKRAdapter("127.0.0.1", 7497, 9001, use_delayed=True)
    runtime = _FakeRuntime()
    monkeypatch.setattr(adapter, "_runtime_instance", lambda: runtime)
    monkeypatch.setattr(
        ibkr_module,
        "build_underlying_contract",
        lambda qualified: SimpleNamespace(secType="STK", symbol=qualified["symbol"]),
    )
    monkeypatch.setattr(
        ibkr_module,
        "build_option_contract",
        lambda **kwargs: SimpleNamespace(
            secType="OPT",
            symbol=kwargs["symbol"],
            right=kwargs["right"],
            strike=kwargs["strike"],
            conId=None,
            localSymbol=None,
        ),
    )

    chain = adapter.get_option_chain("SPY", "2026-04-17")

    assert chain["selected_expiration"] == "2026-04-17"
    assert len(chain["options"]) == 2
    call = next(item for item in chain["options"] if item["right"] == "call")
    put = next(item for item in chain["options"] if item["right"] == "put")

    assert call["market_data_unavailable"] is True
    assert call["subscription_missing"] is True
    assert call.get("bid") is None
    assert put["market_data_unavailable"] is False
    assert put["subscription_missing"] is False
    assert put["bid"] == 4.9
    assert all(generic_tick_list == "" for _, generic_tick_list, _ in runtime.option_requests)
    assert all(allow_partial is True for _, _, allow_partial in runtime.option_requests)


def test_adapter_only_requests_optional_option_stats_when_enabled(monkeypatch) -> None:
    adapter = IBKRAdapter(
        "127.0.0.1",
        7497,
        9001,
        use_delayed=True,
        include_optional_option_stats=True,
    )
    runtime = _FakeRuntime()
    monkeypatch.setattr(adapter, "_runtime_instance", lambda: runtime)
    monkeypatch.setattr(
        ibkr_module,
        "build_underlying_contract",
        lambda qualified: SimpleNamespace(secType="STK", symbol=qualified["symbol"]),
    )
    monkeypatch.setattr(
        ibkr_module,
        "build_option_contract",
        lambda **kwargs: SimpleNamespace(
            secType="OPT",
            symbol=kwargs["symbol"],
            right=kwargs["right"],
            strike=kwargs["strike"],
            conId=None,
            localSymbol=None,
        ),
    )

    adapter.get_option_chain("SPY", "2026-04-17")

    assert runtime.option_requests
    assert all(generic_tick_list == "100,101" for _, generic_tick_list, _ in runtime.option_requests)


def test_adapter_reuses_cached_qualified_contracts_and_option_quotes(monkeypatch) -> None:
    adapter = IBKRAdapter("127.0.0.1", 7497, 9001, use_delayed=True)
    runtime = _FakeRuntime()
    monkeypatch.setattr(adapter, "_runtime_instance", lambda: runtime)
    monkeypatch.setattr(
        ibkr_module,
        "build_underlying_contract",
        lambda qualified: SimpleNamespace(secType="STK", symbol=qualified["symbol"]),
    )
    monkeypatch.setattr(
        ibkr_module,
        "build_option_contract",
        lambda **kwargs: SimpleNamespace(
            secType="OPT",
            symbol=kwargs["symbol"],
            right=kwargs["right"],
            strike=kwargs["strike"],
            conId=None,
            localSymbol=None,
        ),
    )

    first_chain = adapter.get_option_chain("SPY", "2026-04-17")
    second_chain = adapter.get_option_chain("SPY", "2026-04-17")
    single_quote = adapter.get_option_quote(first_chain["options"][0]["contract_id"])

    assert len(first_chain["options"]) == len(second_chain["options"]) == 2
    assert runtime.qualify_calls == 1
    assert runtime.option_param_calls == 1
    assert len(runtime.batch_requests) == 1
    assert runtime.option_requests
    assert single_quote["contract_id"] == first_chain["options"][0]["contract_id"]


def test_adapter_summary_then_chain_reuses_single_underlying_qualification(monkeypatch) -> None:
    adapter = IBKRAdapter("127.0.0.1", 7497, 9001, use_delayed=True)
    runtime = _FakeRuntime()
    monkeypatch.setattr(adapter, "_runtime_instance", lambda: runtime)
    monkeypatch.setattr(
        ibkr_module,
        "build_underlying_contract",
        lambda qualified: SimpleNamespace(secType="STK", symbol=qualified["symbol"]),
    )
    monkeypatch.setattr(
        ibkr_module,
        "build_option_contract",
        lambda **kwargs: SimpleNamespace(
            secType="OPT",
            symbol=kwargs["symbol"],
            right=kwargs["right"],
            strike=kwargs["strike"],
            conId=None,
            localSymbol=None,
        ),
    )

    summary = adapter.get_underlying_summary("SPY")
    chain = adapter.get_option_chain("SPY", "2026-04-17")

    assert summary["symbol"] == "SPY"
    assert chain["symbol"] == "SPY"
    assert runtime.qualify_calls == 1
    assert runtime.option_param_calls == 1
    assert len(runtime.batch_requests) == 1


def test_adapter_summary_and_chain_survive_subscription_limited_delayed_underlying_quotes(
    monkeypatch,
) -> None:
    class PartialUnderlyingRuntime(_FakeRuntime):
        def qualify_underlying(self, symbol: str) -> dict[str, object]:
            self.qualify_calls += 1
            return {
                "symbol": symbol.upper(),
                "long_name": "Virgin Galactic Holdings",
                "primary_exchange": "NYSE",
                "exchange": "SMART",
                "currency": "USD",
                "con_id": 392610781,
            }

        def option_chain_params(self, symbol: str, underlying_conid: int) -> list[dict[str, object]]:
            self.option_param_calls += 1
            assert symbol == "SPCE"
            assert underlying_conid == 392610781
            return [
                {
                    "exchange": "SMART",
                    "trading_class": "SPCE",
                    "multiplier": "100",
                    "expirations": ["20260417"],
                    "strikes": [4.0],
                }
            ]

        def quote_contract(
            self,
            contract: object,
            generic_tick_list: str = "",
            wait_seconds: float = 1.5,
            allow_partial: bool = False,
        ) -> dict[str, object]:
            if getattr(contract, "secType", "") == "STK":
                return {
                    "last": 4.25,
                    "timestamp": TIMESTAMP,
                    "market_data_mode": "delayed",
                    "is_delayed": True,
                    "market_data_unavailable": False,
                    "subscription_missing": True,
                }
            return super().quote_contract(
                contract,
                generic_tick_list=generic_tick_list,
                wait_seconds=wait_seconds,
                allow_partial=allow_partial,
            )

    adapter = IBKRAdapter("127.0.0.1", 7497, 9001, use_delayed=True)
    runtime = PartialUnderlyingRuntime()
    monkeypatch.setattr(adapter, "_runtime_instance", lambda: runtime)
    monkeypatch.setattr(
        ibkr_module,
        "build_underlying_contract",
        lambda qualified: SimpleNamespace(secType="STK", symbol=qualified["symbol"]),
    )
    monkeypatch.setattr(
        ibkr_module,
        "build_option_contract",
        lambda **kwargs: SimpleNamespace(
            secType="OPT",
            symbol=kwargs["symbol"],
            right=kwargs["right"],
            strike=kwargs["strike"],
            conId=None,
            localSymbol=None,
        ),
    )

    summary = adapter.get_underlying_summary("SPCE")
    chain = adapter.get_option_chain("SPCE", "2026-04-17")

    assert summary["spot"] == 4.25
    assert summary["subscription_missing"] is True
    assert summary["market_data_unavailable"] is False
    assert chain["underlying"]["spot"] == 4.25
    assert chain["underlying"]["subscription_missing"] is True
    assert len(chain["options"]) == 2


@pytest.mark.parametrize(
    ("quote", "expected_spot"),
    [
        (
            {
                "bid": 529.8,
                "ask": 530.2,
                "last": 530.0,
                "market_data_mode": "delayed_frozen",
                "is_delayed": True,
            },
            530.0,
        ),
        (
            {
                "bid": None,
                "ask": None,
                "last": 529.9,
                "market_data_mode": "delayed_frozen",
                "is_delayed": True,
            },
            529.9,
        ),
    ],
)
def test_adapter_accepts_delayed_frozen_reference_quotes(
    monkeypatch,
    quote: dict[str, object],
    expected_spot: float,
) -> None:
    class ReferenceRuntime(_FakeRuntime):
        def quote_contract(
            self,
            contract: object,
            generic_tick_list: str = "",
            wait_seconds: float = 1.5,
            allow_partial: bool = False,
        ) -> dict[str, object]:
            return {"timestamp": TIMESTAMP, **quote}

    adapter = IBKRAdapter("127.0.0.1", 7497, 9001, use_delayed=True)
    monkeypatch.setattr(adapter, "_runtime_instance", lambda: ReferenceRuntime())
    monkeypatch.setattr(
        ibkr_module,
        "build_underlying_contract",
        lambda qualified: SimpleNamespace(secType="STK", symbol=qualified["symbol"]),
    )

    summary = adapter.get_underlying_summary("SPY")

    assert summary["spot"] == expected_spot
    assert summary["market_data_mode"] == "delayed_frozen"
    assert summary["is_delayed"] is True


@pytest.mark.parametrize(
    "quote",
    [
        {
            "bid": 530.4,
            "ask": 530.1,
            "last": 530.2,
            "market_data_mode": "delayed_frozen",
            "is_delayed": True,
        },
        {
            "market_data_mode": "delayed_frozen",
            "is_delayed": True,
            "market_data_unavailable": True,
        },
        {
            "bid": 530.0,
            "ask": 530.2,
            "market_data_mode": "unconfirmed",
            "is_delayed": False,
            "market_data_unavailable": True,
        },
        {
            "bid": 530.0,
            "ask": 530.2,
            "last": 530.1,
            "market_data_mode": "delayed_frozen",
            "is_delayed": True,
            "market_data_unavailable": True,
        },
    ],
)
def test_adapter_rejects_crossed_unusable_or_unconfirmed_reference_quotes(
    monkeypatch,
    quote: dict[str, object],
) -> None:
    class InvalidRuntime(_FakeRuntime):
        def quote_contract(
            self,
            contract: object,
            generic_tick_list: str = "",
            wait_seconds: float = 1.5,
            allow_partial: bool = False,
        ) -> dict[str, object]:
            return {"timestamp": TIMESTAMP, **quote}

    adapter = IBKRAdapter("127.0.0.1", 7497, 9001, use_delayed=True)
    monkeypatch.setattr(adapter, "_runtime_instance", lambda: InvalidRuntime())
    monkeypatch.setattr(
        ibkr_module,
        "build_underlying_contract",
        lambda qualified: SimpleNamespace(secType="STK", symbol=qualified["symbol"]),
    )

    with pytest.raises(AdapterUnavailableError):
        adapter.get_underlying_summary("SPY")


def test_adapter_serializes_concurrent_underlying_qualification(monkeypatch) -> None:
    class ConcurrentRuntime(_FakeRuntime):
        def __init__(self) -> None:
            super().__init__()
            self.qualify_started = threading.Event()
            self.release_qualify = threading.Event()

        def qualify_underlying(self, symbol: str) -> dict[str, object]:
            self.qualify_calls += 1
            self.qualify_started.set()
            self.release_qualify.wait(timeout=1.0)
            return {
                "symbol": symbol.upper(),
                "long_name": "SPDR S&P 500 ETF",
                "primary_exchange": "ARCA",
                "exchange": "SMART",
                "currency": "USD",
                "con_id": 756733,
            }

    adapter = IBKRAdapter("127.0.0.1", 7497, 9001, use_delayed=True)
    runtime = ConcurrentRuntime()
    monkeypatch.setattr(adapter, "_runtime_instance", lambda: runtime)
    monkeypatch.setattr(
        ibkr_module,
        "build_underlying_contract",
        lambda qualified: SimpleNamespace(secType="STK", symbol=qualified["symbol"]),
    )
    monkeypatch.setattr(
        ibkr_module,
        "build_option_contract",
        lambda **kwargs: SimpleNamespace(
            secType="OPT",
            symbol=kwargs["symbol"],
            right=kwargs["right"],
            strike=kwargs["strike"],
            conId=None,
            localSymbol=None,
        ),
    )

    errors: list[Exception] = []

    def load_summary() -> None:
        try:
            adapter.get_underlying_summary("SPY")
        except Exception as error:  # pragma: no cover - assertion aid
            errors.append(error)

    def load_chain() -> None:
        try:
            adapter.get_option_chain("SPY", "2026-04-17")
        except Exception as error:  # pragma: no cover - assertion aid
            errors.append(error)

    summary_thread = threading.Thread(target=load_summary)
    chain_thread = threading.Thread(target=load_chain)
    summary_thread.start()
    runtime.qualify_started.wait(timeout=1.0)
    chain_thread.start()
    runtime.release_qualify.set()
    summary_thread.join(timeout=1.0)
    chain_thread.join(timeout=1.0)

    assert not errors
    assert runtime.qualify_calls == 1


def test_adapter_initializes_runtime_once_across_threads(monkeypatch) -> None:
    created: list[object] = []

    class FakeRuntime:
        def __init__(self, **kwargs: object) -> None:
            created.append(self)

    monkeypatch.setattr(ibkr_module, "IBKRRuntime", FakeRuntime)
    adapter = IBKRAdapter("127.0.0.1", 7497, 9001)
    runtimes: list[object] = []
    threads = [
        threading.Thread(target=lambda: runtimes.append(adapter._runtime_instance())) for _ in range(8)
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(created) == 1
    assert len({id(runtime) for runtime in runtimes}) == 1
