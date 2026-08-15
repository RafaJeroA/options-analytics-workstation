from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.services.adapters.base import AdapterUnavailableError

try:  # pragma: no cover - imported only when ibapi is present
    from ibapi.contract import Contract

    IBAPI_AVAILABLE = True
except ImportError:  # pragma: no cover
    Contract = object  # type: ignore[assignment]
    IBAPI_AVAILABLE = False


CONTRACT_ID_PATTERN = re.compile(
    r"^(?P<symbol>[A-Z0-9._]+)-(?P<expiration>\d{4}-\d{2}-\d{2})-(?P<strike>\d+(?:\.\d+)?)-(?P<right>[CP])$"
)


@dataclass(frozen=True, slots=True)
class ParsedOptionContractId:
    symbol: str
    expiration: date
    strike: float
    right: str


def build_contract_id(symbol: str, expiration: date, strike: float, right: str) -> str:
    normalized_right = _normalize_right(right)
    return f"{symbol.upper()}-{expiration.isoformat()}-{strike:.2f}-{normalized_right}"


def parse_contract_id(contract_id: str) -> ParsedOptionContractId:
    match = CONTRACT_ID_PATTERN.match(contract_id.upper())
    if match is None:
        raise AdapterUnavailableError(f"Unsupported option contract identifier: {contract_id}")
    return ParsedOptionContractId(
        symbol=match.group("symbol"),
        expiration=date.fromisoformat(match.group("expiration")),
        strike=float(match.group("strike")),
        right=match.group("right"),
    )


def build_option_contract(
    symbol: str,
    expiration: date,
    strike: float,
    right: str,
    exchange: str,
    currency: str,
    multiplier: str,
    trading_class: str,
    underlying_con_id: int | None = None,
) -> Any:
    if not IBAPI_AVAILABLE:
        raise AdapterUnavailableError("ibapi is required to build live IBKR contracts.")

    contract = Contract()
    contract.symbol = symbol.upper()
    contract.secType = "OPT"
    contract.exchange = exchange
    contract.currency = currency
    contract.lastTradeDateOrContractMonth = expiration.strftime("%Y%m%d")
    contract.strike = float(strike)
    contract.right = _normalize_right(right)
    contract.multiplier = multiplier
    contract.tradingClass = trading_class
    if underlying_con_id:
        contract.underConId = underlying_con_id
    return contract


def build_underlying_contract(qualified: dict[str, Any]) -> Any:
    if not IBAPI_AVAILABLE:
        raise AdapterUnavailableError("ibapi is required to build live IBKR contracts.")

    contract = Contract()
    contract.conId = int(qualified["con_id"])
    contract.symbol = str(qualified["symbol"])
    contract.secType = str(qualified.get("sec_type", "STK"))
    contract.exchange = str(qualified.get("exchange", "SMART"))
    contract.primaryExchange = str(qualified.get("primary_exchange", ""))
    contract.currency = str(qualified.get("currency", "USD"))
    return contract


def build_cash_contract(base_currency: str, quote_currency: str) -> Any:
    if not IBAPI_AVAILABLE:
        raise AdapterUnavailableError("ibapi is required to build live IBKR contracts.")

    contract = Contract()
    contract.symbol = base_currency.upper()
    contract.secType = "CASH"
    contract.exchange = "IDEALPRO"
    contract.currency = quote_currency.upper()
    return contract


def _normalize_right(right: str) -> str:
    normalized = right.upper()
    if normalized in {"CALL", "C"}:
        return "C"
    if normalized in {"PUT", "P"}:
        return "P"
    raise AdapterUnavailableError(f"Unsupported option right: {right}")
