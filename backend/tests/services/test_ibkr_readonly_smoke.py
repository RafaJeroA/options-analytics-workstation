from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.ibkr_readonly_smoke as smoke_module
from app.core.config import Settings
from app.services.adapters.base import AdapterUnavailableError
from scripts.ibkr_readonly_smoke import (
    ReadOnlySmokeFailure,
    run_eurusd_readonly_check,
    run_readonly_checks,
)


class FakeReadOnlyAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.closed = False

    def search_underlyings(self, symbol: str):
        self.calls.append("search")
        return [{"symbol": symbol}]

    def get_underlying_summary(self, symbol: str):
        self.calls.append("summary")
        return {"symbol": symbol, "spot": 500.0, "market_data_mode": "delayed_frozen"}

    def get_option_chain(self, symbol: str):
        self.calls.append("chain")
        return {
            "expirations": ["2026-08-21"],
            "selected_expiration": "2026-08-21",
            "options": [
                {"bid": 5.0, "ask": 5.2, "market_data_mode": "delayed_frozen"},
                {"bid": None, "ask": 4.8, "market_data_mode": "delayed_frozen"},
            ],
        }

    def diagnostics_snapshot(self) -> dict[str, object]:
        return {
            "lifecycle_status": "connected",
            "api_handshake_succeeded": True,
            "requested_market_data_type": 4,
            "requested_market_data_mode": "delayed_frozen_capable",
            "market_data_type_callbacks": [{"type": 4, "mode": "delayed_frozen"}],
            "relevant_errors": [],
            "last_quote": {
                "quote_provenance": "delayed_frozen",
                "provenance_confirmed": True,
                "core_quote_available": True,
                "price_callbacks": {"bid": {"received": 1, "usable": 1, "unavailable": 0}},
            },
        }

    def close(self) -> None:
        self.closed = True


def test_readonly_smoke_aggregates_sanitized_market_metadata() -> None:
    adapter = FakeReadOnlyAdapter()

    result = run_readonly_checks("spy", adapter)

    assert adapter.calls == ["search", "summary", "chain"]
    assert adapter.closed is True
    assert result["symbol"] == "SPY"
    assert result["partial_option_quote_count"] == 1
    assert result["requested_market_data_type"] == 4
    assert result["market_data_modes"] == ["delayed_frozen"]
    assert result["quote_provenance"] == "delayed_frozen"
    assert result["reason_code"] == "success"
    assert "account" not in result
    assert "orders" not in result
    assert "positions" not in result


def test_readonly_smoke_failure_reports_sanitized_callback_diagnostics() -> None:
    class FailingAdapter(FakeReadOnlyAdapter):
        def get_underlying_summary(self, symbol: str):
            self.calls.append("summary")
            raise AdapterUnavailableError(
                r"No usable quote; C:\private\secret.txt account=U123456 password=hunter2"
            )

        def diagnostics_snapshot(self) -> dict[str, object]:
            unsafe_message = r"TWS error C:\private\secret.txt for U123456 host=127.0.0.1"
            return {
                "lifecycle_status": "connected",
                "api_handshake_succeeded": True,
                "requested_market_data_type": 4,
                "requested_market_data_mode": "delayed_frozen_capable",
                "market_data_type_callbacks": [{"type": 4, "mode": "delayed_frozen"}],
                "relevant_errors": [{"code": 354, "message": unsafe_message}],
                "last_quote": {
                    "market_data_type_callbacks": [{"type": 4, "mode": "delayed_frozen"}],
                    "quote_provenance": "delayed_frozen",
                    "provenance_confirmed": True,
                    "core_quote_available": False,
                    "price_callbacks": {
                        "bid": {"received": 1, "usable": 0, "unavailable": 1},
                        "ask": {"received": 1, "usable": 0, "unavailable": 1},
                        "last": {"received": 1, "usable": 0, "unavailable": 1},
                    },
                    "timeout_stage": "market_data_wait",
                    "errors": [{"code": 354, "message": unsafe_message}],
                },
            }

    adapter = FailingAdapter()

    with pytest.raises(ReadOnlySmokeFailure) as failure:
        run_readonly_checks("SPY", adapter)

    result = failure.value.result()
    serialized = json.dumps(result)
    assert adapter.closed is True
    assert result["failed_stage"] == "underlying_quote"
    assert result["reason_code"] == "subscription_missing"
    assert result["timeout_stage"] == "market_data_wait"
    assert result["api_handshake_succeeded"] is True
    assert result["requested_market_data_type"] == 4
    assert result["quote_provenance"] == "delayed_frozen"
    assert result["price_callbacks"]["bid"]["unavailable"] == 1
    assert "<redacted-path>" in serialized
    assert "<redacted-account>" in serialized
    assert "private\\secret" not in serialized
    assert "U123456" not in serialized
    assert "hunter2" not in serialized
    assert "127.0.0.1" not in serialized


def test_delayed_mode_with_no_price_callbacks_reports_evidence_without_invented_error() -> None:
    class NoDataAdapter(FakeReadOnlyAdapter):
        def get_underlying_summary(self, symbol: str):
            self.calls.append("summary")
            raise AdapterUnavailableError("No usable market data received for SPY.")

        def diagnostics_snapshot(self) -> dict[str, object]:
            return {
                "lifecycle_status": "connected",
                "api_handshake_succeeded": True,
                "client_api_package_version": "10.45.1",
                "tws_server_version": 187,
                "requested_market_data_type": 4,
                "requested_market_data_mode": "delayed_frozen_capable",
                "market_data_type_callbacks": [{"type": 3, "mode": "delayed"}],
                "request_errors": [],
                "informational_messages": [],
                "last_quote": {
                    "market_data_type_callbacks": [{"type": 3, "mode": "delayed"}],
                    "quote_provenance": "delayed",
                    "provenance_confirmed": True,
                    "requested_mode_compatible": True,
                    "core_quote_available": False,
                    "final_quote_usable": False,
                    "reason_code": "no_price_callbacks",
                    "price_callbacks": {},
                    "elapsed_request_seconds": 8.0,
                    "timeout_stage": "market_data_wait",
                    "errors": [],
                },
            }

    with pytest.raises(ReadOnlySmokeFailure) as failure:
        run_readonly_checks("SPY", NoDataAdapter())

    result = failure.value.result()
    assert result["reason_code"] == "no_price_callbacks"
    assert result["quote_provenance"] == "delayed"
    assert result["request_errors"] == []
    assert result["ibkr_errors"] == []
    assert result["final_quote_usable"] is False


def test_eurusd_smoke_uses_cash_contract_and_reports_modern_runtime_diagnostics(monkeypatch) -> None:
    observed: dict[str, object] = {}

    class FakeRuntime:
        def __init__(self, **kwargs: object) -> None:
            observed["runtime_kwargs"] = kwargs
            self.closed = False

        def quote_contract(self, contract: object, **kwargs: object) -> dict[str, object]:
            observed["contract"] = contract
            observed["quote_kwargs"] = kwargs
            return {
                "bid": 1.16,
                "ask": 1.17,
                "high": 1.18,
                "low": 1.14,
                "close": 1.15,
                "market_data_mode": "live",
            }

        def diagnostics_snapshot(self) -> dict[str, object]:
            return {
                "lifecycle_status": "connected",
                "api_handshake_succeeded": True,
                "client_api_package_version": "10.45.1",
                "minimum_client_api_version": "10.45.1",
                "tws_server_version": 187,
                "requested_market_data_type": 4,
                "requested_market_data_mode": "delayed_frozen_capable",
                "market_data_type_callbacks": [{"type": 1, "mode": "live"}],
                "request_errors": [],
                "informational_messages": [],
                "last_quote": {
                    "quote_provenance": "live",
                    "provenance_confirmed": True,
                    "requested_mode_compatible": True,
                    "core_quote_available": True,
                    "final_quote_usable": True,
                    "reason_code": "success",
                    "price_callbacks": {
                        "bid": {"received": 1, "usable": 1, "unavailable": 0},
                        "ask": {"received": 1, "usable": 1, "unavailable": 0},
                    },
                    "elapsed_request_seconds": 0.5,
                    "errors": [],
                },
            }

        def close(self) -> None:
            self.closed = True
            observed["closed"] = True

    cash_contract = object()
    monkeypatch.setattr(smoke_module, "IBKRRuntime", FakeRuntime)
    monkeypatch.setattr(smoke_module, "build_cash_contract", lambda base, quote: cash_contract)

    result = run_eurusd_readonly_check(Settings())

    assert observed["contract"] is cash_contract
    assert observed["closed"] is True
    assert result["contract"] == "EUR/USD CASH IDEALPRO"
    assert result["reason_code"] == "success"
    assert result["client_api_package_version"] == "10.45.1"
    assert result["quote_provenance"] == "live"
    assert result["high_received"] is True
    assert result["low_received"] is True
    assert result["close_received"] is True


def test_readonly_smoke_refuses_to_run_without_explicit_flag() -> None:
    script = Path(__file__).parents[2] / "scripts" / "ibkr_readonly_smoke.py"
    env = {**os.environ}
    env.pop("MODELLATOR_IBKR_READONLY_SMOKE", None)

    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=script.parent.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert completed.returncode == 2
    assert "experimental read-only check" in completed.stderr
