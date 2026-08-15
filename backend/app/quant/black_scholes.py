from __future__ import annotations

import math

from app.models.market import OptionRight

SQRT_TWO_PI = math.sqrt(2.0 * math.pi)


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / SQRT_TWO_PI


def _require_finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _validate_pricing_inputs(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    dividend_yield: float,
) -> None:
    for name, value in {
        "spot": spot,
        "strike": strike,
        "time_to_expiry": time_to_expiry,
        "risk_free_rate": risk_free_rate,
        "volatility": volatility,
        "dividend_yield": dividend_yield,
    }.items():
        _require_finite(name, value)
    if spot < 0.0:
        raise ValueError("spot must be greater than or equal to zero")
    if strike <= 0.0:
        raise ValueError("strike must be greater than zero")
    if time_to_expiry < 0.0:
        raise ValueError("time_to_expiry must be greater than or equal to zero")
    if volatility < 0.0:
        raise ValueError("volatility must be greater than or equal to zero")
    if time_to_expiry > 0.0 and spot <= 0.0:
        raise ValueError("spot must be greater than zero before expiry")


def intrinsic_value(spot: float, strike: float, option_right: OptionRight) -> float:
    _require_finite("spot", spot)
    _require_finite("strike", strike)
    if spot < 0.0:
        raise ValueError("spot must be greater than or equal to zero")
    if strike <= 0.0:
        raise ValueError("strike must be greater than zero")
    if option_right == OptionRight.CALL:
        return max(spot - strike, 0.0)
    return max(strike - spot, 0.0)


def option_price_bounds(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    option_right: OptionRight,
    dividend_yield: float = 0.0,
) -> tuple[float, float]:
    _validate_pricing_inputs(spot, strike, time_to_expiry, risk_free_rate, 0.0, dividend_yield)
    if time_to_expiry == 0.0:
        intrinsic = intrinsic_value(spot, strike, option_right)
        return intrinsic, intrinsic

    discounted_spot = spot * math.exp(-dividend_yield * time_to_expiry)
    discounted_strike = strike * math.exp(-risk_free_rate * time_to_expiry)
    if option_right == OptionRight.CALL:
        return max(discounted_spot - discounted_strike, 0.0), discounted_spot
    return max(discounted_strike - discounted_spot, 0.0), discounted_strike


def black_scholes_price(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    option_right: OptionRight,
    dividend_yield: float = 0.0,
) -> float:
    _validate_pricing_inputs(spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield)
    if time_to_expiry == 0.0:
        return intrinsic_value(spot, strike, option_right)

    discounted_spot = spot * math.exp(-dividend_yield * time_to_expiry)
    discounted_strike = strike * math.exp(-risk_free_rate * time_to_expiry)
    if volatility == 0.0:
        if option_right == OptionRight.CALL:
            return max(discounted_spot - discounted_strike, 0.0)
        return max(discounted_strike - discounted_spot, 0.0)

    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (
        math.log(spot / strike)
        + (risk_free_rate - dividend_yield + 0.5 * volatility * volatility) * time_to_expiry
    ) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t

    if option_right == OptionRight.CALL:
        return discounted_spot * normal_cdf(d1) - discounted_strike * normal_cdf(d2)
    return discounted_strike * normal_cdf(-d2) - discounted_spot * normal_cdf(-d1)


def black_scholes_greeks(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    option_right: OptionRight,
    dividend_yield: float = 0.0,
) -> dict[str, float]:
    _validate_pricing_inputs(spot, strike, time_to_expiry, risk_free_rate, volatility, dividend_yield)
    if time_to_expiry == 0.0:
        intrinsic = intrinsic_value(spot, strike, option_right)
        return {
            "delta": 1.0
            if option_right == OptionRight.CALL and spot > strike
            else -1.0
            if option_right == OptionRight.PUT and spot < strike
            else 0.0,
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
            "rho": 0.0,
            "theoretical_price": intrinsic,
        }

    discounted_spot = spot * math.exp(-dividend_yield * time_to_expiry)
    discounted_strike = strike * math.exp(-risk_free_rate * time_to_expiry)
    if volatility == 0.0:
        call_in_the_money = discounted_spot > discounted_strike
        put_in_the_money = discounted_strike > discounted_spot
        if option_right == OptionRight.CALL:
            delta = math.exp(-dividend_yield * time_to_expiry) if call_in_the_money else 0.0
            theta = (
                dividend_yield * discounted_spot - risk_free_rate * discounted_strike
                if call_in_the_money
                else 0.0
            ) / 365.0
            rho = discounted_strike * time_to_expiry / 100.0 if call_in_the_money else 0.0
        else:
            delta = -math.exp(-dividend_yield * time_to_expiry) if put_in_the_money else 0.0
            theta = (
                risk_free_rate * discounted_strike - dividend_yield * discounted_spot
                if put_in_the_money
                else 0.0
            ) / 365.0
            rho = -discounted_strike * time_to_expiry / 100.0 if put_in_the_money else 0.0
        return {
            "delta": delta,
            "gamma": 0.0,
            "theta": theta,
            "vega": 0.0,
            "rho": rho,
            "theoretical_price": black_scholes_price(
                spot,
                strike,
                time_to_expiry,
                risk_free_rate,
                volatility,
                option_right,
                dividend_yield,
            ),
        }

    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (
        math.log(spot / strike)
        + (risk_free_rate - dividend_yield + 0.5 * volatility * volatility) * time_to_expiry
    ) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t

    pdf_d1 = normal_pdf(d1)

    gamma = math.exp(-dividend_yield * time_to_expiry) * pdf_d1 / (spot * volatility * sqrt_t)
    vega = discounted_spot * pdf_d1 * sqrt_t / 100.0

    if option_right == OptionRight.CALL:
        delta = math.exp(-dividend_yield * time_to_expiry) * normal_cdf(d1)
        theta = (
            -discounted_spot * pdf_d1 * volatility / (2.0 * sqrt_t)
            - risk_free_rate * discounted_strike * normal_cdf(d2)
            + dividend_yield * discounted_spot * normal_cdf(d1)
        ) / 365.0
        rho = discounted_strike * time_to_expiry * normal_cdf(d2) / 100.0
    else:
        delta = -math.exp(-dividend_yield * time_to_expiry) * normal_cdf(-d1)
        theta = (
            -discounted_spot * pdf_d1 * volatility / (2.0 * sqrt_t)
            + risk_free_rate * discounted_strike * normal_cdf(-d2)
            - dividend_yield * discounted_spot * normal_cdf(-d1)
        ) / 365.0
        rho = -discounted_strike * time_to_expiry * normal_cdf(-d2) / 100.0

    theoretical_price = black_scholes_price(
        spot=spot,
        strike=strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        volatility=volatility,
        option_right=option_right,
        dividend_yield=dividend_yield,
    )
    return {
        "delta": delta,
        "gamma": gamma,
        "theta": theta,
        "vega": vega,
        "rho": rho,
        "theoretical_price": theoretical_price,
    }


def extrinsic_value(
    mark: float | None, spot: float, strike: float, option_right: OptionRight
) -> float | None:
    if mark is None:
        return None
    return max(mark - intrinsic_value(spot, strike, option_right), 0.0)
