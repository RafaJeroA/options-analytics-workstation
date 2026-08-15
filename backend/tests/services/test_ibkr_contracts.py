from __future__ import annotations

from datetime import date

import pytest

import app.services.adapters.ibkr_contracts as contracts_module
from app.services.adapters.base import AdapterUnavailableError
from app.services.adapters.ibkr_contracts import build_cash_contract, build_contract_id, parse_contract_id


def test_contract_id_round_trips() -> None:
    contract_id = build_contract_id("spy", date(2026, 4, 17), 510, "call")
    parsed = parse_contract_id(contract_id)

    assert contract_id == "SPY-2026-04-17-510.00-C"
    assert parsed.symbol == "SPY"
    assert parsed.expiration == date(2026, 4, 17)
    assert parsed.strike == 510.0
    assert parsed.right == "C"


def test_contract_id_parser_rejects_invalid_shapes() -> None:
    with pytest.raises(AdapterUnavailableError):
        parse_contract_id("SPY-20260417-510-C")


def test_build_cash_contract_targets_eurusd_idealpro(monkeypatch) -> None:
    class FakeContract:
        pass

    monkeypatch.setattr(contracts_module, "IBAPI_AVAILABLE", True)
    monkeypatch.setattr(contracts_module, "Contract", FakeContract)

    contract = build_cash_contract("eur", "usd")

    assert contract.symbol == "EUR"
    assert contract.currency == "USD"
    assert contract.secType == "CASH"
    assert contract.exchange == "IDEALPRO"
