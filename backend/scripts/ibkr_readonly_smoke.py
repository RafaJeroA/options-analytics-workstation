from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.services.adapters.base import (  # noqa: E402
    AdapterUnavailableError,
    AmbiguousContractError,
    UnknownSymbolError,
)
from app.services.adapters.ibkr import IBKRAdapter  # noqa: E402
from app.services.adapters.ibkr_compat import IBAPICompatibilityError  # noqa: E402
from app.services.adapters.ibkr_contracts import build_cash_contract  # noqa: E402
from app.services.adapters.ibkr_runtime import IBKRRuntime  # noqa: E402

ENABLE_VALUE = "I_UNDERSTAND_READ_ONLY"
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9._]{1,12}$")
WINDOWS_PATH_PATTERN = re.compile(r"(?i)(?:[A-Z]:\\|\\\\)[^\s\"']+")
UNIX_PATH_PATTERN = re.compile(r"(?<![:\w])/(?:[^/\s]+/)*[^/\s]+")
ACCOUNT_PATTERN = re.compile(r"\b(?:DU|U|F|DF|FA)\d{5,}\b", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"\b[^\s@]+@[^\s@]+\b")
SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(account(?:_id)?|username|user|client[_ ]?id|password|token|secret|host)"
    r"(?:\s*[:=]\s*|\s+)\S+"
)


class ReadOnlySmokeFailure(RuntimeError):
    def __init__(self, stage: str, error: Exception, diagnostics: dict[str, object]) -> None:
        super().__init__(str(error))
        self.stage = stage
        self.error = error
        self.error_type = type(error).__name__
        self.diagnostics = diagnostics

    def result(self) -> dict[str, object]:
        last_quote = dict(self.diagnostics.get("last_quote") or {})
        timeout_stage = last_quote.get("timeout_stage")
        if timeout_stage is None and "timed out" in str(self).lower():
            timeout_stage = self.stage
        return {
            "status": "failed",
            "reason_code": _failure_reason_code(self.error, self.diagnostics),
            "error_type": self.error_type,
            "message": _sanitize_message(str(self)),
            "failed_stage": self.stage,
            "timeout_stage": timeout_stage,
            "api_handshake_succeeded": bool(self.diagnostics.get("api_handshake_succeeded", False)),
            "client_api_package_version": self.diagnostics.get("client_api_package_version"),
            "minimum_client_api_version": self.diagnostics.get("minimum_client_api_version"),
            "tws_server_version": self.diagnostics.get("tws_server_version"),
            "requested_market_data_type": self.diagnostics.get("requested_market_data_type"),
            "requested_market_data_mode": self.diagnostics.get("requested_market_data_mode", "unreported"),
            "market_data_type_callbacks": self.diagnostics.get("market_data_type_callbacks", []),
            "request_errors": self.diagnostics.get("request_errors", []),
            "informational_messages": self.diagnostics.get("informational_messages", []),
            "ibkr_errors": self.diagnostics.get("request_errors", []),
            "price_callbacks": last_quote.get("price_callbacks", {}),
            "bid_received": bool(last_quote.get("bid_received", False)),
            "ask_received": bool(last_quote.get("ask_received", False)),
            "last_received": bool(last_quote.get("last_received", False)),
            "bid_unavailable": bool(last_quote.get("bid_unavailable", False)),
            "ask_unavailable": bool(last_quote.get("ask_unavailable", False)),
            "last_unavailable": bool(last_quote.get("last_unavailable", False)),
            "elapsed_request_seconds": last_quote.get("elapsed_request_seconds"),
            "final_quote_usable": bool(last_quote.get("final_quote_usable", False)),
            "quote_provenance": last_quote.get("quote_provenance", "unconfirmed"),
            "provenance_confirmed": bool(last_quote.get("provenance_confirmed", False)),
            "requested_mode_compatible": bool(last_quote.get("requested_mode_compatible", False)),
        }


def _sanitize_message(message: object) -> str:
    sanitized = " ".join(str(message).split())
    sanitized = WINDOWS_PATH_PATTERN.sub("<redacted-path>", sanitized)
    sanitized = UNIX_PATH_PATTERN.sub("<redacted-path>", sanitized)
    sanitized = ACCOUNT_PATTERN.sub("<redacted-account>", sanitized)
    sanitized = EMAIL_PATTERN.sub("<redacted-email>", sanitized)
    sanitized = SENSITIVE_ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}=<redacted>", sanitized)
    return sanitized[:320]


def _sanitize_diagnostics(diagnostics: object) -> dict[str, object]:
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    last_quote = diagnostics.get("last_quote")
    if not isinstance(last_quote, dict):
        last_quote = {}

    def sanitized_errors(value: object) -> list[dict[str, object]]:
        if not isinstance(value, list):
            return []
        result: list[dict[str, object]] = []
        for item in value[-12:]:
            if not isinstance(item, dict):
                continue
            result.append(
                {
                    "req_id": item.get("req_id"),
                    "error_time": item.get("error_time"),
                    "code": item.get("code"),
                    "message": _sanitize_message(item.get("message", "")),
                    "advanced_order_reject_present": bool(item.get("advanced_order_reject_present", False)),
                }
            )
        return result

    return {
        "lifecycle_status": diagnostics.get("lifecycle_status", "unreported"),
        "api_handshake_succeeded": bool(diagnostics.get("api_handshake_succeeded", False)),
        "client_api_package_version": diagnostics.get("client_api_package_version"),
        "minimum_client_api_version": diagnostics.get("minimum_client_api_version"),
        "client_api_compatibility_reason": diagnostics.get("client_api_compatibility_reason"),
        "tws_server_version": diagnostics.get("tws_server_version"),
        "requested_market_data_type": diagnostics.get("requested_market_data_type"),
        "requested_market_data_mode": diagnostics.get("requested_market_data_mode", "unreported"),
        "market_data_type_callbacks": list(
            diagnostics.get("market_data_type_callbacks", [])
            if isinstance(diagnostics.get("market_data_type_callbacks"), list)
            else []
        )[-20:],
        "request_errors": sanitized_errors(
            diagnostics.get("request_errors", diagnostics.get("relevant_errors"))
        ),
        "relevant_errors": sanitized_errors(
            diagnostics.get("request_errors", diagnostics.get("relevant_errors"))
        ),
        "informational_messages": sanitized_errors(diagnostics.get("informational_messages")),
        "last_quote": {
            "market_data_type_callbacks": list(
                last_quote.get("market_data_type_callbacks", [])
                if isinstance(last_quote.get("market_data_type_callbacks"), list)
                else []
            )[-20:],
            "quote_provenance": last_quote.get("quote_provenance", "unconfirmed"),
            "provenance_confirmed": bool(last_quote.get("provenance_confirmed", False)),
            "requested_mode_compatible": bool(last_quote.get("requested_mode_compatible", False)),
            "core_quote_available": bool(last_quote.get("core_quote_available", False)),
            "final_quote_usable": bool(last_quote.get("final_quote_usable", False)),
            "reason_code": last_quote.get("reason_code"),
            "bid_received": bool(last_quote.get("bid_received", False)),
            "ask_received": bool(last_quote.get("ask_received", False)),
            "last_received": bool(last_quote.get("last_received", False)),
            "bid_unavailable": bool(last_quote.get("bid_unavailable", False)),
            "ask_unavailable": bool(last_quote.get("ask_unavailable", False)),
            "last_unavailable": bool(last_quote.get("last_unavailable", False)),
            "elapsed_request_seconds": last_quote.get("elapsed_request_seconds"),
            "price_callbacks": (
                last_quote.get("price_callbacks", {})
                if isinstance(last_quote.get("price_callbacks"), dict)
                else {}
            ),
            "timeout_stage": last_quote.get("timeout_stage"),
            "errors": sanitized_errors(last_quote.get("errors")),
        },
    }


def _failure_reason_code(error: Exception, diagnostics: dict[str, object]) -> str:
    explicit_reason = getattr(error, "reason_code", None)
    if isinstance(explicit_reason, str):
        return explicit_reason
    if isinstance(error, IBAPICompatibilityError):
        return "api_version_incompatible"
    if isinstance(error, UnknownSymbolError):
        return "contract_not_found"
    if isinstance(error, AmbiguousContractError):
        return "ambiguous_contract"

    message = str(error).lower()
    if "crossed market" in message:
        return "crossed_market"

    last_quote = diagnostics.get("last_quote")
    if isinstance(last_quote, dict) and isinstance(last_quote.get("reason_code"), str):
        return str(last_quote["reason_code"])

    request_errors = diagnostics.get("request_errors", diagnostics.get("relevant_errors", []))
    if isinstance(request_errors, list):
        error_codes = {item.get("code") for item in request_errors if isinstance(item, dict)}
        if error_codes & {354, 10089, 10090, 10167}:
            return "subscription_missing"
        if error_codes & {502, 504, 1100}:
            return "adapter_connection_failed"

    if "timed out" in message:
        return "request_timeout"
    return "adapter_connection_failed" if not diagnostics.get("api_handshake_succeeded") else "partial_quote"


def _adapter_diagnostics(adapter: Any) -> dict[str, object]:
    snapshot = getattr(adapter, "diagnostics_snapshot", None)
    if not callable(snapshot):
        return _sanitize_diagnostics({})
    try:
        return _sanitize_diagnostics(snapshot())
    except Exception:
        return _sanitize_diagnostics({})


def build_adapter(settings: Settings) -> IBKRAdapter:
    return IBKRAdapter(
        host=settings.ibkr_host,
        port=settings.ibkr_port,
        client_id=settings.ibkr_client_id,
        use_delayed=settings.ibkr_use_delayed,
        include_optional_option_stats=settings.ibkr_option_quote_include_optional_stats,
        option_quote_wait_seconds=settings.ibkr_chain_quote_wait_seconds,
        default_chain_strike_count=settings.ibkr_chain_default_strike_count,
        default_chain_spot_window_pct=settings.ibkr_chain_spot_window_pct,
    )


def run_readonly_checks(symbol: str, adapter: Any) -> dict[str, object]:
    """Run only symbol, contract-definition, and market-data requests."""
    normalized_symbol = symbol.strip().upper()
    if not SYMBOL_PATTERN.fullmatch(normalized_symbol):
        raise ValueError("Symbol must contain only letters, digits, period, or underscore.")

    stage = "symbol_search"
    try:
        matches = adapter.search_underlyings(normalized_symbol)
        stage = "underlying_quote"
        summary = adapter.get_underlying_summary(normalized_symbol)
        stage = "option_chain"
        chain = adapter.get_option_chain(normalized_symbol)
        stage = "result_aggregation"
        options = list(chain.get("options", []))
        modes = sorted({str(item.get("market_data_mode", "unreported")) for item in [summary, *options]})
        diagnostics = _adapter_diagnostics(adapter)
        last_quote = dict(diagnostics.get("last_quote") or {})
        return {
            "product": "Options Analytics Workstation",
            "adapter": "IBKR experimental read-only",
            "reason_code": last_quote.get("reason_code") or "success",
            "live_market_data_validated": False,
            "symbol": normalized_symbol,
            "matching_symbol_count": len(matches),
            "underlying_quote_received": summary.get("spot") is not None,
            "subscription_missing": bool(summary.get("subscription_missing", False)),
            "market_data_modes": modes,
            "expiration_count": len(chain.get("expirations", [])),
            "selected_expiration": chain.get("selected_expiration"),
            "option_quote_count": len(options),
            "partial_option_quote_count": sum(
                1 for item in options if item.get("bid") is None or item.get("ask") is None
            ),
            "api_handshake_succeeded": diagnostics.get("api_handshake_succeeded", False),
            "client_api_package_version": diagnostics.get("client_api_package_version"),
            "minimum_client_api_version": diagnostics.get("minimum_client_api_version"),
            "tws_server_version": diagnostics.get("tws_server_version"),
            "requested_market_data_type": diagnostics.get("requested_market_data_type"),
            "requested_market_data_mode": diagnostics.get("requested_market_data_mode"),
            "market_data_type_callbacks": diagnostics.get("market_data_type_callbacks", []),
            "request_errors": diagnostics.get("request_errors", []),
            "informational_messages": diagnostics.get("informational_messages", []),
            "bid_received": bool(last_quote.get("bid_received", False)),
            "ask_received": bool(last_quote.get("ask_received", False)),
            "last_received": bool(last_quote.get("last_received", False)),
            "bid_unavailable": bool(last_quote.get("bid_unavailable", False)),
            "ask_unavailable": bool(last_quote.get("ask_unavailable", False)),
            "last_unavailable": bool(last_quote.get("last_unavailable", False)),
            "elapsed_request_seconds": last_quote.get("elapsed_request_seconds"),
            "final_quote_usable": bool(last_quote.get("final_quote_usable", False)),
            "quote_provenance": last_quote.get("quote_provenance", "unconfirmed"),
        }
    except Exception as error:
        raise ReadOnlySmokeFailure(stage, error, _adapter_diagnostics(adapter)) from error
    finally:
        adapter.close()


def run_eurusd_readonly_check(settings: Settings) -> dict[str, object]:
    """Reproduce the known-good EUR/USD CASH IDEALPRO market-data path."""
    runtime = IBKRRuntime(
        host=settings.ibkr_host,
        port=settings.ibkr_port,
        client_id=settings.ibkr_client_id,
        use_delayed=settings.ibkr_use_delayed,
    )
    stage = "eurusd_market_data"
    try:
        quote = runtime.quote_contract(
            build_cash_contract("EUR", "USD"),
            wait_seconds=settings.ibkr_chain_quote_wait_seconds,
            allow_partial=True,
        )
        diagnostics = _adapter_diagnostics(runtime)
        last_quote = dict(diagnostics.get("last_quote") or {})
        if not bool(last_quote.get("final_quote_usable", False)):
            provenance = str(last_quote.get("quote_provenance", "unconfirmed"))
            if provenance in {"delayed", "delayed_frozen"}:
                message = f"{provenance} market-data mode confirmed, but no usable quote was delivered."
            else:
                message = "No usable EUR/USD quote was delivered."
            raise AdapterUnavailableError(message)
        return {
            "product": "Options Analytics Workstation",
            "adapter": "IBKR experimental read-only",
            "reason_code": last_quote.get("reason_code") or "success",
            "live_market_data_validated": False,
            "instrument": "EURUSD",
            "contract": "EUR/USD CASH IDEALPRO",
            "bid_received": quote.get("bid") is not None,
            "ask_received": quote.get("ask") is not None,
            "last_received": quote.get("last") is not None,
            "high_received": quote.get("high") is not None,
            "low_received": quote.get("low") is not None,
            "close_received": quote.get("close") is not None,
            "api_handshake_succeeded": diagnostics.get("api_handshake_succeeded", False),
            "client_api_package_version": diagnostics.get("client_api_package_version"),
            "minimum_client_api_version": diagnostics.get("minimum_client_api_version"),
            "tws_server_version": diagnostics.get("tws_server_version"),
            "requested_market_data_type": diagnostics.get("requested_market_data_type"),
            "requested_market_data_mode": diagnostics.get("requested_market_data_mode"),
            "market_data_type_callbacks": diagnostics.get("market_data_type_callbacks", []),
            "request_errors": diagnostics.get("request_errors", []),
            "informational_messages": diagnostics.get("informational_messages", []),
            "price_callbacks": last_quote.get("price_callbacks", {}),
            "elapsed_request_seconds": last_quote.get("elapsed_request_seconds"),
            "final_quote_usable": bool(last_quote.get("final_quote_usable", False)),
            "quote_provenance": last_quote.get("quote_provenance", "unconfirmed"),
        }
    except Exception as error:
        raise ReadOnlySmokeFailure(stage, error, _adapter_diagnostics(runtime)) from error
    finally:
        runtime.close()


def main() -> int:
    if os.environ.get("MODELLATOR_IBKR_READONLY_SMOKE") != ENABLE_VALUE:
        print(
            "IBKR smoke check disabled. Set MODELLATOR_IBKR_READONLY_SMOKE="
            f"{ENABLE_VALUE} to acknowledge the experimental read-only check.",
            file=sys.stderr,
        )
        return 2

    instrument = os.environ.get("MODELLATOR_IBKR_SMOKE_INSTRUMENT", "SPY").strip().upper()
    try:
        settings = Settings()
        if instrument == "EURUSD":
            result = run_eurusd_readonly_check(settings)
        else:
            symbol = os.environ.get("MODELLATOR_IBKR_SMOKE_SYMBOL", instrument or "SPY")
            result = run_readonly_checks(symbol, build_adapter(settings))
    except ReadOnlySmokeFailure as error:
        print(json.dumps(error.result(), indent=2, sort_keys=True))
        return 1
    except Exception as error:
        compatibility = getattr(error, "compatibility", None)
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason_code": getattr(error, "reason_code", "adapter_connection_failed"),
                    "error_type": type(error).__name__,
                    "message": _sanitize_message(error),
                    "client_api_package_version": getattr(compatibility, "package_version", None),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    print(json.dumps({"status": "completed", **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
