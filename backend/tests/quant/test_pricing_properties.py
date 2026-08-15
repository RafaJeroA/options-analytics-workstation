from __future__ import annotations

import math

import pytest

from app.models.market import OptionRight
from app.quant.black_scholes import (
    black_scholes_greeks,
    black_scholes_price,
    intrinsic_value,
    option_price_bounds,
)


@pytest.mark.parametrize("risk_free_rate", [0.04, -0.015])
def test_put_call_parity_with_continuous_dividend_yield(risk_free_rate: float) -> None:
    spot = 103.0
    strike = 100.0
    time = 0.75
    dividend_yield = 0.018
    volatility = 0.31

    call = black_scholes_price(
        spot, strike, time, risk_free_rate, volatility, OptionRight.CALL, dividend_yield
    )
    put = black_scholes_price(spot, strike, time, risk_free_rate, volatility, OptionRight.PUT, dividend_yield)
    parity = spot * math.exp(-dividend_yield * time) - strike * math.exp(-risk_free_rate * time)

    assert call - put == pytest.approx(parity, abs=1e-10)


def test_zero_volatility_uses_discounted_deterministic_payoff() -> None:
    call = black_scholes_price(100, 100, 1, 0.05, 0, OptionRight.CALL)
    put = black_scholes_price(90, 100, 1, 0.05, 0, OptionRight.PUT)

    assert call == pytest.approx(100 - 100 * math.exp(-0.05))
    assert put == pytest.approx(100 * math.exp(-0.05) - 90)


@pytest.mark.parametrize("right", [OptionRight.CALL, OptionRight.PUT])
def test_expiry_price_is_intrinsic_value(right: OptionRight) -> None:
    assert black_scholes_price(90, 100, 0, -0.02, 0.4, right, 0.03) == intrinsic_value(90, 100, right)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"spot": float("nan")}, "spot must be finite"),
        ({"spot": 0.0}, "spot must be greater than zero before expiry"),
        ({"strike": 0.0}, "strike must be greater than zero"),
        ({"time_to_expiry": -1.0}, "time_to_expiry must be greater than or equal to zero"),
        ({"volatility": -0.1}, "volatility must be greater than or equal to zero"),
    ],
)
def test_invalid_pricing_inputs_are_rejected(kwargs: dict[str, float], message: str) -> None:
    inputs = {
        "spot": 100.0,
        "strike": 100.0,
        "time_to_expiry": 1.0,
        "risk_free_rate": 0.03,
        "volatility": 0.2,
        "option_right": OptionRight.CALL,
        "dividend_yield": 0.01,
    }
    inputs.update(kwargs)

    with pytest.raises(ValueError, match=message):
        black_scholes_price(**inputs)


def test_european_price_bounds_include_dividends_and_negative_rates() -> None:
    call_lower, call_upper = option_price_bounds(100, 95, 0.5, -0.01, OptionRight.CALL, 0.02)
    put_lower, put_upper = option_price_bounds(100, 95, 0.5, -0.01, OptionRight.PUT, 0.02)

    discounted_spot = 100 * math.exp(-0.02 * 0.5)
    discounted_strike = 95 * math.exp(0.01 * 0.5)
    assert call_lower == pytest.approx(max(discounted_spot - discounted_strike, 0))
    assert call_upper == pytest.approx(discounted_spot)
    assert put_lower == pytest.approx(max(discounted_strike - discounted_spot, 0))
    assert put_upper == pytest.approx(discounted_strike)


def test_analytic_greeks_match_finite_differences() -> None:
    spot = 102.0
    strike = 100.0
    time = 0.6
    rate = 0.025
    volatility = 0.27
    dividend = 0.012
    greeks = black_scholes_greeks(spot, strike, time, rate, volatility, OptionRight.CALL, dividend)

    spot_bump = 0.01
    up = black_scholes_price(spot + spot_bump, strike, time, rate, volatility, OptionRight.CALL, dividend)
    down = black_scholes_price(spot - spot_bump, strike, time, rate, volatility, OptionRight.CALL, dividend)
    center = black_scholes_price(spot, strike, time, rate, volatility, OptionRight.CALL, dividend)
    delta_fd = (up - down) / (2 * spot_bump)
    gamma_fd = (up - 2 * center + down) / (spot_bump**2)

    vol_bump = 1e-4
    vega_fd_per_point = (
        (
            black_scholes_price(spot, strike, time, rate, volatility + vol_bump, OptionRight.CALL, dividend)
            - black_scholes_price(spot, strike, time, rate, volatility - vol_bump, OptionRight.CALL, dividend)
        )
        / (2 * vol_bump)
        / 100
    )

    rate_bump = 1e-5
    rho_fd_per_point = (
        (
            black_scholes_price(spot, strike, time, rate + rate_bump, volatility, OptionRight.CALL, dividend)
            - black_scholes_price(
                spot, strike, time, rate - rate_bump, volatility, OptionRight.CALL, dividend
            )
        )
        / (2 * rate_bump)
        / 100
    )

    assert greeks["delta"] == pytest.approx(delta_fd, rel=1e-5)
    assert greeks["gamma"] == pytest.approx(gamma_fd, rel=2e-4)
    assert greeks["vega"] == pytest.approx(vega_fd_per_point, rel=1e-6)
    assert greeks["rho"] == pytest.approx(rho_fd_per_point, rel=1e-6)
    assert 0 < greeks["delta"] < math.exp(-dividend * time)
    assert greeks["gamma"] > 0
    assert greeks["vega"] > 0
