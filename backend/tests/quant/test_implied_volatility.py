import pytest

from app.models.market import OptionRight
from app.quant.black_scholes import black_scholes_price
from app.quant.implied_volatility import solve_implied_volatility


def test_implied_volatility_recovers_input_vol() -> None:
    premium = black_scholes_price(
        spot=100.0,
        strike=100.0,
        time_to_expiry=60 / 365,
        risk_free_rate=0.03,
        volatility=0.24,
        option_right=OptionRight.CALL,
    )
    implied_vol = solve_implied_volatility(
        premium=premium,
        spot=100.0,
        strike=100.0,
        time_to_expiry=60 / 365,
        risk_free_rate=0.03,
        option_right=OptionRight.CALL,
    )
    assert implied_vol is not None
    assert abs(implied_vol - 0.24) < 1e-4


def test_implied_volatility_rejects_invalid_premium() -> None:
    implied_vol = solve_implied_volatility(
        premium=0.01,
        spot=100.0,
        strike=50.0,
        time_to_expiry=30 / 365,
        risk_free_rate=0.02,
        option_right=OptionRight.CALL,
    )
    assert implied_vol is None


def test_implied_volatility_accepts_valid_put_below_current_intrinsic() -> None:
    implied_vol = solve_implied_volatility(
        premium=7.0,
        spot=90.0,
        strike=100.0,
        time_to_expiry=1.0,
        risk_free_rate=0.05,
        option_right=OptionRight.PUT,
    )

    assert implied_vol is not None
    assert implied_vol > 0


def test_implied_volatility_recovers_vol_with_negative_rate_and_dividend() -> None:
    premium = black_scholes_price(105, 100, 0.8, -0.01, 0.32, OptionRight.CALL, 0.015)

    result = solve_implied_volatility(premium, 105, 100, 0.8, -0.01, OptionRight.CALL, 0.015)

    assert result == pytest.approx(0.32, abs=1e-5)


def test_implied_volatility_returns_zero_at_deterministic_lower_bound() -> None:
    lower_bound = black_scholes_price(100, 100, 1, 0.05, 0, OptionRight.CALL)

    assert solve_implied_volatility(lower_bound, 100, 100, 1, 0.05, OptionRight.CALL) == 0


@pytest.mark.parametrize("premium", [4.0, 100.0])
def test_implied_volatility_rejects_prices_outside_european_bounds(premium: float) -> None:
    assert solve_implied_volatility(premium, 90, 100, 1, 0.05, OptionRight.PUT) is None


def test_implied_volatility_does_not_return_unconverged_midpoint() -> None:
    assert (
        solve_implied_volatility(
            10,
            100,
            100,
            1,
            0,
            OptionRight.CALL,
            max_iterations=1,
            tolerance=1e-12,
        )
        is None
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"premium": float("nan")},
        {"spot": 0.0},
        {"strike": 0.0},
        {"time_to_expiry": 0.0},
        {"max_iterations": 0},
    ],
)
def test_implied_volatility_rejects_invalid_inputs(kwargs: dict[str, float | int]) -> None:
    inputs = {
        "premium": 10.0,
        "spot": 100.0,
        "strike": 100.0,
        "time_to_expiry": 1.0,
        "risk_free_rate": 0.02,
        "option_right": OptionRight.CALL,
    }
    inputs.update(kwargs)

    assert solve_implied_volatility(**inputs) is None
