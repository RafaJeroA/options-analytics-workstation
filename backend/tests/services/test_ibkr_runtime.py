from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.services.adapters.ibkr_runtime as runtime_module
from app.services.adapters.base import AdapterUnavailableError
from app.services.adapters.ibkr_compat import IBAPICompatibility
from app.services.adapters.ibkr_runtime import (
    IBKRRuntime,
    _ListRequest,
    _MarketDataRequest,
    _RuntimeCallbacks,
)


class TickTypeEnum:
    BID = 1
    ASK = 2
    LAST = 4
    HIGH = 6
    LOW = 7
    VOLUME = 8
    CLOSE = 9
    BID_OPTION_COMPUTATION = 10
    ASK_OPTION_COMPUTATION = 11
    LAST_OPTION_COMPUTATION = 12
    MODEL_OPTION = 13
    OPEN = 14
    OPEN_INTEREST = 22
    OPTION_CALL_OPEN_INTEREST = 27
    OPTION_PUT_OPEN_INTEREST = 28
    OPTION_CALL_VOLUME = 29
    OPTION_PUT_VOLUME = 30
    LAST_TIMESTAMP = 45
    RT_VOLUME = 48
    DELAYED_BID = 66
    DELAYED_ASK = 67
    DELAYED_LAST = 68
    DELAYED_HIGH = 72
    DELAYED_LOW = 73
    DELAYED_VOLUME = 74
    DELAYED_CLOSE = 75
    DELAYED_OPEN = 76
    DELAYED_BID_OPTION = 80
    DELAYED_ASK_OPTION = 81
    DELAYED_LAST_OPTION = 82
    DELAYED_MODEL_OPTION = 83

    _NAMES = {
        value: name for name, value in vars().copy().items() if name.isupper() and isinstance(value, int)
    }

    @classmethod
    def toStr(cls, value: int) -> str:  # noqa: N802 - mirrors the official API
        return cls._NAMES.get(value, f"UNKNOWN_{value}")


@pytest.fixture(autouse=True)
def _compatible_runtime_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    compatibility = IBAPICompatibility(
        available=True,
        compatible=True,
        package_version="10.45.1",
        reason_code="compatible",
        detail="test fixture",
    )
    monkeypatch.setattr(runtime_module, "TickTypeEnum", TickTypeEnum)
    monkeypatch.setattr(runtime_module, "require_compatible_ibapi", lambda: compatibility)


def test_runtime_collects_broker_model_ticks() -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 17, use_delayed=True)
    request = _MarketDataRequest(contract=SimpleNamespace(right="C"))
    runtime._market_data_requests[1] = request

    runtime._handle_market_data_type(1, 3)
    runtime._handle_tick_option_computation(
        req_id=1,
        tick_type=TickTypeEnum.DELAYED_MODEL_OPTION,
        implied_vol=0.24,
        delta=0.52,
        option_price=5.26,
        pv_dividend=0.11,
        gamma=0.04,
        vega=0.18,
        theta=-0.08,
        underlying_price=101.2,
    )

    assert request.payload["market_data_type"] == 3
    assert request.payload["broker_implied_vol"] == 0.24
    assert request.payload["broker_model_price"] == 5.26
    assert request.payload["broker_underlying_price"] == 101.2
    assert request.payload["broker_pv_dividend"] == 0.11
    assert request.payload["broker_greeks"] == {
        "delta": 0.52,
        "gamma": 0.04,
        "theta": -0.08,
        "vega": 0.18,
    }


@pytest.mark.parametrize(
    ("market_data_type", "expected_mode", "expected_delayed"),
    [
        (1, "live", False),
        (2, "frozen", False),
        (3, "delayed", True),
        (4, "delayed_frozen", True),
    ],
)
def test_runtime_preserves_all_ibkr_market_data_modes(
    market_data_type: int,
    expected_mode: str,
    expected_delayed: bool,
) -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 117, use_delayed=True)
    exchange_time = datetime(2026, 7, 31, 15, 29, tzinfo=timezone.utc)
    request = _MarketDataRequest(
        contract=SimpleNamespace(right="C"),
        payload={
            "bid": 5.1,
            "ask": 5.3,
            "market_data_type": market_data_type,
            "last_timestamp": str(int(exchange_time.timestamp())),
        },
    )

    payload = runtime._finalize_market_data_request(request, allow_partial=False)

    assert payload["market_data_mode"] == expected_mode
    assert payload["is_delayed"] is expected_delayed
    assert payload["exchange_timestamp"] == exchange_time.isoformat()
    assert payload["timestamp"] == exchange_time.isoformat()
    assert payload["received_at"] != payload["exchange_timestamp"]


def test_runtime_prefers_model_computation_over_competing_last_tick() -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 118, use_delayed=True)
    request = _MarketDataRequest(contract=SimpleNamespace(right="C"))
    runtime._market_data_requests[9] = request

    runtime._handle_tick_option_computation(
        9, TickTypeEnum.LAST_OPTION_COMPUTATION, 0.8, 0.8, 9.0, 0.0, 0.8, 0.8, -0.8, 101.0
    )
    runtime._handle_tick_option_computation(
        9, TickTypeEnum.DELAYED_MODEL_OPTION, 0.24, 0.52, 5.26, 0.11, 0.04, 0.18, -0.08, 101.2
    )
    runtime._handle_tick_option_computation(
        9, TickTypeEnum.LAST_OPTION_COMPUTATION, 0.9, 0.9, 10.0, 0.0, 0.9, 0.9, -0.9, 102.0
    )

    assert request.payload["broker_implied_vol"] == 0.24
    assert request.payload["broker_model_price"] == 5.26
    assert request.payload["broker_greeks"]["delta"] == 0.52


def test_runtime_reconnects_once_after_initial_connection_failure(monkeypatch) -> None:
    attempts: list[object] = []

    class FakeApp:
        def __init__(self, runtime: IBKRRuntime) -> None:
            self.runtime = runtime
            self.connected = False
            attempts.append(self)

        def connect(self, host: str, port: int, client_id: int) -> None:
            if len(attempts) == 1:
                raise ConnectionError("first attempt failed")
            self.connected = True
            self.runtime._handle_next_valid_id(700)

        def run(self) -> None:
            return None

        def isConnected(self) -> bool:  # noqa: N802
            return self.connected

        def disconnect(self) -> None:
            self.connected = False

        def reqMarketDataType(self, market_data_type: int) -> None:  # noqa: N802
            assert market_data_type == 4

    monkeypatch.setattr(runtime_module, "_RuntimeApp", FakeApp)
    runtime = IBKRRuntime("127.0.0.1", 4002, 119, use_delayed=True)

    runtime.ensure_connected(timeout=0.05, reconnect_attempts=1)

    assert len(attempts) == 2
    assert runtime.lifecycle_status == "connected"
    assert runtime.is_connected()


def test_runtime_bounds_reconnect_failure(monkeypatch) -> None:
    attempts = 0

    class FailingApp:
        def __init__(self, runtime: IBKRRuntime) -> None:
            pass

        def connect(self, host: str, port: int, client_id: int) -> None:
            nonlocal attempts
            attempts += 1
            raise ConnectionError("gateway unavailable")

        def isConnected(self) -> bool:  # noqa: N802
            return False

    monkeypatch.setattr(runtime_module, "_RuntimeApp", FailingApp)
    runtime = IBKRRuntime("127.0.0.1", 4002, 120, use_delayed=True)

    with pytest.raises(AdapterUnavailableError, match="gateway unavailable"):
        runtime.ensure_connected(timeout=0.01, reconnect_attempts=1)

    assert attempts == 2
    assert runtime.lifecycle_status == "failed"


def test_connection_loss_cancels_pending_requests() -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 121, use_delayed=True)
    request = _MarketDataRequest(contract=SimpleNamespace(right="C"))
    runtime._market_data_requests[44] = request

    runtime._handle_error(44, 1100, "Connectivity between IBKR and TWS has been lost")

    assert request.event.is_set()
    assert any("lost" in error.message for error in request.errors)
    assert runtime.lifecycle_status == "failed"


def test_modern_error_callback_preserves_error_time_and_request_context() -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 123, use_delayed=True)
    request = _MarketDataRequest(contract=SimpleNamespace(right="C"))
    runtime._market_data_requests[44] = request

    _RuntimeCallbacks.error(
        SimpleNamespace(runtime=runtime),
        44,
        1_786_725_600,
        354,
        "Requested market data is not subscribed.",
        "{}",
    )

    assert request.event.is_set()
    assert request.errors == [
        runtime_module.RuntimeErrorInfo(
            req_id=44,
            code=354,
            message="Requested market data is not subscribed.",
            error_time=1_786_725_600,
            advanced_order_reject_present=True,
        )
    ]
    diagnostic = runtime.diagnostics_snapshot()["request_errors"][-1]
    assert diagnostic["req_id"] == 44
    assert diagnostic["error_time"] == 1_786_725_600
    assert diagnostic["code"] == 354
    assert diagnostic["advanced_order_reject_present"] is True


@pytest.mark.parametrize("code", [2104, 2106, 2158])
def test_farm_status_messages_are_informational_not_request_failures(code: int) -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 124, use_delayed=True)
    request = _MarketDataRequest(contract=SimpleNamespace(right="C"))
    runtime._market_data_requests[55] = request

    _RuntimeCallbacks.error(
        SimpleNamespace(runtime=runtime),
        55,
        1_786_725_601,
        code,
        "Market data farm connection is OK.",
    )

    assert request.errors == []
    assert not request.event.is_set()
    snapshot = runtime.diagnostics_snapshot()
    assert snapshot["request_errors"] == []
    assert snapshot["informational_messages"][-1]["code"] == code
    assert snapshot["informational_messages"][-1]["error_time"] == 1_786_725_601


def test_connection_closed_callback_cancels_pending_request() -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 125, use_delayed=True)
    runtime._lifecycle_status = "connected"
    request = _ListRequest()
    runtime._matching_symbol_requests[66] = request

    _RuntimeCallbacks.connectionClosed(SimpleNamespace(runtime=runtime))

    assert runtime.lifecycle_status == "failed"
    assert request.event.is_set()
    assert request.errors[-1].message == "The TWS / IB Gateway connection closed."


def test_disconnect_cancels_pending_requests_and_cleans_up() -> None:
    class ConnectedApp:
        def __init__(self) -> None:
            self.connected = True
            self.disconnected = False

        def isConnected(self) -> bool:  # noqa: N802
            return self.connected

        def disconnect(self) -> None:
            self.connected = False
            self.disconnected = True

    runtime = IBKRRuntime("127.0.0.1", 4002, 122, use_delayed=True)
    request = _ListRequest()
    app = ConnectedApp()
    runtime._app = app
    runtime._matching_symbol_requests[55] = request

    runtime.disconnect()

    assert request.event.is_set()
    assert app.disconnected is True
    assert runtime.lifecycle_status == "disconnected"
    assert runtime._app is None


def test_runtime_maps_option_volume_and_open_interest_by_contract_side() -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 18, use_delayed=True)
    request = _MarketDataRequest(contract=SimpleNamespace(right="P"))
    runtime._market_data_requests[2] = request

    runtime._handle_tick_size(2, TickTypeEnum.OPTION_PUT_OPEN_INTEREST, 321)
    runtime._handle_tick_size(2, TickTypeEnum.OPTION_PUT_VOLUME, 98)

    assert request.payload["put_open_interest"] == 321
    assert request.payload["open_interest"] == 321
    assert request.payload["put_volume"] == 98
    assert request.payload["volume"] == 98


def test_runtime_accepts_modern_decimal_tick_sizes_without_truncation() -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 126, use_delayed=True)
    request = _MarketDataRequest(contract=SimpleNamespace(right="C"))
    runtime._market_data_requests[2] = request

    runtime._handle_tick_size(2, TickTypeEnum.OPTION_CALL_VOLUME, Decimal("123"))
    runtime._handle_tick_size(2, TickTypeEnum.OPTION_CALL_OPEN_INTEREST, Decimal("456"))

    assert request.payload["volume"] == 123
    assert request.payload["open_interest"] == 456


def test_runtime_preserves_eurusd_high_low_and_close_ticks() -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 128, use_delayed=True)
    request = _MarketDataRequest(contract=SimpleNamespace(right=""))
    runtime._market_data_requests[3] = request

    runtime._handle_tick_price(3, TickTypeEnum.HIGH, 1.18)
    runtime._handle_tick_price(3, TickTypeEnum.LOW, 1.14)
    runtime._handle_tick_price(3, TickTypeEnum.CLOSE, 1.15)

    assert request.payload["high"] == 1.18
    assert request.payload["low"] == 1.14
    assert request.payload["close"] == 1.15


def test_runtime_rejects_fractional_size_instead_of_silently_truncating() -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 127, use_delayed=True)
    request = _MarketDataRequest(contract=SimpleNamespace(right="C"))
    runtime._market_data_requests[2] = request

    runtime._handle_tick_size(2, TickTypeEnum.OPTION_CALL_VOLUME, Decimal("12.5"))

    assert "volume" not in request.payload


def test_runtime_app_option_param_callback_maps_ibkr_args_to_pythonic_helper_signature() -> None:
    class Recorder:
        def __init__(self) -> None:
            self.call: tuple[object, ...] | None = None

        def _handle_option_param(
            self,
            req_id: int,
            exchange: str,
            underlying_con_id: int,
            trading_class: str,
            multiplier: str,
            expirations: set[str],
            strikes: set[float],
        ) -> None:
            self.call = (
                req_id,
                exchange,
                underlying_con_id,
                trading_class,
                multiplier,
                expirations,
                strikes,
            )

    runtime = Recorder()

    _RuntimeCallbacks.securityDefinitionOptionParameter(
        SimpleNamespace(runtime=runtime),
        7,
        "SMART",
        756733,
        "SPY",
        "100",
        {"20260417"},
        {530.0, 535.0},
    )

    assert runtime.call == (
        7,
        "SMART",
        756733,
        "SPY",
        "100",
        {"20260417"},
        {530.0, 535.0},
    )


def test_runtime_option_param_callback_stores_data_and_signals_completion() -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 19, use_delayed=True)
    request = _ListRequest()
    runtime._option_param_requests[3] = request
    callback_host = SimpleNamespace(runtime=runtime)

    _RuntimeCallbacks.securityDefinitionOptionParameter(
        callback_host,
        3,
        "SMART",
        756733,
        "SPY",
        "100",
        {"20260516", "20260417"},
        {535.0, 530.0},
    )

    assert request.items == [
        {
            "exchange": "SMART",
            "underlying_con_id": 756733,
            "trading_class": "SPY",
            "multiplier": "100",
            "expirations": ["20260417", "20260516"],
            "strikes": [530.0, 535.0],
        }
    ]
    assert not request.event.is_set()

    _RuntimeCallbacks.securityDefinitionOptionParameterEnd(callback_host, 3)

    assert request.event.is_set()


def test_option_chain_params_wait_completes_when_callbacks_arrive(monkeypatch) -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 20, use_delayed=True)
    callback_host = SimpleNamespace(runtime=runtime)

    class FakeApp:
        def reqSecDefOptParams(
            self,
            req_id: int,
            symbol: str,
            exchange: str,
            sec_type: str,
            underlying_conid: int,
        ) -> None:
            _RuntimeCallbacks.securityDefinitionOptionParameter(
                callback_host,
                req_id,
                "SMART",
                underlying_conid,
                symbol,
                "100",
                {"20260417", "20260516"},
                {530.0, 535.0},
            )
            _RuntimeCallbacks.securityDefinitionOptionParameterEnd(callback_host, req_id)

    monkeypatch.setattr(runtime, "ensure_connected", lambda timeout=8.0: None)
    runtime._next_request_id = 11
    runtime._app = FakeApp()

    assert runtime.option_chain_params("SPY", 756733, timeout=0.05) == [
        {
            "exchange": "SMART",
            "underlying_con_id": 756733,
            "trading_class": "SPY",
            "multiplier": "100",
            "expirations": ["20260417", "20260516"],
            "strikes": [530.0, 535.0],
        }
    ]


def test_runtime_app_tick_option_computation_callback_maps_ibkr_args_to_pythonic_helper_signature() -> None:
    class Recorder:
        def __init__(self) -> None:
            self.call: tuple[object, ...] | None = None

        def _handle_tick_option_computation(
            self,
            req_id: int,
            tick_type: int,
            implied_vol: float,
            delta: float,
            option_price: float,
            pv_dividend: float,
            gamma: float,
            vega: float,
            theta: float,
            underlying_price: float,
        ) -> None:
            self.call = (
                req_id,
                tick_type,
                implied_vol,
                delta,
                option_price,
                pv_dividend,
                gamma,
                vega,
                theta,
                underlying_price,
            )

    runtime = Recorder()

    _RuntimeCallbacks.tickOptionComputation(
        SimpleNamespace(runtime=runtime),
        13,
        TickTypeEnum.DELAYED_MODEL_OPTION,
        0,
        0.24,
        0.52,
        5.26,
        0.11,
        0.04,
        0.18,
        -0.08,
        101.2,
    )

    assert runtime.call == (
        13,
        TickTypeEnum.DELAYED_MODEL_OPTION,
        0.24,
        0.52,
        5.26,
        0.11,
        0.04,
        0.18,
        -0.08,
        101.2,
    )


def test_quote_contract_does_not_guess_provenance_when_data_type_callback_is_missing(
    monkeypatch,
) -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 21, use_delayed=True)

    class FakeApp:
        def reqMarketDataType(self, market_data_type: int) -> None:
            assert market_data_type == 4

        def reqMktData(
            self,
            req_id: int,
            contract: object,
            generic_tick_list: str,
            snapshot: bool,
            regulatory_snapshot: bool,
            options: list[object],
        ) -> None:
            assert generic_tick_list == ""
            runtime._handle_tick_price(req_id, TickTypeEnum.DELAYED_BID, 5.0)
            runtime._handle_tick_price(req_id, TickTypeEnum.DELAYED_ASK, 5.4)

        def cancelMktData(self, req_id: int) -> None:
            return None

    monkeypatch.setattr(runtime, "ensure_connected", lambda timeout=8.0: None)
    runtime._next_request_id = 31
    runtime._app = FakeApp()

    payload = runtime.quote_contract(SimpleNamespace(right="C"), wait_seconds=0.05)

    assert payload["bid"] == 5.0
    assert payload["ask"] == 5.4
    assert payload["market_data_mode"] == "unconfirmed"
    assert payload["market_data_type_confirmed"] is False
    assert payload["is_delayed"] is False
    assert payload["market_data_unavailable"] is True
    assert payload["subscription_missing"] is False


@pytest.mark.parametrize(
    ("actual_type", "expected_mode", "expected_delayed", "bid_tick", "ask_tick"),
    [
        (3, "delayed", True, TickTypeEnum.DELAYED_BID, TickTypeEnum.DELAYED_ASK),
        (4, "delayed_frozen", True, TickTypeEnum.DELAYED_BID, TickTypeEnum.DELAYED_ASK),
        (1, "live", False, TickTypeEnum.BID, TickTypeEnum.ASK),
    ],
)
def test_requested_type_four_preserves_actual_callback_mode(
    monkeypatch,
    actual_type: int,
    expected_mode: str,
    expected_delayed: bool,
    bid_tick: int,
    ask_tick: int,
) -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 221, use_delayed=True)
    requested_types: list[int] = []

    class FakeApp:
        def reqMarketDataType(self, market_data_type: int) -> None:
            requested_types.append(market_data_type)

        def reqMktData(
            self,
            req_id: int,
            contract: object,
            generic_tick_list: str,
            snapshot: bool,
            regulatory_snapshot: bool,
            options: list[object],
        ) -> None:
            runtime._handle_market_data_type(req_id, actual_type)
            runtime._handle_tick_price(req_id, bid_tick, 5.0)
            runtime._handle_tick_price(req_id, ask_tick, 5.4)

        def cancelMktData(self, req_id: int) -> None:
            return None

    monkeypatch.setattr(runtime, "ensure_connected", lambda timeout=8.0: None)
    runtime._next_request_id = 81
    runtime._app = FakeApp()

    payload = runtime.quote_contract(SimpleNamespace(right="C"), wait_seconds=0.01)

    assert requested_types == [4]
    assert payload["market_data_mode"] == expected_mode
    assert payload["market_data_type_confirmed"] is True
    assert payload["is_delayed"] is expected_delayed
    assert payload["market_data_unavailable"] is False


def test_runtime_tracks_delayed_and_delayed_frozen_transitions_and_back() -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 222, use_delayed=True)
    request = _MarketDataRequest(
        contract=SimpleNamespace(right="C"),
        requested_market_data_type=4,
        payload={"bid": 5.0, "ask": 5.4},
    )
    runtime._market_data_requests[82] = request

    runtime._handle_market_data_type(82, 3)
    delayed = runtime._finalize_market_data_request(request, allow_partial=False)
    runtime._handle_market_data_type(82, 4)
    delayed_frozen = runtime._finalize_market_data_request(request, allow_partial=False)
    runtime._handle_market_data_type(82, 3)
    available_again = runtime._finalize_market_data_request(request, allow_partial=False)

    assert delayed["market_data_mode"] == "delayed"
    assert delayed_frozen["market_data_mode"] == "delayed_frozen"
    assert available_again["market_data_mode"] == "delayed"
    assert [
        item["type"] for item in runtime.diagnostics_snapshot()["last_quote"]["market_data_type_callbacks"]
    ] == [3, 4, 3]


def test_type_four_request_with_delayed_callback_and_no_prices_does_not_invent_entitlement_error(
    monkeypatch,
) -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 226, use_delayed=True)
    requested_types: list[int] = []

    class FakeApp:
        def reqMarketDataType(self, market_data_type: int) -> None:  # noqa: N802
            requested_types.append(market_data_type)

        def reqMktData(  # noqa: N802
            self,
            req_id: int,
            contract: object,
            generic_tick_list: str,
            snapshot: bool,
            regulatory_snapshot: bool,
            options: list[object],
        ) -> None:
            runtime._handle_market_data_type(req_id, 3)

        def cancelMktData(self, req_id: int) -> None:  # noqa: N802
            return None

    monkeypatch.setattr(runtime, "ensure_connected", lambda timeout=8.0: None)
    runtime._next_request_id = 85
    runtime._app = FakeApp()

    payload = runtime.quote_contract(
        SimpleNamespace(right="C"),
        wait_seconds=0.01,
        allow_partial=True,
    )

    assert requested_types == [4]
    assert payload["market_data_mode"] == "delayed"
    assert payload["quote_outcome_reason"] == "no_price_callbacks"
    assert payload["market_data_unavailable"] is True
    assert payload["subscription_missing"] is False
    diagnostics = runtime.diagnostics_snapshot()["last_quote"]
    assert diagnostics["reason_code"] == "no_price_callbacks"
    assert diagnostics["quote_provenance"] == "delayed"
    assert diagnostics["price_callbacks"] == {}
    assert diagnostics["errors"] == []


@pytest.mark.parametrize(
    ("actual_type", "expected_mode"),
    [(3, "delayed"), (4, "delayed_frozen")],
)
def test_no_usable_delayed_or_delayed_frozen_quote_reports_unavailable_callbacks(
    monkeypatch,
    actual_type: int,
    expected_mode: str,
) -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 223, use_delayed=True)

    class FakeApp:
        def reqMarketDataType(self, market_data_type: int) -> None:
            assert market_data_type == 4

        def reqMktData(
            self,
            req_id: int,
            contract: object,
            generic_tick_list: str,
            snapshot: bool,
            regulatory_snapshot: bool,
            options: list[object],
        ) -> None:
            runtime._handle_market_data_type(req_id, actual_type)
            runtime._handle_tick_price(req_id, TickTypeEnum.DELAYED_BID, -1.0)
            runtime._handle_tick_price(req_id, TickTypeEnum.DELAYED_ASK, -1.0)
            runtime._handle_tick_price(req_id, TickTypeEnum.DELAYED_LAST, -1.0)

        def cancelMktData(self, req_id: int) -> None:
            return None

    monkeypatch.setattr(runtime, "ensure_connected", lambda timeout=8.0: None)
    runtime._next_request_id = 83
    runtime._app = FakeApp()

    with pytest.raises(AdapterUnavailableError, match="No usable market data"):
        runtime.quote_contract(SimpleNamespace(right="C"), wait_seconds=0.01)

    last_quote = runtime.diagnostics_snapshot()["last_quote"]
    assert last_quote["quote_provenance"] == expected_mode
    assert last_quote["timeout_stage"] == "market_data_wait"
    assert last_quote["price_callbacks"] == {
        "bid": {"received": 1, "usable": 0, "unavailable": 1},
        "ask": {"received": 1, "usable": 0, "unavailable": 1},
        "last": {"received": 1, "usable": 0, "unavailable": 1},
    }


def test_live_only_mode_keeps_default_live_request_behavior(monkeypatch) -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 224, use_delayed=False)
    requested_types: list[int] = []

    class FakeApp:
        def reqMarketDataType(self, market_data_type: int) -> None:
            requested_types.append(market_data_type)

        def reqMktData(
            self,
            req_id: int,
            contract: object,
            generic_tick_list: str,
            snapshot: bool,
            regulatory_snapshot: bool,
            options: list[object],
        ) -> None:
            runtime._handle_market_data_type(req_id, 1)
            runtime._handle_tick_price(req_id, TickTypeEnum.BID, 5.0)
            runtime._handle_tick_price(req_id, TickTypeEnum.ASK, 5.4)

        def cancelMktData(self, req_id: int) -> None:
            return None

    monkeypatch.setattr(runtime, "ensure_connected", lambda timeout=8.0: None)
    runtime._next_request_id = 84
    runtime._app = FakeApp()

    payload = runtime.quote_contract(SimpleNamespace(right="C"), wait_seconds=0.01)

    assert requested_types == []
    assert runtime.requested_market_data_type == 1
    assert payload["market_data_mode"] == "live"
    assert payload["requested_mode_compatible"] is True
    assert payload["market_data_unavailable"] is False


@pytest.mark.parametrize(
    ("actual_type", "expected_mode"),
    [(2, "frozen"), (3, "delayed"), (4, "delayed_frozen")],
)
def test_live_only_mode_preserves_but_rejects_non_live_callbacks(
    actual_type: int,
    expected_mode: str,
) -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 225, use_delayed=False)
    request = _MarketDataRequest(
        contract=SimpleNamespace(right="C"),
        requested_market_data_type=1,
        payload={"bid": 5.0, "ask": 5.4, "market_data_type": actual_type},
    )

    payload = runtime._finalize_market_data_request(request, allow_partial=False)

    assert payload["market_data_mode"] == expected_mode
    assert payload["market_data_type_confirmed"] is True
    assert payload["requested_mode_compatible"] is False
    assert payload["market_data_unavailable"] is True


def test_quote_contract_returns_partial_payload_when_permissions_are_missing(monkeypatch) -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 22, use_delayed=True)

    class FakeApp:
        def reqMarketDataType(self, market_data_type: int) -> None:
            assert market_data_type == 4

        def reqMktData(
            self,
            req_id: int,
            contract: object,
            generic_tick_list: str,
            snapshot: bool,
            regulatory_snapshot: bool,
            options: list[object],
        ) -> None:
            runtime._handle_market_data_type(req_id, 4)
            runtime._handle_error(req_id, 354, "Requested market data is not subscribed.")

        def cancelMktData(self, req_id: int) -> None:
            return None

    monkeypatch.setattr(runtime, "ensure_connected", lambda timeout=8.0: None)
    runtime._next_request_id = 41
    runtime._app = FakeApp()

    payload = runtime.quote_contract(
        SimpleNamespace(right="P"),
        wait_seconds=0.05,
        allow_partial=True,
    )

    assert payload["market_data_mode"] == "delayed_frozen"
    assert payload["is_delayed"] is True
    assert payload["market_data_unavailable"] is True
    assert payload["subscription_missing"] is True
    assert "bid" not in payload
    assert "ask" not in payload


@pytest.mark.parametrize(
    ("error_code", "error_message"),
    [
        (
            10167,
            "Requested market data is not subscribed. Displaying delayed market data.",
        ),
        (
            10089,
            "Requested market data requires additional subscription for API.",
        ),
    ],
)
def test_quote_contract_waits_for_delayed_payload_after_subscription_limited_notice(
    monkeypatch,
    error_code: int,
    error_message: str,
) -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 24, use_delayed=True)
    workers: list[threading.Thread] = []

    class FakeApp:
        def reqMarketDataType(self, market_data_type: int) -> None:
            assert market_data_type == 4

        def reqMktData(
            self,
            req_id: int,
            contract: object,
            generic_tick_list: str,
            snapshot: bool,
            regulatory_snapshot: bool,
            options: list[object],
        ) -> None:
            runtime._handle_market_data_type(req_id, 3)
            runtime._handle_error(req_id, error_code, error_message)

            def emit_delayed_close() -> None:
                time.sleep(0.2)
                runtime._handle_tick_price(req_id, TickTypeEnum.DELAYED_CLOSE, 10.0)

            worker = threading.Thread(target=emit_delayed_close)
            worker.start()
            workers.append(worker)

        def cancelMktData(self, req_id: int) -> None:
            return None

    monkeypatch.setattr(runtime, "ensure_connected", lambda timeout=8.0: None)
    runtime._next_request_id = 61
    runtime._app = FakeApp()

    payload = runtime.quote_contract(
        SimpleNamespace(right="C"),
        wait_seconds=0.4,
        allow_partial=True,
    )

    for worker in workers:
        worker.join(timeout=1.0)

    assert payload["close"] == 10.0
    assert payload["market_data_unavailable"] is False
    assert payload["subscription_missing"] is True


def test_quote_contract_still_raises_for_genuinely_fatal_market_data_errors(monkeypatch) -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 25, use_delayed=True)

    class FakeApp:
        def reqMarketDataType(self, market_data_type: int) -> None:
            assert market_data_type == 4

        def reqMktData(
            self,
            req_id: int,
            contract: object,
            generic_tick_list: str,
            snapshot: bool,
            regulatory_snapshot: bool,
            options: list[object],
        ) -> None:
            runtime._handle_error(req_id, 502, "Couldn't connect to TWS.")

        def cancelMktData(self, req_id: int) -> None:
            return None

    monkeypatch.setattr(runtime, "ensure_connected", lambda timeout=8.0: None)
    runtime._next_request_id = 71
    runtime._app = FakeApp()

    with pytest.raises(AdapterUnavailableError, match=r"\[502\] Couldn't connect to TWS\."):
        runtime.quote_contract(SimpleNamespace(right="P"), wait_seconds=0.05)


def test_quote_contracts_batches_requests_and_keeps_partial_failures_local(monkeypatch) -> None:
    runtime = IBKRRuntime("127.0.0.1", 4002, 23, use_delayed=True)

    class FakeApp:
        def reqMarketDataType(self, market_data_type: int) -> None:
            assert market_data_type == 4

        def reqMktData(
            self,
            req_id: int,
            contract: object,
            generic_tick_list: str,
            snapshot: bool,
            regulatory_snapshot: bool,
            options: list[object],
        ) -> None:
            if getattr(contract, "right", "") == "C":
                runtime._handle_market_data_type(req_id, 3)
                runtime._handle_tick_price(req_id, TickTypeEnum.DELAYED_BID, 5.0)
                runtime._handle_tick_price(req_id, TickTypeEnum.DELAYED_ASK, 5.4)
                return
            runtime._handle_market_data_type(req_id, 4)
            runtime._handle_error(req_id, 354, "Requested market data is not subscribed.")

        def cancelMktData(self, req_id: int) -> None:
            return None

    monkeypatch.setattr(runtime, "ensure_connected", lambda timeout=8.0: None)
    runtime._next_request_id = 51
    runtime._app = FakeApp()

    payloads = runtime.quote_contracts(
        [
            ("SPY-2026-04-17-530.00-C", SimpleNamespace(right="C")),
            ("SPY-2026-04-17-530.00-P", SimpleNamespace(right="P")),
        ],
        wait_seconds=0.05,
        allow_partial=True,
    )

    assert payloads["SPY-2026-04-17-530.00-C"]["bid"] == 5.0
    assert payloads["SPY-2026-04-17-530.00-C"]["ask"] == 5.4
    assert payloads["SPY-2026-04-17-530.00-C"]["market_data_unavailable"] is False
    assert payloads["SPY-2026-04-17-530.00-P"]["market_data_unavailable"] is True
    assert payloads["SPY-2026-04-17-530.00-P"]["subscription_missing"] is True
