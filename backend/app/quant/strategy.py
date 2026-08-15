from __future__ import annotations

from math import exp, isfinite

from app.models.analytics import (
    AnalyticsState,
    PricingAssumptions,
    ScenarioDayState,
    ScenarioExpirationState,
    ScenarioGridResult,
    ScenarioInput,
    ScenarioPoint,
)
from app.models.market import InstrumentType
from app.models.strategy import (
    BreakevenInterval,
    PayoffMetricState,
    PayoffPoint,
    StrategyDefinition,
    StrategyLeg,
    StrategyLegValuation,
    StrategyValuation,
)
from app.quant.black_scholes import black_scholes_price, intrinsic_value
from app.quant.payoff import analyze_expiry_payoff, payoff_at_expiry


def _signed_quantity(leg: StrategyLeg) -> int:
    sign = 1 if leg.side == "long" else -1
    return sign * leg.quantity


def _leg_multiplier(leg: StrategyLeg) -> int:
    if leg.instrument_type == InstrumentType.STOCK:
        return 1
    if leg.contract is None:
        raise ValueError("Option legs require a contract")
    return leg.contract.multiplier


def _option_time_years(days_forward: int, expiration_days: float) -> float:
    return max(expiration_days - days_forward, 0.0) / 365.0


def _usable_price(value: float | None) -> float | None:
    if value is None:
        return None
    return value if value > 0.0 else None


def _usable_option_market_price(leg: StrategyLeg) -> float | None:
    quote = leg.quote
    if quote is None:
        return None
    for candidate in (quote.mark, quote.last):
        usable = _usable_price(candidate)
        if usable is not None:
            return usable
    return None


def _usable_option_entry_price(leg: StrategyLeg) -> float | None:
    return _usable_price(leg.entry_price)


def _usable_stock_price(leg: StrategyLeg) -> float | None:
    for candidate in (leg.stock_price, leg.entry_price):
        usable = _usable_price(candidate)
        if usable is not None:
            return usable
    return None


def _leg_base_vol(leg: StrategyLeg) -> float | None:
    quote = leg.quote
    if quote is None:
        return None
    for candidate in (quote.implied_vol, quote.broker_implied_vol):
        if candidate is not None and candidate > 0.0:
            return candidate
    return None


def _leg_theoretical_value(leg: StrategyLeg, spot: float, assumptions: PricingAssumptions) -> float | None:
    signed_quantity = _signed_quantity(leg)
    multiplier = _leg_multiplier(leg)
    if leg.instrument_type == InstrumentType.STOCK:
        return signed_quantity * multiplier * spot

    if leg.contract is None:
        raise ValueError("Option legs require a contract")

    expiration_days = (leg.contract.expiration - assumptions.valuation_date).days
    time_to_expiry = _option_time_years(assumptions.days_forward, expiration_days)
    if time_to_expiry <= 0.0:
        option_value = intrinsic_value(spot, leg.contract.strike, leg.contract.right)
        # Static-shock convention: the scenario spot proxies the settlement spot for an expired
        # leg, then the settled cash is carried from expiry to the scenario date.
        carry_days = max(assumptions.days_forward - expiration_days, 0)
        option_value *= exp(assumptions.risk_free_rate * carry_days / 365.0)
    else:
        if not isfinite(spot) or spot <= 0.0:
            return None
        base_vol = _leg_base_vol(leg)
        if base_vol is None:
            return None
        effective_vol = max(base_vol + assumptions.volatility_shift, 1e-4)
        option_value = black_scholes_price(
            spot=spot,
            strike=leg.contract.strike,
            time_to_expiry=time_to_expiry,
            risk_free_rate=assumptions.risk_free_rate,
            volatility=effective_vol,
            option_right=leg.contract.right,
            dividend_yield=assumptions.dividend_yield,
        )
    return signed_quantity * multiplier * option_value


def _leg_market_value(leg: StrategyLeg) -> float | None:
    signed_quantity = _signed_quantity(leg)
    multiplier = _leg_multiplier(leg)
    if leg.instrument_type == InstrumentType.STOCK:
        stock_price = _usable_stock_price(leg)
        if stock_price is None:
            return None
        return signed_quantity * multiplier * stock_price

    premium = _usable_option_market_price(leg)
    if premium is None:
        return None
    return signed_quantity * multiplier * premium


def _leg_entry_value(leg: StrategyLeg) -> float | None:
    signed_quantity = _signed_quantity(leg)
    multiplier = _leg_multiplier(leg)
    if leg.instrument_type == InstrumentType.STOCK:
        stock_price = _usable_stock_price(leg)
        if stock_price is None:
            return None
        return signed_quantity * multiplier * stock_price

    premium = _usable_option_entry_price(leg)
    if premium is None:
        return None
    return signed_quantity * multiplier * premium


def _sample_spot_grid(base_spot: float | None) -> list[float]:
    if base_spot is None or not isfinite(base_spot) or base_spot <= 0.0:
        return []
    floor = max(base_spot * 0.5, 1.0)
    step = max(base_spot * 0.02, 1.0)
    ceiling = max(base_spot * 1.7, floor + step)
    points: list[float] = []
    current = floor
    while current <= ceiling + 1e-9:
        points.append(round(current, 4))
        current += step
    return points


def _sum_or_none(values: list[float | None]) -> float | None:
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _payoff_grid_reference_price(
    strategy: StrategyDefinition,
    assumptions: PricingAssumptions,
) -> float | None:
    for candidate in (assumptions.underlying_price, strategy.underlying_price):
        if isinstance(candidate, (int, float)) and isfinite(candidate) and candidate > 0.0:
            return float(candidate)
    return None


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _volatility_shift_effective(points: list[ScenarioPoint]) -> bool | None:
    if not points:
        return None

    grouped: dict[tuple[int, float], set[float]] = {}
    for point in points:
        if point.theoretical_value is None:
            continue
        grouped.setdefault((point.days_forward, point.move_pct), set()).add(round(point.theoretical_value, 8))
    if not grouped:
        return None
    return any(len(values) > 1 for values in grouped.values())


def _scenario_expiration_state(
    strategy: StrategyDefinition,
    scenario: ScenarioInput,
    days_forward: int,
) -> ScenarioExpirationState:
    expiration_days = [
        (leg.contract.expiration - scenario.valuation_date).days
        for leg in strategy.legs
        if leg.instrument_type == InstrumentType.OPTION and leg.contract is not None
    ]
    if not expiration_days:
        return ScenarioExpirationState.NO_OPTION_LEGS
    expired = [days_forward >= days for days in expiration_days]
    if all(expired):
        return ScenarioExpirationState.AT_OR_AFTER_EXPIRY
    if any(expired):
        return ScenarioExpirationState.MIXED
    return ScenarioExpirationState.PRE_EXPIRY


def _scenario_day_message(state: ScenarioExpirationState, volatility_effective: bool | None) -> str | None:
    if state == ScenarioExpirationState.AT_OR_AFTER_EXPIRY:
        return (
            "At or after expiry: values reflect expiry payoff; volatility shifts have no effect. "
            "Post-expiry cash is carried at the risk-free rate."
        )
    if state == ScenarioExpirationState.MIXED:
        return (
            "Mixed expirations: expired legs use intrinsic settlement at the scenario spot and are "
            "carried to the scenario date at the risk-free rate; unexpired legs retain time value."
        )
    if state == ScenarioExpirationState.NO_OPTION_LEGS:
        return "No option legs: volatility shifts do not affect stock-only scenario values."
    if volatility_effective is False:
        return "Volatility shifts have no material effect on this pre-expiry strategy at the displayed precision."
    return None


def value_strategy(strategy: StrategyDefinition, assumptions: PricingAssumptions) -> StrategyValuation:
    leg_values: list[StrategyLegValuation] = []
    market_values: list[float | None] = []
    theoretical_values: list[float | None] = []
    entry_values: list[float | None] = []
    warnings: list[str] = []

    for leg in strategy.legs:
        leg_warnings: list[str] = []
        market_value = _leg_market_value(leg)
        model_value = _leg_theoretical_value(leg, assumptions.underlying_price, assumptions)
        entry_value = _leg_entry_value(leg)

        if leg.instrument_type == InstrumentType.OPTION:
            quote = leg.quote
            if quote is None:
                leg_warnings.append("No quote is attached to this option leg.")
            else:
                if quote.subscription_missing:
                    leg_warnings.append("This leg is subscription-limited.")
                if quote.market_data_unavailable:
                    leg_warnings.append("No usable market quote was received for this leg.")
            if entry_value is None:
                leg_warnings.append("Entry premium is unavailable for this leg.")
            if market_value is None:
                leg_warnings.append("Current marked value is unavailable for this leg.")
            if model_value is None:
                leg_warnings.append("No usable implied volatility is available for this leg.")
        else:
            if entry_value is None:
                leg_warnings.append("Entry price is unavailable for this stock leg.")
            if market_value is None:
                leg_warnings.append("Current stock price is unavailable for this leg.")

        market_values.append(market_value)
        theoretical_values.append(model_value)
        entry_values.append(entry_value)
        leg_values.append(
            StrategyLegValuation(
                leg_id=leg.leg_id,
                market_value=market_value,
                theoretical_value=model_value,
                entry_value=entry_value,
                pnl_open=(
                    market_value - entry_value
                    if market_value is not None and entry_value is not None
                    else None
                ),
                warnings=leg_warnings,
            )
        )
        warnings.extend(leg_warnings)

    current_value = _sum_or_none(market_values)
    theoretical_value = _sum_or_none(theoretical_values)
    entry_cost = _sum_or_none(entry_values)

    payoff: list[PayoffPoint] = []
    max_profit: float | None = None
    max_loss: float | None = None
    max_profit_state = PayoffMetricState.UNAVAILABLE
    max_loss_state = PayoffMetricState.UNAVAILABLE
    breakevens: list[float] = []
    breakeven_intervals: list[BreakevenInterval] = []
    if entry_cost is not None:
        analysis = analyze_expiry_payoff(strategy)
        max_profit = analysis.max_profit
        max_loss = analysis.max_loss
        max_profit_state = analysis.max_profit_state
        max_loss_state = analysis.max_loss_state
        breakevens = list(analysis.breakevens)
        breakeven_intervals = [
            BreakevenInterval(start=interval.start, end=interval.end)
            for interval in analysis.zero_payoff_intervals
        ]
        grid = _sample_spot_grid(_payoff_grid_reference_price(strategy, assumptions))
        if not grid:
            warnings.append("Payoff chart is unavailable because the valuation grid is empty.")
        else:
            payoff = [PayoffPoint(spot=spot, value=payoff_at_expiry(strategy, spot)) for spot in grid]
    elif strategy.legs:
        warnings.append(
            "Payoff analysis is unavailable because one or more legs have no usable entry premium."
        )

    warnings = _dedupe_preserving_order(warnings)

    if theoretical_value is None and current_value is None and entry_cost is None:
        pricing_state = AnalyticsState.UNAVAILABLE
    elif warnings:
        pricing_state = AnalyticsState.PARTIAL
    else:
        pricing_state = AnalyticsState.COMPLETE

    status_message: str | None = None
    if theoretical_value is None:
        status_message = "Strategy pricing incomplete: one or more legs have no usable implied volatility."
    elif entry_cost is None:
        status_message = "Strategy pricing incomplete: one or more legs have no usable entry premium."
    elif current_value is None:
        status_message = "Strategy pricing incomplete: one or more legs have no usable current quote."
    elif warnings:
        status_message = warnings[0]

    return StrategyValuation(
        strategy_name=strategy.name,
        underlying_symbol=strategy.underlying_symbol,
        assumptions=assumptions,
        net_debit_credit=(-entry_cost if entry_cost is not None else None),
        entry_cost=entry_cost,
        current_value=current_value,
        theoretical_value=theoretical_value,
        pnl_open=(
            current_value - entry_cost if current_value is not None and entry_cost is not None else None
        ),
        max_profit=max_profit,
        max_loss=max_loss,
        max_profit_state=max_profit_state,
        max_loss_state=max_loss_state,
        breakevens=breakevens,
        breakeven_intervals=breakeven_intervals,
        payoff=payoff,
        legs=leg_values,
        pricing_state=pricing_state,
        status_message=status_message,
        warnings=warnings,
    )


def build_scenario_grid(strategy: StrategyDefinition, scenario: ScenarioInput) -> ScenarioGridResult:
    points: list[ScenarioPoint] = []
    warnings: list[str] = []
    base_price = strategy.underlying_price
    base_assumptions = PricingAssumptions(
        valuation_date=scenario.valuation_date,
        underlying_price=base_price,
        risk_free_rate=scenario.risk_free_rate,
        dividend_yield=scenario.dividend_yield,
    )
    base_value = value_strategy(strategy, base_assumptions)

    if base_value.theoretical_value is None:
        return ScenarioGridResult(
            strategy_name=strategy.name,
            underlying_symbol=strategy.underlying_symbol,
            base_underlying_price=base_price,
            points=[],
            pricing_state=AnalyticsState.UNAVAILABLE,
            status_message="Scenario grid unavailable: one or more legs have no usable implied volatility.",
            warnings=base_value.warnings,
            volatility_shift_effective=None,
        )

    if base_value.entry_cost is None:
        return ScenarioGridResult(
            strategy_name=strategy.name,
            underlying_symbol=strategy.underlying_symbol,
            base_underlying_price=base_price,
            points=[],
            pricing_state=AnalyticsState.UNAVAILABLE,
            status_message="Scenario grid unavailable: one or more legs have no usable entry premium.",
            warnings=base_value.warnings,
            volatility_shift_effective=None,
        )

    for days_forward in scenario.days_forward:
        for move_pct in scenario.underlying_moves_pct:
            for vol_shift in scenario.implied_vol_shifts:
                underlying_price = base_price * (1.0 + move_pct)
                assumptions = PricingAssumptions(
                    valuation_date=scenario.valuation_date,
                    underlying_price=underlying_price,
                    risk_free_rate=scenario.risk_free_rate,
                    dividend_yield=scenario.dividend_yield,
                    volatility_shift=vol_shift,
                    days_forward=days_forward,
                )
                valuation = value_strategy(strategy, assumptions)
                points.append(
                    ScenarioPoint(
                        underlying_price=underlying_price,
                        move_pct=move_pct,
                        vol_shift=vol_shift,
                        days_forward=days_forward,
                        current_value=valuation.current_value,
                        theoretical_value=valuation.theoretical_value,
                        pnl_open=(
                            valuation.theoretical_value - base_value.entry_cost
                            if valuation.theoretical_value is not None and base_value.entry_cost is not None
                            else None
                        ),
                    )
                )

    day_states: list[ScenarioDayState] = []
    for days_forward in scenario.days_forward:
        day_points = [point for point in points if point.days_forward == days_forward]
        expiration_state = _scenario_expiration_state(strategy, scenario, days_forward)
        day_volatility_effective = _volatility_shift_effective(day_points)
        day_states.append(
            ScenarioDayState(
                days_forward=days_forward,
                expiration_state=expiration_state,
                volatility_shift_effective=day_volatility_effective,
                message=_scenario_day_message(expiration_state, day_volatility_effective),
            )
        )

    volatility_shift_effective = _volatility_shift_effective(points)
    if base_value.current_value is None:
        warnings.append("Scenario grid is partial due to delayed or limited market data.")
    if volatility_shift_effective is False:
        warnings.append("Volatility shifts have no material effect on the current strategy inputs.")
    warnings = _dedupe_preserving_order(warnings)

    pricing_state = AnalyticsState.PARTIAL if warnings else AnalyticsState.COMPLETE
    status_message = warnings[0] if warnings else None

    return ScenarioGridResult(
        strategy_name=strategy.name,
        underlying_symbol=strategy.underlying_symbol,
        base_underlying_price=base_price,
        points=points,
        pricing_state=pricing_state,
        status_message=status_message,
        warnings=warnings,
        volatility_shift_effective=volatility_shift_effective,
        day_states=day_states,
    )
