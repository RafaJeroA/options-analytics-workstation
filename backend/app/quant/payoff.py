from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite

from app.models.market import InstrumentType, OptionRight
from app.models.strategy import PayoffMetricState, StrategyDefinition, StrategyLeg
from app.quant.black_scholes import intrinsic_value

PAYOFF_VALUE_TOLERANCE = 1e-8
BREAKEVEN_SPOT_TOLERANCE = 1e-7


@dataclass(frozen=True)
class ZeroPayoffInterval:
    start: float
    end: float | None


@dataclass(frozen=True)
class ExpiryPayoffAnalysis:
    max_profit: float | None
    max_loss: float | None
    max_profit_state: PayoffMetricState
    max_loss_state: PayoffMetricState
    breakevens: tuple[float, ...]
    zero_payoff_intervals: tuple[ZeroPayoffInterval, ...]


def _signed_quantity(leg: StrategyLeg) -> int:
    return leg.quantity if leg.side == "long" else -leg.quantity


def _leg_multiplier(leg: StrategyLeg) -> int:
    if leg.instrument_type == InstrumentType.STOCK:
        return 1
    if leg.contract is None:
        raise ValueError("Option legs require a contract")
    return leg.contract.multiplier


def _stock_basis(strategy: StrategyDefinition, leg: StrategyLeg) -> float:
    for candidate in (leg.stock_price, leg.entry_price, strategy.underlying_price):
        if candidate is not None and isfinite(candidate):
            return candidate
    raise ValueError("Stock legs require a finite entry basis for payoff analysis")


def payoff_at_expiry(strategy: StrategyDefinition, spot: float) -> float:
    if not isfinite(spot) or spot < 0.0:
        raise ValueError("Expiry payoff requires a finite spot greater than or equal to zero")

    total = 0.0
    for leg in strategy.legs:
        signed_quantity = _signed_quantity(leg)
        multiplier = _leg_multiplier(leg)
        if leg.instrument_type == InstrumentType.STOCK:
            total += signed_quantity * (spot - _stock_basis(strategy, leg))
            continue

        if leg.contract is None:
            raise ValueError("Option legs require a contract")
        if leg.entry_price is None or not isfinite(leg.entry_price):
            raise ValueError("Option legs require a finite entry premium for payoff analysis")
        payoff = intrinsic_value(spot, leg.contract.strike, leg.contract.right)
        total += signed_quantity * multiplier * (payoff - leg.entry_price)
    return total


def _tail_slope(strategy: StrategyDefinition) -> float:
    slope = 0.0
    for leg in strategy.legs:
        signed_quantity = _signed_quantity(leg)
        if leg.instrument_type == InstrumentType.STOCK:
            slope += signed_quantity
        elif leg.contract is not None and leg.contract.right == OptionRight.CALL:
            slope += signed_quantity * leg.contract.multiplier
    return slope


def _is_zero(value: float) -> bool:
    return isclose(value, 0.0, rel_tol=1e-12, abs_tol=PAYOFF_VALUE_TOLERANCE)


def _dedupe_roots(roots: list[float]) -> tuple[float, ...]:
    ordered = sorted(max(0.0, root) for root in roots if isfinite(root) and root >= -BREAKEVEN_SPOT_TOLERANCE)
    deduped: list[float] = []
    for root in ordered:
        if deduped and isclose(root, deduped[-1], rel_tol=1e-10, abs_tol=BREAKEVEN_SPOT_TOLERANCE):
            continue
        deduped.append(round(root, 10))
    return tuple(deduped)


def _inside_zero_interval(root: float, interval: ZeroPayoffInterval) -> bool:
    if root < interval.start - BREAKEVEN_SPOT_TOLERANCE:
        return False
    return interval.end is None or root <= interval.end + BREAKEVEN_SPOT_TOLERANCE


def analyze_expiry_payoff(strategy: StrategyDefinition) -> ExpiryPayoffAnalysis:
    strikes = sorted(
        {
            float(leg.contract.strike)
            for leg in strategy.legs
            if leg.instrument_type == InstrumentType.OPTION and leg.contract is not None
        }
    )
    breakpoints = [0.0, *(strike for strike in strikes if strike > 0.0)]
    values = [payoff_at_expiry(strategy, spot) for spot in breakpoints]
    finite_candidates = list(values)
    roots: list[float] = []
    zero_intervals: list[ZeroPayoffInterval] = []

    for index in range(len(breakpoints) - 1):
        left_spot = breakpoints[index]
        right_spot = breakpoints[index + 1]
        left_value = values[index]
        right_value = values[index + 1]

        if _is_zero(left_value) and _is_zero(right_value):
            zero_intervals.append(ZeroPayoffInterval(left_spot, right_spot))
            continue
        if _is_zero(left_value):
            roots.append(left_spot)
        if _is_zero(right_value):
            roots.append(right_spot)
        if left_value * right_value < 0.0:
            slope = (right_value - left_value) / (right_spot - left_spot)
            roots.append(left_spot - left_value / slope)

    tail_start = breakpoints[-1]
    tail_value = values[-1]
    tail_slope = _tail_slope(strategy)
    if _is_zero(tail_slope):
        if _is_zero(tail_value):
            zero_intervals.append(ZeroPayoffInterval(tail_start, None))
    else:
        tail_root = tail_start - tail_value / tail_slope
        if tail_root >= tail_start - BREAKEVEN_SPOT_TOLERANCE:
            roots.append(tail_root)

    max_profit_state = PayoffMetricState.FINITE
    max_loss_state = PayoffMetricState.FINITE
    max_profit: float | None = max(finite_candidates)
    max_loss: float | None = min(finite_candidates)
    if tail_slope > PAYOFF_VALUE_TOLERANCE:
        max_profit = None
        max_profit_state = PayoffMetricState.UNLIMITED
    elif tail_slope < -PAYOFF_VALUE_TOLERANCE:
        max_loss = None
        max_loss_state = PayoffMetricState.UNLIMITED

    merged_intervals: list[ZeroPayoffInterval] = []
    for interval in zero_intervals:
        if (
            merged_intervals
            and merged_intervals[-1].end is not None
            and isclose(
                merged_intervals[-1].end,
                interval.start,
                rel_tol=1e-10,
                abs_tol=BREAKEVEN_SPOT_TOLERANCE,
            )
        ):
            merged_intervals[-1] = ZeroPayoffInterval(merged_intervals[-1].start, interval.end)
        else:
            merged_intervals.append(interval)

    point_roots = [
        root
        for root in roots
        if not any(_inside_zero_interval(root, interval) for interval in merged_intervals)
    ]
    return ExpiryPayoffAnalysis(
        max_profit=max_profit,
        max_loss=max_loss,
        max_profit_state=max_profit_state,
        max_loss_state=max_loss_state,
        breakevens=_dedupe_roots(point_roots),
        zero_payoff_intervals=tuple(merged_intervals),
    )
