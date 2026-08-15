from app.models.market import OptionRight
from app.quant.black_scholes import black_scholes_greeks, black_scholes_price


def test_black_scholes_call_price_matches_reference_value() -> None:
    price = black_scholes_price(
        spot=100.0,
        strike=100.0,
        time_to_expiry=30 / 365,
        risk_free_rate=0.05,
        volatility=0.2,
        option_right=OptionRight.CALL,
    )
    assert round(price, 4) == 2.4934


def test_black_scholes_put_delta_is_negative() -> None:
    greeks = black_scholes_greeks(
        spot=100.0,
        strike=105.0,
        time_to_expiry=45 / 365,
        risk_free_rate=0.04,
        volatility=0.28,
        option_right=OptionRight.PUT,
    )
    assert greeks["delta"] < 0.0
    assert greeks["gamma"] > 0.0
    assert greeks["vega"] > 0.0
