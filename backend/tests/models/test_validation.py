from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.analytics import PricingAssumptions, ScenarioInput
from app.models.market import OptionContract, OptionQuote, OptionRight
from app.models.strategy import StrategyDefinition, StrategyLeg


def contract(symbol: str = "SPY", strike: float = 100, multiplier: int = 100) -> OptionContract:
    return OptionContract(
        contract_id=f"{symbol}-2026-12-18-{strike:.2f}-C",
        symbol=symbol,
        expiration=date(2026, 12, 18),
        strike=strike,
        right=OptionRight.CALL,
        multiplier=multiplier,
    )


@pytest.mark.parametrize(
    ("model", "kwargs", "message"),
    [
        (PricingAssumptions, {"underlying_price": 0}, "greater than 0"),
        (PricingAssumptions, {"underlying_price": -1}, "greater than 0"),
        (PricingAssumptions, {"underlying_price": float("inf")}, "finite number"),
        (PricingAssumptions, {"underlying_price": 100, "days_forward": -1}, "greater than or equal to 0"),
        (ScenarioInput, {"underlying_moves_pct": [-1]}, "greater than -1"),
        (ScenarioInput, {"underlying_moves_pct": [float("nan")]}, "finite number"),
        (ScenarioInput, {"days_forward": [-1]}, "greater than or equal to 0"),
        (ScenarioInput, {"implied_vol_shifts": [float("inf")]}, "finite number"),
    ],
)
def test_financial_models_reject_invalid_numeric_states(
    model, kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        model(**kwargs)


def test_negative_interest_rate_is_valid() -> None:
    assumptions = PricingAssumptions(underlying_price=100, risk_free_rate=-0.025)
    scenario = ScenarioInput(risk_free_rate=-0.025)

    assert assumptions.risk_free_rate == -0.025
    assert scenario.risk_free_rate == -0.025


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("underlying_moves_pct", [0.0, 0.0]),
        ("implied_vol_shifts", [-0.1, -0.1]),
        ("days_forward", [7, 7]),
    ],
)
def test_scenario_dimensions_must_be_unique(field: str, value: list[float] | list[int]) -> None:
    with pytest.raises(ValidationError, match="scenario dimensions must contain unique values"):
        ScenarioInput(**{field: value})


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"strike": 0}, "greater than 0"),
        ({"multiplier": 0}, "greater than 0"),
        ({"strike": float("inf")}, "finite number"),
    ],
)
def test_option_contract_requires_positive_finite_terms(kwargs: dict[str, object], message: str) -> None:
    values = {
        "contract_id": "SPY-2026-12-18-100.00-C",
        "symbol": "SPY",
        "expiration": date(2026, 12, 18),
        "strike": 100,
        "right": OptionRight.CALL,
        "multiplier": 100,
    }
    values.update(kwargs)

    with pytest.raises(ValidationError, match=message):
        OptionContract(**values)


def test_option_leg_requires_contract_and_positive_quantity() -> None:
    with pytest.raises(ValidationError, match="option legs require a contract"):
        StrategyLeg(leg_id="missing", instrument_type="option", side="long", quantity=1)

    with pytest.raises(ValidationError, match="greater than 0"):
        StrategyLeg(leg_id="zero", instrument_type="option", side="long", quantity=0, contract=contract())


def test_stock_leg_requires_stock_fields_but_not_option_contract() -> None:
    leg = StrategyLeg(
        leg_id="stock",
        instrument_type="stock",
        side="long",
        quantity=100,
        stock_price=100,
        underlying_symbol="SPY",
    )

    assert leg.contract is None
    assert leg.quote is None

    with pytest.raises(ValidationError, match="stock legs cannot include"):
        StrategyLeg(
            leg_id="bad-stock",
            instrument_type="stock",
            side="long",
            quantity=100,
            stock_price=100,
            underlying_symbol="SPY",
            contract=contract(),
        )


def test_option_quote_contract_must_match_leg_contract() -> None:
    leg_contract = contract("SPY", 100)
    other_contract = contract("SPY", 105)
    quote = OptionQuote(contract=other_contract, mark=2, updated_at=datetime.now(timezone.utc))

    with pytest.raises(ValidationError, match="quote contract must match"):
        StrategyLeg(
            leg_id="mismatch",
            instrument_type="option",
            side="long",
            contract=leg_contract,
            quote=quote,
        )


def test_strategy_rejects_mixed_underlying_symbols() -> None:
    with pytest.raises(ValidationError, match="does not match strategy symbol"):
        StrategyDefinition(
            name="mixed",
            underlying_symbol="SPY",
            underlying_price=500,
            legs=[StrategyLeg(leg_id="aapl", side="long", contract=contract("AAPL"))],
        )
