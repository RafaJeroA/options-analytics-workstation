from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.analytics import PricingAssumptions
from app.models.market import InstrumentType, OptionContract, OptionQuote, OptionRight
from app.models.strategy import PayoffMetricState, StrategyDefinition, StrategyLeg
from app.quant.payoff import analyze_expiry_payoff
from app.quant.strategy import value_strategy


def option_leg(
    leg_id: str,
    right: OptionRight,
    side: str,
    strike: float,
    premium: float,
    *,
    quantity: int = 1,
    multiplier: int = 100,
) -> StrategyLeg:
    contract = OptionContract(
        contract_id=f"TEST-2026-12-18-{strike:.2f}-{right.value[0].upper()}-{leg_id}",
        symbol="TEST",
        expiration=date.today() + timedelta(days=90),
        strike=strike,
        right=right,
        multiplier=multiplier,
    )
    quote = OptionQuote(
        contract=contract,
        bid=max(premium - 0.05, 0.01),
        ask=premium + 0.05,
        last=premium,
        mark=premium,
        implied_vol=0.25,
        updated_at=datetime.now(timezone.utc),
    )
    return StrategyLeg(
        leg_id=leg_id,
        instrument_type=InstrumentType.OPTION,
        side=side,
        quantity=quantity,
        contract=contract,
        quote=quote,
        entry_price=premium,
    )


def stock_leg(side: str = "long", quantity: int = 100, basis: float = 100.0) -> StrategyLeg:
    return StrategyLeg(
        leg_id="stock",
        instrument_type=InstrumentType.STOCK,
        side=side,
        quantity=quantity,
        stock_price=basis,
        entry_price=basis,
        underlying_symbol="TEST",
    )


def valuation(name: str, legs: list[StrategyLeg], spot: float = 100.0):
    strategy = StrategyDefinition(name=name, underlying_symbol="TEST", underlying_price=spot, legs=legs)
    return value_strategy(strategy, PricingAssumptions(underlying_price=spot, valuation_date=date.today()))


@pytest.mark.parametrize(
    ("name", "legs", "max_profit", "max_loss", "profit_state", "loss_state", "breakevens"),
    [
        (
            "long call",
            [option_leg("lc", OptionRight.CALL, "long", 100, 5)],
            None,
            -500,
            PayoffMetricState.UNLIMITED,
            PayoffMetricState.FINITE,
            [105],
        ),
        (
            "short call",
            [option_leg("sc", OptionRight.CALL, "short", 100, 5)],
            500,
            None,
            PayoffMetricState.FINITE,
            PayoffMetricState.UNLIMITED,
            [105],
        ),
        (
            "long put",
            [option_leg("lp", OptionRight.PUT, "long", 100, 5)],
            9500,
            -500,
            PayoffMetricState.FINITE,
            PayoffMetricState.FINITE,
            [95],
        ),
        (
            "short put",
            [option_leg("sp", OptionRight.PUT, "short", 100, 5)],
            500,
            -9500,
            PayoffMetricState.FINITE,
            PayoffMetricState.FINITE,
            [95],
        ),
        (
            "covered call",
            [stock_leg(), option_leg("cc", OptionRight.CALL, "short", 110, 3)],
            1300,
            -9700,
            PayoffMetricState.FINITE,
            PayoffMetricState.FINITE,
            [97],
        ),
        (
            "protective put",
            [stock_leg(), option_leg("pp", OptionRight.PUT, "long", 95, 2)],
            None,
            -700,
            PayoffMetricState.UNLIMITED,
            PayoffMetricState.FINITE,
            [102],
        ),
        (
            "bull call spread",
            [
                option_leg("bc-long", OptionRight.CALL, "long", 100, 5),
                option_leg("bc-short", OptionRight.CALL, "short", 110, 2),
            ],
            700,
            -300,
            PayoffMetricState.FINITE,
            PayoffMetricState.FINITE,
            [103],
        ),
        (
            "bear call spread",
            [
                option_leg("bec-short", OptionRight.CALL, "short", 100, 8),
                option_leg("bec-long", OptionRight.CALL, "long", 110, 3),
            ],
            500,
            -500,
            PayoffMetricState.FINITE,
            PayoffMetricState.FINITE,
            [105],
        ),
        (
            "bull put spread",
            [
                option_leg("bp-long", OptionRight.PUT, "long", 90, 1),
                option_leg("bp-short", OptionRight.PUT, "short", 100, 4),
            ],
            300,
            -700,
            PayoffMetricState.FINITE,
            PayoffMetricState.FINITE,
            [97],
        ),
        (
            "bear put spread",
            [
                option_leg("bep-long", OptionRight.PUT, "long", 110, 12),
                option_leg("bep-short", OptionRight.PUT, "short", 100, 5),
            ],
            300,
            -700,
            PayoffMetricState.FINITE,
            PayoffMetricState.FINITE,
            [103],
        ),
        (
            "long straddle",
            [
                option_leg("ls-c", OptionRight.CALL, "long", 100, 5),
                option_leg("ls-p", OptionRight.PUT, "long", 100, 4),
            ],
            None,
            -900,
            PayoffMetricState.UNLIMITED,
            PayoffMetricState.FINITE,
            [91, 109],
        ),
        (
            "short straddle",
            [
                option_leg("ss-c", OptionRight.CALL, "short", 100, 5),
                option_leg("ss-p", OptionRight.PUT, "short", 100, 4),
            ],
            900,
            None,
            PayoffMetricState.FINITE,
            PayoffMetricState.UNLIMITED,
            [91, 109],
        ),
        (
            "long strangle",
            [
                option_leg("str-p", OptionRight.PUT, "long", 90, 3),
                option_leg("str-c", OptionRight.CALL, "long", 110, 2),
            ],
            None,
            -500,
            PayoffMetricState.UNLIMITED,
            PayoffMetricState.FINITE,
            [85, 115],
        ),
        (
            "butterfly",
            [
                option_leg("fly-low", OptionRight.CALL, "long", 90, 12),
                option_leg("fly-mid", OptionRight.CALL, "short", 100, 6, quantity=2),
                option_leg("fly-high", OptionRight.CALL, "long", 110, 2),
            ],
            800,
            -200,
            PayoffMetricState.FINITE,
            PayoffMetricState.FINITE,
            [92, 108],
        ),
        (
            "iron condor",
            [
                option_leg("ic-lp", OptionRight.PUT, "long", 90, 1),
                option_leg("ic-sp", OptionRight.PUT, "short", 95, 2),
                option_leg("ic-sc", OptionRight.CALL, "short", 105, 2),
                option_leg("ic-lc", OptionRight.CALL, "long", 110, 1),
            ],
            200,
            -300,
            PayoffMetricState.FINITE,
            PayoffMetricState.FINITE,
            [93, 107],
        ),
    ],
)
def test_exact_strategy_metrics(
    name: str,
    legs: list[StrategyLeg],
    max_profit: float | None,
    max_loss: float | None,
    profit_state: PayoffMetricState,
    loss_state: PayoffMetricState,
    breakevens: list[float],
) -> None:
    result = valuation(name, legs)

    if max_profit is None:
        assert result.max_profit is None
    else:
        assert result.max_profit == pytest.approx(max_profit)
    if max_loss is None:
        assert result.max_loss is None
    else:
        assert result.max_loss == pytest.approx(max_loss)
    assert result.max_profit_state == profit_state
    assert result.max_loss_state == loss_state
    assert result.breakevens == pytest.approx(breakevens)


def test_distant_strike_metrics_are_independent_of_chart_interval() -> None:
    result = valuation("distant call", [option_leg("far", OptionRight.CALL, "long", 200, 1)])

    assert result.payoff[-1].spot == 170
    assert result.breakevens == [201]
    assert result.max_profit is None
    assert result.max_profit_state == PayoffMetricState.UNLIMITED
    assert result.max_loss == -100


def test_mixed_quantity_and_multiplier_scale_cash_risk_without_changing_breakeven() -> None:
    result = valuation(
        "scaled call",
        [option_leg("scaled", OptionRight.CALL, "long", 100, 3, quantity=2, multiplier=50)],
    )

    assert result.max_loss == -300
    assert result.breakevens == [103]
    assert result.max_profit_state == PayoffMetricState.UNLIMITED


def test_net_debit_and_credit_use_positive_credit_negative_debit_convention() -> None:
    debit = valuation("debit", [option_leg("debit", OptionRight.CALL, "long", 100, 5)])
    credit = valuation("credit", [option_leg("credit", OptionRight.CALL, "short", 100, 5)])

    assert debit.net_debit_credit == -500
    assert credit.net_debit_credit == 500


def test_duplicate_roots_are_deduplicated() -> None:
    result = valuation(
        "duplicated root",
        [
            option_leg("first", OptionRight.CALL, "long", 100, 5),
            option_leg("second", OptionRight.CALL, "long", 100, 5),
        ],
    )

    assert result.breakevens == [105]


def test_zero_payoff_intervals_are_explicit_instead_of_fabricating_point_roots() -> None:
    strategy = StrategyDefinition(
        name="flat zero",
        underlying_symbol="TEST",
        underlying_price=100,
        legs=[
            option_leg("long", OptionRight.CALL, "long", 100, 5),
            option_leg("short", OptionRight.CALL, "short", 100, 5),
        ],
    )

    result = analyze_expiry_payoff(strategy)

    assert result.max_profit == 0
    assert result.max_loss == 0
    assert result.breakevens == ()
    assert len(result.zero_payoff_intervals) == 1
    assert result.zero_payoff_intervals[0].start == 0
    assert result.zero_payoff_intervals[0].end is None
