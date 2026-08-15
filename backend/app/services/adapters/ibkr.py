from __future__ import annotations

import math
import threading
from datetime import date, datetime, timezone
from typing import Any

from app.services.adapters.base import AdapterUnavailableError
from app.services.adapters.ibkr_compat import require_compatible_ibapi
from app.services.adapters.ibkr_contracts import (
    build_contract_id,
    build_option_contract,
    build_underlying_contract,
    parse_contract_id,
)
from app.services.adapters.ibkr_runtime import (
    DELAYED_FROZEN_MARKET_DATA_TYPE,
    LIVE_MARKET_DATA_TYPE,
    IBKRRuntime,
)
from app.services.cache import KeyedLockPool, TTLCache

PREFERRED_OPTION_EXCHANGES = ("SMART", "CBOE", "BOX", "AMEX")
OPTIONAL_OPTION_GENERIC_TICKS = "100,101"


class IBKRAdapter:
    mode = "ibkr"

    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        use_delayed: bool = True,
        include_optional_option_stats: bool = False,
        contract_cache_ttl_seconds: float = 1800.0,
        quote_cache_ttl_seconds: float = 8.0,
        option_quote_wait_seconds: float = 1.2,
        default_chain_strike_count: int = 10,
        default_chain_spot_window_pct: float = 0.15,
    ) -> None:
        self._compatibility = require_compatible_ibapi()
        self.host = host
        self.port = port
        self.client_id = client_id
        self.use_delayed = use_delayed
        self.include_optional_option_stats = include_optional_option_stats
        self.option_quote_wait_seconds = option_quote_wait_seconds
        self.default_chain_strike_count = default_chain_strike_count
        self.default_chain_spot_window_pct = default_chain_spot_window_pct
        self._runtime: IBKRRuntime | None = None
        self._last_diagnostics: dict[str, Any] = {}
        self._runtime_lock = threading.Lock()
        self._qualified_underlying_cache = TTLCache(ttl_seconds=contract_cache_ttl_seconds)
        self._option_params_cache = TTLCache(ttl_seconds=contract_cache_ttl_seconds)
        self._option_quote_cache = TTLCache(ttl_seconds=quote_cache_ttl_seconds)
        self._cache_locks = KeyedLockPool()

    def status(self) -> str:
        runtime = self._runtime
        if runtime is None:
            return "ready"
        if runtime.is_connected():
            return "connected_delayed_frozen_capable" if self.use_delayed else "connected_live"
        return getattr(runtime, "lifecycle_status", "disconnected")

    def search_underlyings(self, query: str) -> list[dict[str, object]]:
        runtime = self._runtime_instance()
        matches = runtime.matching_symbols(query)
        filtered = [
            item
            for item in matches
            if item.get("sec_type") == "STK"
            and item.get("currency") == "USD"
            and "OPT" in item.get("derivative_sec_types", [])
        ]
        filtered.sort(key=lambda item: (item.get("symbol") != query.upper(), item.get("exchange") != "SMART"))
        return [
            {
                "symbol": item["symbol"],
                "description": item.get("symbol"),
                "exchange": item.get("primary_exchange") or item.get("exchange") or "SMART",
                "currency": item.get("currency", "USD"),
                "market_data_mode": "unconfirmed",
                "con_id": item.get("con_id"),
            }
            for item in filtered
        ]

    def get_underlying_summary(self, symbol: str) -> dict[str, object]:
        runtime = self._runtime_instance()
        qualified = self._qualified_underlying(runtime, symbol)
        quote = runtime.quote_contract(
            build_underlying_contract(qualified),
            generic_tick_list="",
            wait_seconds=self.option_quote_wait_seconds,
            allow_partial=True,
        )
        bid = _number(quote.get("bid"))
        ask = _number(quote.get("ask"))
        last = _number(quote.get("last"))
        close = _number(quote.get("close"))
        open_price = _number(quote.get("open"))

        market_data_mode = str(quote.get("market_data_mode", "unconfirmed"))
        crossed_market = bid is not None and ask is not None and bid > ask
        if crossed_market:
            raise AdapterUnavailableError(
                f"IBKR returned a crossed market for {symbol.upper()}; no usable reference quote."
            )

        mid = (bid + ask) / 2.0 if bid is not None and ask is not None else None
        spot = _first_usable_number(last, mid, close, open_price)
        if market_data_mode == "unconfirmed" or bool(quote.get("market_data_unavailable", False)):
            spot = None
        if spot is None:
            raise AdapterUnavailableError(f"No usable market data received for {symbol.upper()}.")

        previous_close = _first_usable_number(close, spot) or spot
        change = spot - previous_close
        return {
            "symbol": qualified["symbol"],
            "description": qualified.get("long_name") or qualified["symbol"],
            "exchange": qualified.get("primary_exchange") or qualified.get("exchange") or "SMART",
            "currency": qualified.get("currency", "USD"),
            "spot": spot,
            "previous_close": previous_close,
            "change": change,
            "change_percent": (change / previous_close * 100.0) if previous_close else 0.0,
            "timestamp": quote.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "exchange_timestamp": quote.get("exchange_timestamp"),
            "received_at": quote.get("received_at"),
            "market_data_mode": market_data_mode,
            "is_delayed": bool(quote.get("is_delayed", False)),
            "market_data_unavailable": bool(quote.get("market_data_unavailable", False)),
            "subscription_missing": bool(quote.get("subscription_missing", False)),
            "con_id": qualified.get("con_id"),
        }

    def get_option_chain(self, symbol: str, expiration: str | date | None = None) -> dict[str, object]:
        runtime = self._runtime_instance()
        qualified = self._qualified_underlying(runtime, symbol)
        underlying = self.get_underlying_summary(symbol)
        params = self._option_chain_params(runtime, symbol, int(qualified["con_id"]))
        requested_expiration = (
            expiration
            if isinstance(expiration, date)
            else date.fromisoformat(expiration)
            if expiration
            else None
        )
        selected_params = _select_option_params(params, requested_expiration=requested_expiration)
        expirations = _sorted_expirations(selected_params["expirations"])
        selected_expiration = _select_expiration(expirations, expiration)
        strikes = _select_strikes(
            selected_params["strikes"],
            float(underlying["spot"]),
            max_count=self.default_chain_strike_count,
            spot_window_pct=self.default_chain_spot_window_pct,
        )

        option_quotes: list[dict[str, object]] = []
        pending_contracts: list[tuple[str, Any, dict[str, object]]] = []
        for strike in strikes:
            for right in ("C", "P"):
                contract = build_option_contract(
                    symbol=symbol,
                    expiration=selected_expiration,
                    strike=strike,
                    right=right,
                    exchange=str(selected_params["exchange"]),
                    currency=str(qualified.get("currency", "USD")),
                    multiplier=str(selected_params["multiplier"]),
                    trading_class=str(selected_params["trading_class"]),
                    underlying_con_id=int(qualified["con_id"]),
                )
                contract_id = build_contract_id(symbol, selected_expiration, strike, right)
                cached_quote = self._option_quote_cache.get((contract_id,))
                if cached_quote is not None:
                    option_quotes.append(cached_quote)
                    continue
                pending_contracts.append(
                    (
                        contract_id,
                        contract,
                        self._option_payload_base(
                            symbol=symbol,
                            expiration=selected_expiration,
                            strike=strike,
                            right=right,
                            selected_params=selected_params,
                            qualified=qualified,
                        ),
                    )
                )

        if pending_contracts:
            raw_quotes_by_contract = runtime.quote_contracts(
                [(contract_id, contract) for contract_id, contract, _ in pending_contracts],
                generic_tick_list=self._option_generic_ticks(),
                wait_seconds=self.option_quote_wait_seconds,
                allow_partial=True,
            )
            for contract_id, contract, payload_base in pending_contracts:
                raw_quote = raw_quotes_by_contract.get(contract_id, {})
                payload = {
                    **payload_base,
                    "con_id": raw_quote.get("con_id") or getattr(contract, "conId", None),
                    "local_symbol": raw_quote.get("local_symbol") or getattr(contract, "localSymbol", None),
                    **raw_quote,
                }
                self._option_quote_cache.set((contract_id,), payload)
                option_quotes.append(payload)

        return {
            "symbol": symbol.upper(),
            "underlying": underlying,
            "expirations": [item.isoformat() for item in expirations],
            "selected_expiration": selected_expiration.isoformat(),
            "options": option_quotes,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "market_data_mode": underlying["market_data_mode"],
        }

    def get_option_quote(self, contract_id: str) -> dict[str, object]:
        cached = self._option_quote_cache.get((contract_id,))
        if cached is not None:
            return cached

        runtime = self._runtime_instance()
        parsed = parse_contract_id(contract_id)
        qualified = self._qualified_underlying(runtime, parsed.symbol)
        params = self._option_chain_params(runtime, parsed.symbol, int(qualified["con_id"]))
        selected_params = _select_option_params(params, requested_expiration=parsed.expiration)
        contract = build_option_contract(
            symbol=parsed.symbol,
            expiration=parsed.expiration,
            strike=parsed.strike,
            right=parsed.right,
            exchange=str(selected_params["exchange"]),
            currency=str(qualified.get("currency", "USD")),
            multiplier=str(selected_params["multiplier"]),
            trading_class=str(selected_params["trading_class"]),
            underlying_con_id=int(qualified["con_id"]),
        )
        raw_quote = runtime.quote_contract(
            contract,
            generic_tick_list=self._option_generic_ticks(),
            wait_seconds=self.option_quote_wait_seconds,
            allow_partial=True,
        )
        payload = {
            **self._option_payload_base(
                symbol=parsed.symbol,
                expiration=parsed.expiration,
                strike=parsed.strike,
                right=parsed.right,
                selected_params=selected_params,
                qualified=qualified,
            ),
            "con_id": raw_quote.get("con_id") or getattr(contract, "conId", None),
            "local_symbol": raw_quote.get("local_symbol") or getattr(contract, "localSymbol", None),
            **raw_quote,
        }
        self._option_quote_cache.set((contract_id,), payload)
        return payload

    def _option_generic_ticks(self) -> str:
        if not self.include_optional_option_stats:
            return ""
        return OPTIONAL_OPTION_GENERIC_TICKS

    def _runtime_instance(self) -> IBKRRuntime:
        if self._runtime is None:
            with self._runtime_lock:
                if self._runtime is None:
                    self._runtime = IBKRRuntime(
                        host=self.host,
                        port=self.port,
                        client_id=self.client_id,
                        use_delayed=self.use_delayed,
                        compatibility=self._compatibility,
                    )
        return self._runtime

    def close(self) -> None:
        with self._runtime_lock:
            runtime = self._runtime
            self._runtime = None
        if runtime is not None:
            try:
                self._last_diagnostics = runtime.diagnostics_snapshot()
            finally:
                runtime.disconnect()

    def diagnostics_snapshot(self) -> dict[str, Any]:
        runtime = self._runtime
        if runtime is not None:
            return runtime.diagnostics_snapshot()
        if self._last_diagnostics:
            return dict(self._last_diagnostics)
        requested_type = DELAYED_FROZEN_MARKET_DATA_TYPE if self.use_delayed else LIVE_MARKET_DATA_TYPE
        return {
            **self._compatibility.diagnostics(),
            "lifecycle_status": "not_initialized",
            "api_handshake_succeeded": False,
            "tws_server_version": None,
            "requested_market_data_type": requested_type,
            "requested_market_data_mode": ("delayed_frozen_capable" if self.use_delayed else "live_only"),
            "market_data_type_callbacks": [],
            "request_errors": [],
            "relevant_errors": [],
            "informational_messages": [],
            "last_quote": {},
        }

    def _qualified_underlying(self, runtime: IBKRRuntime, symbol: str) -> dict[str, object]:
        cache_key = (symbol.upper(),)
        cached = self._qualified_underlying_cache.get(cache_key)
        if cached is not None:
            return cached
        with self._cache_locks.hold(("qualified-underlying", *cache_key)):
            cached = self._qualified_underlying_cache.get(cache_key)
            if cached is not None:
                return cached
            qualified = runtime.qualify_underlying(symbol)
            self._qualified_underlying_cache.set(cache_key, qualified)
            return qualified

    def _option_chain_params(
        self,
        runtime: IBKRRuntime,
        symbol: str,
        underlying_con_id: int,
    ) -> list[dict[str, object]]:
        cache_key = (symbol.upper(), underlying_con_id)
        cached = self._option_params_cache.get(cache_key)
        if cached is not None:
            return cached
        with self._cache_locks.hold(("option-chain-params", *cache_key)):
            cached = self._option_params_cache.get(cache_key)
            if cached is not None:
                return cached
            params = runtime.option_chain_params(symbol, underlying_con_id)
            self._option_params_cache.set(cache_key, params)
            return params

    @staticmethod
    def _option_payload_base(
        *,
        symbol: str,
        expiration: date,
        strike: float,
        right: str,
        selected_params: dict[str, Any],
        qualified: dict[str, object],
    ) -> dict[str, object]:
        return {
            "contract_id": build_contract_id(symbol, expiration, strike, right),
            "symbol": symbol.upper(),
            "exchange": selected_params["exchange"],
            "currency": qualified.get("currency", "USD"),
            "expiration": expiration.isoformat(),
            "strike": strike,
            "right": "call" if right == "C" else "put",
            "multiplier": int(selected_params["multiplier"]),
            "trading_class": selected_params["trading_class"],
        }


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _first_usable_number(*values: Any) -> float | None:
    for value in values:
        numeric = _number(value)
        if numeric is not None and numeric > 0.0:
            return numeric
    return None


def _sorted_expirations(expirations: list[str]) -> list[date]:
    return sorted(date.fromisoformat(_normalize_expiration(item)) for item in expirations)


def _normalize_expiration(expiration: str) -> str:
    if "-" in expiration:
        return expiration
    return f"{expiration[0:4]}-{expiration[4:6]}-{expiration[6:8]}"


def _select_expiration(expirations: list[date], requested: str | date | None) -> date:
    if requested is None:
        if not expirations:
            raise AdapterUnavailableError("No valid expirations were returned by IBKR.")
        return expirations[0]

    requested_date = requested if isinstance(requested, date) else date.fromisoformat(str(requested))
    for expiration in expirations:
        if expiration == requested_date:
            return expiration
    raise AdapterUnavailableError(f"Requested expiration {requested_date.isoformat()} is not available.")


def _select_option_params(
    params: list[dict[str, Any]],
    requested_expiration: date | None = None,
) -> dict[str, Any]:
    if not params:
        raise AdapterUnavailableError("No option chain parameters were returned by IBKR.")

    candidates = [item for item in params if str(item.get("multiplier", "")) == "100"]
    if not candidates:
        candidates = params

    if requested_expiration is not None:
        requested_text = requested_expiration.strftime("%Y%m%d")
        candidates = [
            item
            for item in candidates
            if requested_text in item.get("expirations", [])
            or requested_expiration.isoformat() in item.get("expirations", [])
        ] or candidates

    candidates.sort(
        key=lambda item: (
            item.get("exchange") not in PREFERRED_OPTION_EXCHANGES,
            len(item.get("expirations", [])) == 0,
            len(item.get("strikes", [])) == 0,
        )
    )
    return candidates[0]


def _select_strikes(
    strikes: list[float],
    spot: float,
    *,
    max_count: int = 10,
    spot_window_pct: float = 0.15,
) -> list[float]:
    valid_strikes = sorted({float(strike) for strike in strikes if strike is not None and strike > 0.0})
    if not valid_strikes:
        raise AdapterUnavailableError("No valid strikes were returned by IBKR.")

    lower = spot * max(0.0, 1.0 - max(spot_window_pct, 0.0))
    upper = spot * (1.0 + max(spot_window_pct, 0.0))
    bounded = [strike for strike in valid_strikes if lower <= strike <= upper]
    source = bounded if len(bounded) >= max_count else valid_strikes
    nearest = sorted(source, key=lambda strike: abs(strike - spot))[:max_count]
    return sorted(nearest)
