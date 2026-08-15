from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence

from app.services.adapters.base import (
    AdapterUnavailableError,
    AmbiguousContractError,
    UnknownSymbolError,
)
from app.services.adapters.ibkr_compat import IBAPICompatibility, require_compatible_ibapi

try:  # pragma: no cover - exercised indirectly when ibapi is installed
    from ibapi.client import EClient
    from ibapi.common import TickerId
    from ibapi.contract import Contract, ContractDescription, ContractDetails
    from ibapi.ticktype import TickTypeEnum
    from ibapi.wrapper import EWrapper

    IBAPI_AVAILABLE = True
except ImportError:  # pragma: no cover
    EClient = object  # type: ignore[assignment]
    EWrapper = object  # type: ignore[assignment]
    Contract = object  # type: ignore[assignment]
    ContractDescription = object  # type: ignore[assignment]
    ContractDetails = object  # type: ignore[assignment]
    TickerId = int  # type: ignore[assignment]
    TickTypeEnum = None  # type: ignore[assignment]
    IBAPI_AVAILABLE = False


CONNECTION_ERROR_CODES = {502, 504, 1100}
CONNECTION_RECOVERY_CODES = {1101, 1102}
FARM_STATUS_ERROR_CODES = {2104, 2106, 2107, 2108, 2158}
IGNORED_ERROR_CODES = FARM_STATUS_ERROR_CODES | {10167}
TRACKED_INFO_ERROR_CODES = {10167}
SUBSCRIPTION_ERROR_CODES = {354, 10089, 10090, 10167}
UNSET_DOUBLE = 1.7976931348623157e308
SUBSCRIPTION_ERROR_FRAGMENTS = (
    "not subscribed",
    "subscription",
    "permission",
    "permissions",
    "market data is not enabled",
    "market data not enabled",
)
DELAYED_ONLY_ERROR_FRAGMENTS = ("delayed market data",)
REQUEST_POLL_INTERVAL_SECONDS = 0.05
CONTRACT_DETAILS_QUIET_PERIOD_SECONDS = 0.1
LIVE_MARKET_DATA_TYPE = 1
DELAYED_FROZEN_MARKET_DATA_TYPE = 4
MARKET_DATA_TYPE_NAMES = {
    1: "live",
    2: "frozen",
    3: "delayed",
    4: "delayed_frozen",
}


@dataclass(slots=True)
class RuntimeErrorInfo:
    req_id: int
    code: int
    message: str
    error_time: int | None = None
    advanced_order_reject_present: bool = False


@dataclass(slots=True)
class QuoteErrorClassification:
    subscription_missing: bool = False
    delayed_only: bool = False


@dataclass(slots=True)
class _ListRequest:
    event: threading.Event = field(default_factory=threading.Event)
    items: list[dict[str, Any]] = field(default_factory=list)
    errors: list[RuntimeErrorInfo] = field(default_factory=list)
    last_update_monotonic: float = field(default_factory=time.monotonic)

    def note_update(self) -> None:
        self.last_update_monotonic = time.monotonic()

    def is_quiet(self, quiet_period: float) -> bool:
        return time.monotonic() - self.last_update_monotonic >= quiet_period


@dataclass(slots=True)
class _MarketDataRequest:
    contract: Any
    event: threading.Event = field(default_factory=threading.Event)
    errors: list[RuntimeErrorInfo] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    last_update_monotonic: float = field(default_factory=time.monotonic)
    option_computation_priority: int = -1
    requested_market_data_type: int = LIVE_MARKET_DATA_TYPE
    market_data_type_callbacks: list[int] = field(default_factory=list)
    price_callbacks: dict[str, dict[str, int]] = field(default_factory=dict)
    timeout_stage: str | None = None
    started_monotonic: float = field(default_factory=time.monotonic)

    def note_update(self) -> None:
        self.last_update_monotonic = time.monotonic()
        self.event.set()

    def has_payload(self) -> bool:
        interesting_keys = (
            "bid",
            "ask",
            "last",
            "close",
            "open",
            "volume",
            "call_open_interest",
            "put_open_interest",
            "broker_model_price",
            "broker_implied_vol",
            "broker_underlying_price",
        )
        return any(self.payload.get(key) not in {None, ""} for key in interesting_keys)

    def has_core_quote(self) -> bool:
        interesting_keys = (
            "bid",
            "ask",
            "last",
            "close",
            "open",
            "broker_model_price",
            "broker_implied_vol",
            "broker_underlying_price",
            "broker_pv_dividend",
        )
        if any(self.payload.get(key) not in {None, ""} for key in interesting_keys):
            return True
        broker_greeks = self.payload.get("broker_greeks") or {}
        return any(broker_greeks.get(key) not in {None, ""} for key in ("delta", "gamma", "theta", "vega"))

    def is_quiet(self, quiet_period: float) -> bool:
        return time.monotonic() - self.last_update_monotonic >= quiet_period


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_valid_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value) and value != UNSET_DOUBLE


def _clean_price(value: Any) -> float | None:
    if not _is_valid_number(value):
        return None
    numeric = float(value)
    return numeric if numeric >= 0.0 else None


def _clean_broker_implied_vol(value: Any) -> float | None:
    if not _is_valid_number(value):
        return None
    numeric = float(value)
    return numeric if numeric > 0.0 else None


def _clean_broker_greek(value: Any) -> float | None:
    if not _is_valid_number(value):
        return None
    return float(value)


def _clean_size(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = value if isinstance(value, Decimal) else Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return None
    if not numeric.is_finite() or numeric < 0 or numeric != numeric.to_integral_value():
        return None
    return int(numeric)


def _market_mode_name(market_data_type: int | None) -> str:
    return MARKET_DATA_TYPE_NAMES.get(market_data_type, "unconfirmed")


def _is_delayed_mode(market_data_type: int | None) -> bool:
    return market_data_type in {3, 4}


def _price_callback_field(tick_name: str) -> str | None:
    if tick_name in {"BID", "DELAYED_BID", "DELAYED_BID_OPTION"}:
        return "bid"
    if tick_name in {"ASK", "DELAYED_ASK", "DELAYED_ASK_OPTION"}:
        return "ask"
    if tick_name in {"LAST", "DELAYED_LAST", "DELAYED_LAST_OPTION"}:
        return "last"
    if tick_name in {"HIGH", "DELAYED_HIGH"}:
        return "high"
    if tick_name in {"LOW", "DELAYED_LOW"}:
        return "low"
    if tick_name in {"CLOSE", "DELAYED_CLOSE"}:
        return "close"
    if tick_name in {"OPEN", "DELAYED_OPEN"}:
        return "open"
    return None


def _tick_type_name(tick_type: int) -> str:
    if TickTypeEnum is None:
        return f"UNKNOWN_{tick_type}"
    converter = getattr(TickTypeEnum, "toStr", None)
    if not callable(converter):
        return f"UNKNOWN_{tick_type}"
    return str(converter(tick_type))


def _error_to_dict(error: RuntimeErrorInfo) -> dict[str, Any]:
    return {
        "req_id": error.req_id,
        "error_time": error.error_time,
        "code": error.code,
        "message": error.message,
        "advanced_order_reject_present": error.advanced_order_reject_present,
    }


def _exchange_timestamp(value: Any) -> str | None:
    """Convert IBKR's LAST_TIMESTAMP epoch-seconds value to an ISO UTC timestamp."""
    if value in {None, ""}:
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(timestamp) or timestamp < 0.0:
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _classify_quote_errors(errors: list[RuntimeErrorInfo]) -> QuoteErrorClassification:
    classification = QuoteErrorClassification()
    for error in errors:
        message = error.message.lower()
        if error.code in SUBSCRIPTION_ERROR_CODES or any(
            fragment in message for fragment in SUBSCRIPTION_ERROR_FRAGMENTS
        ):
            classification.subscription_missing = True
        if error.code in TRACKED_INFO_ERROR_CODES or any(
            fragment in message for fragment in DELAYED_ONLY_ERROR_FRAGMENTS
        ):
            classification.delayed_only = True
    return classification


def _price_callback_summary(bucket: _MarketDataRequest) -> dict[str, bool]:
    summary: dict[str, bool] = {}
    for field_name in ("bid", "ask", "last"):
        stats = bucket.price_callbacks.get(field_name, {})
        summary[f"{field_name}_received"] = int(stats.get("received", 0)) > 0
        summary[f"{field_name}_unavailable"] = int(stats.get("unavailable", 0)) > 0
    return summary


def _quote_outcome_reason(
    bucket: _MarketDataRequest,
    *,
    core_quote_available: bool,
    market_data_type: int | None,
) -> str:
    error_classification = _classify_quote_errors(bucket.errors)
    if error_classification.subscription_missing and not core_quote_available:
        return "subscription_missing"
    if core_quote_available:
        bid_usable = int(bucket.price_callbacks.get("bid", {}).get("usable", 0)) > 0
        ask_usable = int(bucket.price_callbacks.get("ask", {}).get("usable", 0)) > 0
        return "success" if bid_usable and ask_usable else "partial_quote"
    if not bucket.price_callbacks and market_data_type in MARKET_DATA_TYPE_NAMES:
        return "no_price_callbacks"
    if _is_delayed_mode(market_data_type) and any(
        int(stats.get("unavailable", 0)) > 0 for stats in bucket.price_callbacks.values()
    ):
        return "delayed_data_unavailable"
    if bucket.timeout_stage is not None:
        return "request_timeout"
    return "partial_quote"


def _contract_to_dict(contract: Any) -> dict[str, Any]:
    return {
        "con_id": getattr(contract, "conId", 0) or None,
        "symbol": getattr(contract, "symbol", ""),
        "sec_type": getattr(contract, "secType", ""),
        "exchange": getattr(contract, "exchange", ""),
        "primary_exchange": getattr(contract, "primaryExchange", ""),
        "currency": getattr(contract, "currency", ""),
        "local_symbol": getattr(contract, "localSymbol", ""),
        "trading_class": getattr(contract, "tradingClass", ""),
        "last_trade_date_or_contract_month": getattr(contract, "lastTradeDateOrContractMonth", ""),
        "strike": getattr(contract, "strike", None),
        "right": getattr(contract, "right", ""),
        "multiplier": getattr(contract, "multiplier", ""),
    }


def _contract_details_to_dict(details: Any) -> dict[str, Any]:
    contract = getattr(details, "contract", None)
    payload = _contract_to_dict(contract)
    payload.update(
        {
            "long_name": getattr(details, "longName", ""),
            "market_name": getattr(details, "marketName", ""),
            "min_tick": getattr(details, "minTick", None),
            "valid_exchanges": getattr(details, "validExchanges", ""),
            "under_con_id": getattr(details, "underConId", None),
            "contract_month": getattr(details, "contractMonth", ""),
            "time_zone_id": getattr(details, "timeZoneId", ""),
            "trading_hours": getattr(details, "tradingHours", ""),
            "liquid_hours": getattr(details, "liquidHours", ""),
            "stock_type": getattr(details, "stockType", ""),
        }
    )
    return payload


class _RuntimeCallbacks:
    runtime: "IBKRRuntime"

    def nextValidId(self, orderId: int) -> None:  # noqa: N802 - IB API callback name
        self.runtime._handle_next_valid_id(orderId)

    def error(
        self,
        reqId: int,
        errorTime: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:  # noqa: N802
        self.runtime._handle_error(
            reqId,
            errorCode,
            errorString,
            error_time=errorTime,
            advanced_order_reject_present=bool(advancedOrderRejectJson),
        )

    def symbolSamples(  # noqa: N802
        self,
        reqId: int,
        contractDescriptions: list[ContractDescription],
    ) -> None:
        self.runtime._handle_symbol_samples(reqId, contractDescriptions)

    def contractDetails(self, reqId: int, contractDetails: ContractDetails) -> None:  # noqa: N802
        self.runtime._handle_contract_details(reqId, contractDetails)

    def contractDetailsEnd(self, reqId: int) -> None:  # noqa: N802
        self.runtime._handle_contract_details_end(reqId)

    def securityDefinitionOptionParameter(  # noqa: N802
        self,
        reqId: int,
        exchange: str,
        underlyingConId: int,
        tradingClass: str,
        multiplier: str,
        expirations: set[str],
        strikes: set[float],
    ) -> None:
        self.runtime._handle_option_param(
            reqId,
            exchange,
            underlyingConId,
            tradingClass,
            multiplier,
            expirations,
            strikes,
        )

    def securityDefinitionOptionParameterEnd(self, reqId: int) -> None:  # noqa: N802
        self.runtime._handle_option_param_end(reqId)

    def marketDataType(self, reqId: int, marketDataType: int) -> None:  # noqa: N802
        self.runtime._handle_market_data_type(reqId, marketDataType)

    def tickPrice(  # noqa: N802
        self,
        reqId: TickerId,
        tickType: int,
        price: float,
        attrib: Any,
    ) -> None:
        self.runtime._handle_tick_price(reqId, tickType, price)

    def tickSize(self, reqId: TickerId, tickType: int, size: Decimal) -> None:  # noqa: N802
        self.runtime._handle_tick_size(reqId, tickType, size)

    def tickString(self, reqId: TickerId, tickType: int, value: str) -> None:  # noqa: N802
        self.runtime._handle_tick_string(reqId, tickType, value)

    def tickOptionComputation(  # noqa: N802
        self,
        reqId: int,
        tickType: int,
        tickAttrib: int,
        impliedVol: float,
        delta: float,
        optPrice: float,
        pvDividend: float,
        gamma: float,
        vega: float,
        theta: float,
        undPrice: float,
    ) -> None:
        self.runtime._handle_tick_option_computation(
            reqId,
            tickType,
            impliedVol,
            delta,
            optPrice,
            pvDividend,
            gamma,
            vega,
            theta,
            undPrice,
        )

    def connectionClosed(self) -> None:  # noqa: N802
        self.runtime._handle_connection_closed()


if IBAPI_AVAILABLE:  # pragma: no branch

    class _RuntimeApp(_RuntimeCallbacks, EWrapper, EClient):
        def __init__(self, runtime: "IBKRRuntime") -> None:
            EWrapper.__init__(self)
            EClient.__init__(self, wrapper=self)
            self.runtime = runtime
else:  # pragma: no cover - deterministic tests use the callback bridge directly
    _RuntimeApp = _RuntimeCallbacks  # type: ignore[misc,assignment]


class IBKRRuntime:
    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        use_delayed: bool = True,
        *,
        compatibility: IBAPICompatibility | None = None,
    ) -> None:
        self._compatibility = compatibility or require_compatible_ibapi()
        self.host = host
        self.port = port
        self.client_id = client_id
        self.use_delayed = use_delayed

        self._app: _RuntimeApp | None = None
        self._thread: threading.Thread | None = None
        self._connect_lock = threading.RLock()
        self._request_id_lock = threading.Lock()
        self._requests_lock = threading.Lock()
        self._connected_event = threading.Event()
        self._next_request_id: int | None = None
        self._connection_error: RuntimeErrorInfo | None = None
        self._lifecycle_status = "disconnected"
        self._server_version: int | None = None

        self._matching_symbol_requests: dict[int, _ListRequest] = {}
        self._contract_detail_requests: dict[int, _ListRequest] = {}
        self._option_param_requests: dict[int, _ListRequest] = {}
        self._market_data_requests: dict[int, _MarketDataRequest] = {}
        self._diagnostic_errors: list[RuntimeErrorInfo] = []
        self._informational_messages: list[RuntimeErrorInfo] = []
        self._market_data_type_callbacks: list[int] = []
        self._last_quote_diagnostics: dict[str, Any] = {}

    @property
    def lifecycle_status(self) -> str:
        return self._lifecycle_status

    @property
    def requested_market_data_type(self) -> int:
        return DELAYED_FROZEN_MARKET_DATA_TYPE if self.use_delayed else LIVE_MARKET_DATA_TYPE

    @property
    def requested_market_data_mode(self) -> str:
        return "delayed_frozen_capable" if self.use_delayed else "live_only"

    def diagnostics_snapshot(self) -> dict[str, Any]:
        with self._requests_lock:
            callbacks = [
                {"type": item, "mode": _market_mode_name(item)}
                for item in self._market_data_type_callbacks[-20:]
            ]
            errors = [_error_to_dict(error) for error in self._diagnostic_errors[-12:]]
            informational_messages = [_error_to_dict(error) for error in self._informational_messages[-12:]]
            last_quote = {
                **self._last_quote_diagnostics,
                "price_callbacks": {
                    key: dict(value)
                    for key, value in self._last_quote_diagnostics.get("price_callbacks", {}).items()
                },
            }
        return {
            **self._compatibility.diagnostics(),
            "lifecycle_status": self._lifecycle_status,
            "api_handshake_succeeded": self._next_request_id is not None,
            "tws_server_version": self._server_version,
            "requested_market_data_type": self.requested_market_data_type,
            "requested_market_data_mode": self.requested_market_data_mode,
            "market_data_type_callbacks": callbacks,
            "request_errors": errors,
            "relevant_errors": errors,
            "informational_messages": informational_messages,
            "last_quote": last_quote,
        }

    def _request_market_data_mode(self, app: Any) -> None:
        if self.use_delayed:
            app.reqMarketDataType(self.requested_market_data_type)

    def ensure_connected(self, timeout: float = 8.0, reconnect_attempts: int = 1) -> None:
        if self._app is not None and self._app.isConnected():
            self._lifecycle_status = "connected"
            return

        with self._connect_lock:
            if self._app is not None and self._app.isConnected():
                self._lifecycle_status = "connected"
                return

            attempts = max(reconnect_attempts, 0) + 1
            last_message = "Timed out while connecting to TWS / IB Gateway."
            for attempt in range(attempts):
                self._disconnect_unlocked("IBKR connection is being reinitialized.")
                self._connected_event.clear()
                self._connection_error = None
                self._lifecycle_status = "connecting" if attempt == 0 else "reconnecting"
                app = _RuntimeApp(self)
                self._app = app
                try:
                    app.connect(self.host, self.port, self.client_id)
                    thread = threading.Thread(target=app.run, name="ibkr-runtime", daemon=True)
                    self._thread = thread
                    thread.start()
                except Exception as error:
                    last_message = f"Unable to connect to TWS / IB Gateway: {error}"
                    self._disconnect_unlocked(last_message)
                    continue

                connected = self._connected_event.wait(timeout)
                if (
                    connected
                    and self._connection_error is None
                    and self._next_request_id is not None
                    and app.isConnected()
                ):
                    self._lifecycle_status = "connected"
                    try:
                        self._server_version = int(app.serverVersion())
                    except (AttributeError, TypeError, ValueError):
                        self._server_version = None
                    self._request_market_data_mode(app)
                    return

                if self._connection_error is not None:
                    last_message = self._connection_error.message
                self._disconnect_unlocked(last_message)

            self._lifecycle_status = "failed"
            raise AdapterUnavailableError(last_message)

    def disconnect(self) -> None:
        with self._connect_lock:
            self._disconnect_unlocked("IBKR adapter is shutting down.")

    close = disconnect

    def _disconnect_unlocked(self, pending_message: str) -> None:
        self._lifecycle_status = "closing"
        self._cancel_pending_requests(pending_message)
        app = self._app
        thread = self._thread
        self._app = None
        self._thread = None
        self._connected_event.clear()
        self._next_request_id = None
        if app is not None:
            try:
                if app.isConnected():
                    app.disconnect()
            finally:
                if thread is not None and thread is not threading.current_thread():
                    thread.join(timeout=1.0)
        self._lifecycle_status = "disconnected"

    def is_connected(self) -> bool:
        return self._app is not None and self._app.isConnected()

    def matching_symbols(self, query: str, timeout: float = 5.0) -> list[dict[str, Any]]:
        self.ensure_connected()
        req_id = self._next_req_id()
        bucket = _ListRequest()
        with self._requests_lock:
            self._matching_symbol_requests[req_id] = bucket
        try:
            assert self._app is not None
            self._app.reqMatchingSymbols(req_id, query)
            self._wait_for(bucket.event, timeout, "Timed out waiting for symbol matches")
            self._raise_first_error(bucket.errors, fallback="IBKR symbol search failed.")
            return bucket.items
        finally:
            with self._requests_lock:
                self._matching_symbol_requests.pop(req_id, None)

    def qualify_underlying(self, symbol: str, timeout: float = 6.0) -> dict[str, Any]:
        contract = Contract()
        contract.symbol = symbol.upper()
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        details = self._request_contract_details(contract, timeout)
        candidates = [
            item for item in details if item.get("sec_type") == "STK" and item.get("currency") == "USD"
        ]
        if not candidates:
            raise UnknownSymbolError(f"Unknown IBKR symbol: {symbol.upper()}.")

        preferred_exchanges = {"NASDAQ", "NYSE", "ARCA", "BATS"}

        def rank(item: dict[str, Any]) -> tuple[bool, bool, bool]:
            return (
                item.get("symbol", "").upper() != symbol.upper(),
                item.get("primary_exchange") not in preferred_exchanges,
                item.get("exchange") != "SMART",
            )

        candidates.sort(key=rank)
        best_rank = rank(candidates[0])
        equally_ranked = [item for item in candidates if rank(item) == best_rank]
        identities = {
            (item.get("con_id"), item.get("primary_exchange"), item.get("trading_class"))
            for item in equally_ranked
        }
        if len(identities) > 1:
            raise AmbiguousContractError(
                f"IBKR returned multiple equally plausible contracts for {symbol.upper()}."
            )
        return candidates[0]

    def option_chain_params(
        self,
        symbol: str,
        underlying_conid: int,
        timeout: float = 6.0,
    ) -> list[dict[str, Any]]:
        self.ensure_connected()
        req_id = self._next_req_id()
        bucket = _ListRequest()
        with self._requests_lock:
            self._option_param_requests[req_id] = bucket
        try:
            assert self._app is not None
            self._app.reqSecDefOptParams(req_id, symbol.upper(), "", "STK", underlying_conid)
            self._wait_for(bucket.event, timeout, "Timed out waiting for option chain parameters")
            self._raise_first_error(bucket.errors, fallback="IBKR option chain lookup failed.")
            return bucket.items
        finally:
            with self._requests_lock:
                self._option_param_requests.pop(req_id, None)

    def quote_contract(
        self,
        contract: Any,
        generic_tick_list: str = "",
        wait_seconds: float = 1.5,
        allow_partial: bool = False,
    ) -> dict[str, Any]:
        self.ensure_connected()
        req_id = self._next_req_id()
        bucket = _MarketDataRequest(
            contract=contract,
            requested_market_data_type=self.requested_market_data_type,
        )
        with self._requests_lock:
            self._market_data_requests[req_id] = bucket

        assert self._app is not None
        app = self._app
        try:
            self._request_market_data_mode(app)
            app.reqMktData(req_id, contract, generic_tick_list, False, False, [])
            self._wait_for_market_data(
                [bucket],
                wait_seconds=wait_seconds,
                allow_partial=allow_partial,
                use_delayed=self.use_delayed,
            )
            return self._finalize_market_data_request(bucket, allow_partial=allow_partial)
        finally:
            try:
                app.cancelMktData(req_id)
            finally:
                with self._requests_lock:
                    self._market_data_requests.pop(req_id, None)

    def quote_contracts(
        self,
        contracts: list[tuple[str, Any]],
        generic_tick_list: str = "",
        wait_seconds: float = 1.5,
        allow_partial: bool = False,
    ) -> dict[str, dict[str, Any]]:
        if not contracts:
            return {}

        self.ensure_connected()
        assert self._app is not None
        app = self._app
        requests: list[tuple[str, int, _MarketDataRequest]] = []
        try:
            self._request_market_data_mode(app)

            for cache_key, contract in contracts:
                req_id = self._next_req_id()
                bucket = _MarketDataRequest(
                    contract=contract,
                    requested_market_data_type=self.requested_market_data_type,
                )
                with self._requests_lock:
                    self._market_data_requests[req_id] = bucket
                requests.append((cache_key, req_id, bucket))
                app.reqMktData(req_id, contract, generic_tick_list, False, False, [])

            self._wait_for_market_data(
                [bucket for _, _, bucket in requests],
                wait_seconds=wait_seconds,
                allow_partial=allow_partial,
                use_delayed=self.use_delayed,
            )
            return {
                cache_key: self._finalize_market_data_request(bucket, allow_partial=allow_partial)
                for cache_key, _, bucket in requests
            }
        finally:
            for _, req_id, _ in requests:
                try:
                    app.cancelMktData(req_id)
                finally:
                    with self._requests_lock:
                        self._market_data_requests.pop(req_id, None)

    def _request_contract_details(self, contract: Any, timeout: float) -> list[dict[str, Any]]:
        self.ensure_connected()
        req_id = self._next_req_id()
        bucket = _ListRequest()
        with self._requests_lock:
            self._contract_detail_requests[req_id] = bucket
        try:
            assert self._app is not None
            self._app.reqContractDetails(req_id, contract)
            self._wait_for_contract_details(
                bucket,
                timeout,
                "Timed out waiting for contract details",
            )
            self._raise_first_error(bucket.errors, fallback="IBKR contract details lookup failed.")
            return bucket.items
        finally:
            with self._requests_lock:
                self._contract_detail_requests.pop(req_id, None)

    def _next_req_id(self) -> int:
        self.ensure_connected()
        with self._request_id_lock:
            if self._next_request_id is None:
                raise AdapterUnavailableError("IBKR request id is not initialized.")
            req_id = self._next_request_id
            self._next_request_id += 1
            return req_id

    @staticmethod
    def _wait_for(event: threading.Event, timeout: float, message: str) -> None:
        if not event.wait(timeout):
            raise AdapterUnavailableError(message)

    @staticmethod
    def _wait_for_contract_details(
        bucket: _ListRequest,
        timeout: float,
        message: str,
    ) -> None:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if bucket.items:
                    return
                raise AdapterUnavailableError(message)
            if bucket.event.wait(min(REQUEST_POLL_INTERVAL_SECONDS, remaining)):
                return
            if bucket.items and bucket.is_quiet(CONTRACT_DETAILS_QUIET_PERIOD_SECONDS):
                return

    @staticmethod
    def _raise_first_error(errors: list[RuntimeErrorInfo], *, fallback: str) -> None:
        if not errors:
            return
        first_error = next(
            (error for error in errors if error.code not in TRACKED_INFO_ERROR_CODES),
            errors[0],
        )
        raise AdapterUnavailableError(f"{fallback} [{first_error.code}] {first_error.message}")

    @staticmethod
    def _wait_for_market_data(
        buckets: Sequence[_MarketDataRequest],
        *,
        wait_seconds: float,
        allow_partial: bool,
        use_delayed: bool,
    ) -> None:
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if all(
                IBKRRuntime._market_data_request_complete(
                    bucket,
                    allow_partial=allow_partial,
                    use_delayed=use_delayed,
                )
                for bucket in buckets
            ):
                return
            time.sleep(min(0.05, max(0.01, deadline - time.monotonic())))
        for bucket in buckets:
            if not bucket.has_core_quote():
                bucket.timeout_stage = "market_data_wait"

    @staticmethod
    def _market_data_request_complete(
        bucket: _MarketDataRequest,
        *,
        allow_partial: bool,
        use_delayed: bool,
    ) -> bool:
        if bucket.has_payload() and bucket.is_quiet(0.25):
            return True
        if allow_partial and (bucket.payload or bucket.errors):
            diagnostics = _classify_quote_errors(bucket.errors)
            fatal_errors = [
                error
                for error in bucket.errors
                if error.code not in TRACKED_INFO_ERROR_CODES | SUBSCRIPTION_ERROR_CODES
            ]
            if fatal_errors:
                return True
            if (
                use_delayed
                and (diagnostics.delayed_only or diagnostics.subscription_missing)
                and not bucket.has_payload()
            ):
                return False
            if bucket.is_quiet(0.15):
                return True
        return False

    def _finalize_market_data_request(
        self,
        bucket: _MarketDataRequest,
        *,
        allow_partial: bool,
    ) -> dict[str, Any]:
        payload = dict(bucket.payload)
        diagnostics = _classify_quote_errors(bucket.errors)
        core_quote_available = bucket.has_core_quote()
        market_data_type = payload.get("market_data_type")
        market_data_mode = _market_mode_name(market_data_type)
        provenance_confirmed = market_data_type in MARKET_DATA_TYPE_NAMES
        requested_mode_compatible = self.use_delayed or market_data_type == LIVE_MARKET_DATA_TYPE
        outcome_reason = _quote_outcome_reason(
            bucket,
            core_quote_available=core_quote_available,
            market_data_type=market_data_type,
        )
        if not core_quote_available and not allow_partial:
            self._record_quote_diagnostics(
                bucket,
                market_data_mode=market_data_mode,
                core_quote_available=False,
                provenance_confirmed=provenance_confirmed,
                requested_mode_compatible=requested_mode_compatible,
                outcome_reason=outcome_reason,
            )
            if bucket.errors:
                self._raise_first_error(
                    bucket.errors,
                    fallback="No usable market data was received from IBKR.",
                )
            raise AdapterUnavailableError("No usable market data was received from IBKR.")

        is_delayed = _is_delayed_mode(market_data_type)
        received_at = _now_utc().isoformat()
        exchange_timestamp = _exchange_timestamp(payload.get("last_timestamp"))
        payload.update(
            {
                # Keep the legacy timestamp field while exposing the two clocks explicitly.
                "timestamp": exchange_timestamp or received_at,
                "exchange_timestamp": exchange_timestamp,
                "received_at": received_at,
                "market_data_mode": market_data_mode,
                "market_data_type_confirmed": provenance_confirmed,
                "requested_mode_compatible": requested_mode_compatible,
                "is_delayed": is_delayed,
                "quote_outcome_reason": outcome_reason,
                "elapsed_request_seconds": round(time.monotonic() - bucket.started_monotonic, 3),
                "market_data_unavailable": (
                    not core_quote_available or not provenance_confirmed or not requested_mode_compatible
                ),
                "subscription_missing": diagnostics.subscription_missing,
            }
        )
        self._record_quote_diagnostics(
            bucket,
            market_data_mode=market_data_mode,
            core_quote_available=core_quote_available,
            provenance_confirmed=provenance_confirmed,
            requested_mode_compatible=requested_mode_compatible,
            outcome_reason=outcome_reason,
        )
        return payload

    def _record_quote_diagnostics(
        self,
        bucket: _MarketDataRequest,
        *,
        market_data_mode: str,
        core_quote_available: bool,
        provenance_confirmed: bool,
        requested_mode_compatible: bool,
        outcome_reason: str,
    ) -> None:
        snapshot = {
            "requested_market_data_type": bucket.requested_market_data_type,
            "market_data_type_callbacks": [
                {"type": item, "mode": _market_mode_name(item)} for item in bucket.market_data_type_callbacks
            ],
            "quote_provenance": market_data_mode,
            "provenance_confirmed": provenance_confirmed,
            "requested_mode_compatible": requested_mode_compatible,
            "core_quote_available": core_quote_available,
            "final_quote_usable": (
                core_quote_available and provenance_confirmed and requested_mode_compatible
            ),
            "reason_code": outcome_reason,
            "price_callbacks": {key: dict(value) for key, value in bucket.price_callbacks.items()},
            **_price_callback_summary(bucket),
            "elapsed_request_seconds": round(time.monotonic() - bucket.started_monotonic, 3),
            "timeout_stage": bucket.timeout_stage,
            "errors": [_error_to_dict(error) for error in bucket.errors],
        }
        with self._requests_lock:
            self._last_quote_diagnostics = snapshot

    def _append_error(self, req_id: int, error: RuntimeErrorInfo) -> None:
        with self._requests_lock:
            for registry in (
                self._matching_symbol_requests,
                self._contract_detail_requests,
                self._option_param_requests,
                self._market_data_requests,
            ):
                bucket = registry.get(req_id)
                if bucket is not None:
                    bucket.errors.append(error)
                    if error.code not in IGNORED_ERROR_CODES:
                        bucket.event.set()
                    return

    def _cancel_pending_requests(self, message: str) -> None:
        error = RuntimeErrorInfo(req_id=-1, code=0, message=message)
        with self._requests_lock:
            for registry in (
                self._matching_symbol_requests,
                self._contract_detail_requests,
                self._option_param_requests,
                self._market_data_requests,
            ):
                for bucket in registry.values():
                    bucket.errors.append(error)
                    bucket.event.set()

    def _handle_next_valid_id(self, order_id: int) -> None:
        with self._request_id_lock:
            self._next_request_id = order_id
        self._connected_event.set()
        self._lifecycle_status = "connected"

    def _handle_error(
        self,
        req_id: int,
        code: int,
        message: str,
        *,
        error_time: int | None = None,
        advanced_order_reject_present: bool = False,
    ) -> None:
        error = RuntimeErrorInfo(
            req_id=req_id,
            code=code,
            message=message,
            error_time=error_time,
            advanced_order_reject_present=advanced_order_reject_present,
        )
        with self._requests_lock:
            target = (
                self._informational_messages if code in FARM_STATUS_ERROR_CODES else self._diagnostic_errors
            )
            target.append(error)
            del target[:-100]
        if code in FARM_STATUS_ERROR_CODES:
            return
        if code not in IGNORED_ERROR_CODES or code in TRACKED_INFO_ERROR_CODES:
            self._append_error(req_id, error)
        if code in CONNECTION_ERROR_CODES:
            self._connection_error = error
            self._lifecycle_status = "failed"
            self._connected_event.set()
            self._cancel_pending_requests(message)
        elif code in CONNECTION_RECOVERY_CODES:
            self._connection_error = None
            if self.is_connected():
                self._lifecycle_status = "connected"

    def _handle_connection_closed(self) -> None:
        if self._lifecycle_status in {"closing", "disconnected"}:
            return
        message = "The TWS / IB Gateway connection closed."
        error = RuntimeErrorInfo(req_id=-1, code=0, message=message)
        self._connection_error = error
        self._lifecycle_status = "failed"
        self._connected_event.set()
        self._cancel_pending_requests(message)

    def _handle_symbol_samples(self, req_id: int, descriptions: list[Any]) -> None:
        items: list[dict[str, Any]] = []
        for description in descriptions:
            contract = getattr(description, "contract", None)
            if contract is None:
                continue
            payload = _contract_to_dict(contract)
            payload["derivative_sec_types"] = sorted(getattr(description, "derivativeSecTypes", []) or [])
            items.append(payload)
        with self._requests_lock:
            bucket = self._matching_symbol_requests.get(req_id)
            if bucket is None:
                return
            bucket.items.extend(items)
            bucket.note_update()
            bucket.event.set()

    def _handle_contract_details(self, req_id: int, details: Any) -> None:
        with self._requests_lock:
            bucket = self._contract_detail_requests.get(req_id)
            if bucket is None:
                return
            bucket.items.append(_contract_details_to_dict(details))
            bucket.note_update()

    def _handle_contract_details_end(self, req_id: int) -> None:
        with self._requests_lock:
            bucket = self._contract_detail_requests.get(req_id)
            if bucket is not None:
                bucket.event.set()

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
        with self._requests_lock:
            bucket = self._option_param_requests.get(req_id)
            if bucket is None:
                return
            bucket.items.append(
                {
                    "exchange": exchange,
                    "underlying_con_id": underlying_con_id,
                    "trading_class": trading_class,
                    "multiplier": multiplier,
                    "expirations": sorted(expirations),
                    "strikes": sorted(float(strike) for strike in strikes if strike is not None),
                }
            )
            bucket.note_update()

    def _handle_option_param_end(self, req_id: int) -> None:
        with self._requests_lock:
            bucket = self._option_param_requests.get(req_id)
            if bucket is not None:
                bucket.event.set()

    def _handle_market_data_type(self, req_id: int, market_data_type: int) -> None:
        with self._requests_lock:
            self._market_data_type_callbacks.append(market_data_type)
            del self._market_data_type_callbacks[:-100]
            bucket = self._market_data_requests.get(req_id)
            if bucket is None:
                return
            bucket.market_data_type_callbacks.append(market_data_type)
            bucket.payload["market_data_type"] = market_data_type
            bucket.note_update()

    def _handle_tick_price(self, req_id: int, tick_type: int, price: float) -> None:
        value = _clean_price(price)
        tick_name = _tick_type_name(tick_type)
        with self._requests_lock:
            bucket = self._market_data_requests.get(req_id)
            if bucket is None:
                return
            field_name = _price_callback_field(tick_name)
            if field_name is not None:
                stats = bucket.price_callbacks.setdefault(
                    field_name,
                    {"received": 0, "usable": 0, "unavailable": 0},
                )
                stats["received"] += 1
                stats["usable" if value is not None else "unavailable"] += 1
            if value is None:
                bucket.note_update()
                return
            if field_name == "bid":
                bucket.payload["bid"] = value
            elif field_name == "ask":
                bucket.payload["ask"] = value
            elif field_name == "last":
                bucket.payload["last"] = value
            elif field_name == "high":
                bucket.payload["high"] = value
            elif field_name == "low":
                bucket.payload["low"] = value
            elif field_name == "close":
                bucket.payload["close"] = value
            elif field_name == "open":
                bucket.payload["open"] = value
            bucket.note_update()

    def _handle_tick_size(self, req_id: int, tick_type: int, size: Decimal | int) -> None:
        value = _clean_size(size)
        if value is None:
            return
        with self._requests_lock:
            bucket = self._market_data_requests.get(req_id)
            if bucket is None:
                return
            tick_name = _tick_type_name(tick_type)
            contract_right = getattr(bucket.contract, "right", "")
            if tick_name in {"VOLUME", "DELAYED_VOLUME"}:
                bucket.payload["volume"] = value
            elif tick_name == "OPEN_INTEREST":
                bucket.payload["open_interest"] = value
            elif tick_name == "OPTION_CALL_OPEN_INTEREST":
                bucket.payload["call_open_interest"] = value
                if contract_right == "C":
                    bucket.payload["open_interest"] = value
            elif tick_name == "OPTION_PUT_OPEN_INTEREST":
                bucket.payload["put_open_interest"] = value
                if contract_right == "P":
                    bucket.payload["open_interest"] = value
            elif tick_name == "OPTION_CALL_VOLUME":
                bucket.payload["call_volume"] = value
                if contract_right == "C":
                    bucket.payload["volume"] = value
            elif tick_name == "OPTION_PUT_VOLUME":
                bucket.payload["put_volume"] = value
                if contract_right == "P":
                    bucket.payload["volume"] = value
            bucket.note_update()

    def _handle_tick_string(self, req_id: int, tick_type: int, value: str) -> None:
        with self._requests_lock:
            bucket = self._market_data_requests.get(req_id)
            if bucket is None:
                return
            tick_name = _tick_type_name(tick_type)
            if tick_name == "LAST_TIMESTAMP":
                bucket.payload["last_timestamp"] = value
            elif tick_name == "RT_VOLUME":
                bucket.payload["rt_volume"] = value
            bucket.note_update()

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
        with self._requests_lock:
            bucket = self._market_data_requests.get(req_id)
            if bucket is None:
                return

            tick_name = _tick_type_name(tick_type)
            priorities = {
                "BID_OPTION_COMPUTATION": 0,
                "ASK_OPTION_COMPUTATION": 0,
                "LAST_OPTION_COMPUTATION": 1,
                "MODEL_OPTION": 2,
                "DELAYED_MODEL_OPTION": 2,
            }
            priority = priorities.get(tick_name)
            if priority is None or priority < bucket.option_computation_priority:
                return

            if priority > bucket.option_computation_priority:
                for key in (
                    "broker_implied_vol",
                    "broker_model_price",
                    "broker_underlying_price",
                    "broker_pv_dividend",
                    "broker_greeks",
                ):
                    bucket.payload.pop(key, None)
                bucket.option_computation_priority = priority

            broker_greeks = bucket.payload.setdefault("broker_greeks", {})
            clean_iv = _clean_broker_implied_vol(implied_vol)
            if clean_iv is not None:
                bucket.payload["broker_implied_vol"] = clean_iv
            clean_option_price = _clean_price(option_price)
            if clean_option_price is not None:
                bucket.payload["broker_model_price"] = clean_option_price
            clean_underlying_price = _clean_price(underlying_price)
            if clean_underlying_price is not None:
                bucket.payload["broker_underlying_price"] = clean_underlying_price
            clean_pv_dividend = _clean_price(pv_dividend)
            if clean_pv_dividend is not None:
                bucket.payload["broker_pv_dividend"] = clean_pv_dividend

            for key, raw_value in {
                "delta": delta,
                "gamma": gamma,
                "theta": theta,
                "vega": vega,
            }.items():
                clean_value = _clean_broker_greek(raw_value)
                if clean_value is not None:
                    broker_greeks[key] = clean_value

            bucket.note_update()
