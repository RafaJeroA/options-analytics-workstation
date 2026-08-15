from __future__ import annotations

import os

import pytest

from app.core.config import Settings
from scripts.ibkr_readonly_smoke import (
    ENABLE_VALUE,
    build_adapter,
    run_eurusd_readonly_check,
    run_readonly_checks,
)


@pytest.mark.ibkr_live
def test_ibkr_readonly_market_data_smoke_is_opt_in() -> None:
    if os.environ.get("MODELLATOR_IBKR_READONLY_SMOKE") != ENABLE_VALUE:
        pytest.skip("Requires explicit opt-in and a locally running TWS or IB Gateway session.")

    settings = Settings()
    instrument = os.environ.get("MODELLATOR_IBKR_SMOKE_INSTRUMENT", "SPY").upper()
    if instrument == "EURUSD":
        result = run_eurusd_readonly_check(settings)
        assert result["final_quote_usable"] is True
        return

    result = run_readonly_checks(
        os.environ.get("MODELLATOR_IBKR_SMOKE_SYMBOL", instrument),
        build_adapter(settings),
    )

    assert result["matching_symbol_count"] >= 1
    assert result["underlying_quote_received"] is True
