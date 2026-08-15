from __future__ import annotations

from math import isfinite

from app.models.market import OptionRight
from app.quant.black_scholes import black_scholes_price, option_price_bounds


def solve_implied_volatility(
    premium: float,
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    option_right: OptionRight,
    dividend_yield: float = 0.0,
    lower_bound: float = 0.0,
    upper_bound: float = 5.0,
    tolerance: float = 1e-6,
    max_iterations: int = 200,
) -> float | None:
    if not all(
        isfinite(value)
        for value in (
            premium,
            spot,
            strike,
            time_to_expiry,
            risk_free_rate,
            dividend_yield,
            lower_bound,
            upper_bound,
            tolerance,
        )
    ):
        return None
    if premium < 0.0 or spot <= 0.0 or strike <= 0.0 or time_to_expiry <= 0.0:
        return None
    if lower_bound < 0.0 or upper_bound <= lower_bound or tolerance <= 0.0 or max_iterations <= 0:
        return None

    theoretical_lower, theoretical_upper = option_price_bounds(
        spot,
        strike,
        time_to_expiry,
        risk_free_rate,
        option_right,
        dividend_yield,
    )
    if premium < theoretical_lower - tolerance or premium > theoretical_upper + tolerance:
        return None

    low_price = black_scholes_price(
        spot,
        strike,
        time_to_expiry,
        risk_free_rate,
        lower_bound,
        option_right,
        dividend_yield,
    )
    high_price = black_scholes_price(
        spot,
        strike,
        time_to_expiry,
        risk_free_rate,
        upper_bound,
        option_right,
        dividend_yield,
    )
    if abs(premium - low_price) <= tolerance:
        return lower_bound
    if premium < low_price - tolerance or premium > high_price + tolerance:
        return None

    lower = lower_bound
    upper = upper_bound
    for _ in range(max_iterations):
        midpoint = 0.5 * (lower + upper)
        price = black_scholes_price(
            spot,
            strike,
            time_to_expiry,
            risk_free_rate,
            midpoint,
            option_right,
            dividend_yield,
        )
        difference = price - premium
        if abs(difference) <= tolerance:
            return midpoint
        if difference > 0.0:
            upper = midpoint
        else:
            lower = midpoint

    midpoint = 0.5 * (lower + upper)
    final_price = black_scholes_price(
        spot,
        strike,
        time_to_expiry,
        risk_free_rate,
        midpoint,
        option_right,
        dividend_yield,
    )
    return midpoint if abs(final_price - premium) <= tolerance else None
