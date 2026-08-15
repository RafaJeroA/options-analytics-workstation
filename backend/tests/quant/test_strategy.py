from datetime import date, datetime, timedelta, timezone
from math import exp

import pytest
from pydantic import ValidationError

from app.models.analytics import PricingAssumptions, ScenarioInput
from app.models.market import InstrumentType, OptionContract, OptionQuote, OptionRight
from app.models.strategy import StrategyDefinition, StrategyLeg
from app.quant.strategy import build_scenario_grid, payoff_at_expiry, value_strategy


def _call_leg(
    side: str,
    strike: float,
    entry_price: float,
    *,
    expiration: date | None = None,
) -> StrategyLeg:
    contract = OptionContract(
        contract_id=f"TEST-{strike}-C",
        symbol="TEST",
        expiration=expiration or date.today() + timedelta(days=30),
        strike=strike,
        right=OptionRight.CALL,
    )
    quote = OptionQuote(
        contract=contract,
        bid=entry_price - 0.1,
        ask=entry_price + 0.1,
        last=entry_price,
        mark=entry_price,
        implied_vol=0.24,
        updated_at=datetime.now(timezone.utc),
    )
    return StrategyLeg(
        leg_id=f"leg-{strike}", side=side, contract=contract, quote=quote, entry_price=entry_price
    )


def test_vertical_spread_has_bounded_profit_and_loss() -> None:
    strategy = StrategyDefinition(
        name="Bull Call Spread",
        underlying_symbol="TEST",
        underlying_price=100.0,
        legs=[_call_leg("long", 100.0, 4.2), _call_leg("short", 110.0, 1.8)],
    )
    valuation = value_strategy(
        strategy,
        PricingAssumptions(underlying_price=100.0, valuation_date=date.today()),
    )
    assert valuation.max_profit is not None
    assert valuation.max_loss is not None
    assert valuation.max_profit > 0.0


def test_payoff_at_expiry_respects_stock_leg() -> None:
    strategy = StrategyDefinition(
        name="Covered Call",
        underlying_symbol="TEST",
        underlying_price=100.0,
        legs=[
            StrategyLeg(
                leg_id="stock",
                side="long",
                instrument_type=InstrumentType.STOCK,
                quantity=100,
                entry_price=100.0,
                stock_price=100.0,
                underlying_symbol="TEST",
            ),
            _call_leg("short", 105.0, 2.5),
        ],
    )
    payoff = payoff_at_expiry(strategy, 120.0)
    assert payoff < 2000.0


def test_strategy_valuation_marks_missing_entry_as_partial_without_faking_costs() -> None:
    leg = _call_leg("long", 100.0, 4.2)
    leg.entry_price = None
    strategy = StrategyDefinition(
        name="Long Call",
        underlying_symbol="TEST",
        underlying_price=100.0,
        legs=[leg],
    )

    valuation = value_strategy(
        strategy,
        PricingAssumptions(underlying_price=100.0, valuation_date=date.today()),
    )

    assert valuation.theoretical_value is not None
    assert valuation.entry_cost is None
    assert valuation.net_debit_credit is None
    assert valuation.pnl_open is None
    assert valuation.payoff == []
    assert valuation.pricing_state.value == "partial"
    assert (
        valuation.status_message
        == "Strategy pricing incomplete: one or more legs have no usable entry premium."
    )


def test_strategy_model_rejects_non_positive_chart_reference_price() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        StrategyDefinition(
            name="Long Call",
            underlying_symbol="TEST",
            underlying_price=0.0,
            legs=[_call_leg("long", 100.0, 4.2)],
        )


def test_scenario_grid_requires_entry_price_for_open_pnl() -> None:
    leg = _call_leg("long", 100.0, 4.2)
    leg.entry_price = None
    strategy = StrategyDefinition(
        name="Long Call",
        underlying_symbol="TEST",
        underlying_price=100.0,
        legs=[leg],
    )

    scenario = build_scenario_grid(
        strategy,
        ScenarioInput(
            underlying_moves_pct=[0.0],
            implied_vol_shifts=[0.0],
            days_forward=[0],
        ),
    )

    assert scenario.points == []
    assert scenario.pricing_state.value == "unavailable"
    assert (
        scenario.status_message == "Scenario grid unavailable: one or more legs have no usable entry premium."
    )


def test_scenario_grid_reports_when_volatility_shift_changes_pricing() -> None:
    strategy = StrategyDefinition(
        name="Long Call",
        underlying_symbol="TEST",
        underlying_price=100.0,
        legs=[_call_leg("long", 100.0, 4.2)],
    )

    scenario = build_scenario_grid(
        strategy,
        ScenarioInput(
            underlying_moves_pct=[0.0],
            implied_vol_shifts=[-0.1, 0.0, 0.1],
            days_forward=[0],
        ),
    )

    theoretical_values = [point.theoretical_value for point in scenario.points]

    assert scenario.points
    assert scenario.volatility_shift_effective is True
    assert len({value for value in theoretical_values if value is not None}) == 3
    assert scenario.day_states[0].expiration_state.value == "pre_expiry"
    assert scenario.day_states[0].volatility_shift_effective is True


def test_scenario_grid_exact_expiry_collapses_volatility_dimension_semantically() -> None:
    valuation_date = date(2026, 7, 31)
    strategy = StrategyDefinition(
        name="Long Call",
        underlying_symbol="TEST",
        underlying_price=105.0,
        legs=[_call_leg("long", 100.0, 4.2, expiration=valuation_date + timedelta(days=7))],
    )

    scenario = build_scenario_grid(
        strategy,
        ScenarioInput(
            valuation_date=valuation_date,
            underlying_moves_pct=[0.0],
            implied_vol_shifts=[-0.1, 0.0, 0.1],
            days_forward=[7],
        ),
    )

    assert len({point.theoretical_value for point in scenario.points}) == 1
    assert scenario.day_states[0].expiration_state.value == "at_or_after_expiry"
    assert scenario.day_states[0].volatility_shift_effective is False
    assert scenario.day_states[0].message is not None
    assert scenario.day_states[0].message.startswith("At or after expiry:")


def test_scenario_grid_post_expiry_carries_settled_cash_without_volatility_sensitivity() -> None:
    valuation_date = date(2026, 7, 31)
    strategy = StrategyDefinition(
        name="Long Call",
        underlying_symbol="TEST",
        underlying_price=110.0,
        legs=[_call_leg("long", 100.0, 4.2, expiration=valuation_date + timedelta(days=7))],
    )

    scenario = build_scenario_grid(
        strategy,
        ScenarioInput(
            valuation_date=valuation_date,
            underlying_moves_pct=[0.0],
            implied_vol_shifts=[-0.1, 0.0, 0.1],
            days_forward=[14],
            risk_free_rate=0.05,
        ),
    )

    expected_value = 1_000.0 * exp(0.05 * 7 / 365.0)
    assert all(point.theoretical_value == pytest.approx(expected_value) for point in scenario.points)
    assert scenario.day_states[0].expiration_state.value == "at_or_after_expiry"
    assert scenario.day_states[0].volatility_shift_effective is False


def test_scenario_grid_mixed_expirations_settles_only_expired_legs() -> None:
    valuation_date = date(2026, 7, 31)
    strategy = StrategyDefinition(
        name="Call Calendar",
        underlying_symbol="TEST",
        underlying_price=105.0,
        legs=[
            _call_leg("short", 100.0, 4.2, expiration=valuation_date + timedelta(days=7)),
            _call_leg("long", 100.0, 6.0, expiration=valuation_date + timedelta(days=21)),
        ],
    )

    scenario = build_scenario_grid(
        strategy,
        ScenarioInput(
            valuation_date=valuation_date,
            underlying_moves_pct=[0.0],
            implied_vol_shifts=[-0.1, 0.0, 0.1],
            days_forward=[0, 7, 14, 21],
        ),
    )

    states = {state.days_forward: state for state in scenario.day_states}
    assert states[0].expiration_state.value == "pre_expiry"
    assert states[7].expiration_state.value == "mixed"
    assert states[14].expiration_state.value == "mixed"
    assert states[14].volatility_shift_effective is True
    assert states[21].expiration_state.value == "at_or_after_expiry"
    assert states[21].volatility_shift_effective is False
    assert len({(point.days_forward, point.move_pct, point.vol_shift) for point in scenario.points}) == len(
        scenario.points
    )
