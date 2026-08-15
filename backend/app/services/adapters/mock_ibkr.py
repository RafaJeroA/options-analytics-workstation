from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.models.market import MarketDataMode, OptionRight
from app.quant.black_scholes import black_scholes_price
from app.services.adapters.base import UnknownContractError, UnknownSymbolError
from app.services.adapters.ibkr_contracts import parse_contract_id

DEFAULT_MOCK_VALUATION_DATETIME = datetime(2026, 7, 31, 15, 30, tzinfo=timezone.utc)


@dataclass(frozen=True)
class MockUnderlying:
    symbol: str
    description: str
    exchange: str
    currency: str
    spot: float
    previous_close: float
    base_iv: float
    dividend_yield: float = 0.0


class MockIBKRAdapter:
    mode = "mock"

    def __init__(
        self,
        default_rate: float = 0.0425,
        valuation_datetime: datetime = DEFAULT_MOCK_VALUATION_DATETIME,
    ) -> None:
        if valuation_datetime.tzinfo is None:
            raise ValueError("Mock valuation datetime must be timezone-aware")
        self.default_rate = default_rate
        self.valuation_datetime = valuation_datetime.astimezone(timezone.utc)
        self.underlyings: dict[str, MockUnderlying] = {
            "SPY": MockUnderlying("SPY", "SPDR S&P 500 ETF", "ARCA", "USD", 531.42, 526.91, 0.173, 0.012),
            "AAPL": MockUnderlying("AAPL", "Apple Inc.", "NASDAQ", "USD", 214.87, 211.58, 0.242, 0.005),
            "NVDA": MockUnderlying("NVDA", "NVIDIA Corp.", "NASDAQ", "USD", 962.14, 948.02, 0.418, 0.0004),
            "TSLA": MockUnderlying("TSLA", "Tesla Inc.", "NASDAQ", "USD", 188.73, 182.65, 0.553, 0.0),
            "QQQ": MockUnderlying("QQQ", "Invesco QQQ Trust", "NASDAQ", "USD", 454.28, 451.16, 0.205, 0.007),
        }
        self._quote_cache: dict[str, dict[str, object]] = {}

    def status(self) -> str:
        return "healthy"

    def search_underlyings(self, query: str) -> list[dict[str, object]]:
        query_upper = query.upper().strip()
        matches = [
            underlying
            for underlying in self.underlyings.values()
            if query_upper in underlying.symbol or query_upper in underlying.description.upper()
        ]
        return [
            {
                "symbol": item.symbol,
                "description": item.description,
                "exchange": item.exchange,
                "currency": item.currency,
                "market_data_mode": MarketDataMode.MOCK.value,
            }
            for item in matches
        ]

    def get_underlying_summary(self, symbol: str) -> dict[str, object]:
        underlying = self._get_underlying(symbol)
        change = underlying.spot - underlying.previous_close
        return {
            "symbol": underlying.symbol,
            "description": underlying.description,
            "exchange": underlying.exchange,
            "currency": underlying.currency,
            "spot": underlying.spot,
            "previous_close": underlying.previous_close,
            "change": change,
            "change_percent": (change / underlying.previous_close) * 100.0,
            "timestamp": self.valuation_datetime.isoformat(),
            "market_data_mode": MarketDataMode.MOCK.value,
            "is_delayed": False,
        }

    def get_option_chain(self, symbol: str, expiration: str | None = None) -> dict[str, object]:
        underlying = self._get_underlying(symbol)
        expirations = self._expirations()
        selected_expiration = expiration or expirations[0].isoformat()
        expiration_date = date.fromisoformat(selected_expiration)

        options: list[dict[str, object]] = []
        for fixture_index, strike in enumerate(self._strikes(underlying.spot)):
            for right in (OptionRight.CALL, OptionRight.PUT):
                options.append(
                    self._quote_for_contract(
                        underlying,
                        expiration_date,
                        strike,
                        right,
                        fixture_index=fixture_index,
                    )
                )

        return {
            "symbol": underlying.symbol,
            "underlying": self.get_underlying_summary(underlying.symbol),
            "expirations": [item.isoformat() for item in expirations],
            "selected_expiration": expiration_date.isoformat(),
            "options": options,
            "updated_at": self.valuation_datetime.isoformat(),
            "market_data_mode": MarketDataMode.MOCK.value,
        }

    def get_option_quote(self, contract_id: str) -> dict[str, object]:
        cached = self._quote_cache.get(contract_id)
        if cached is not None:
            return cached

        parsed = parse_contract_id(contract_id)
        underlying = self._get_underlying(parsed.symbol)
        if parsed.expiration not in self._expirations():
            raise UnknownContractError(
                f"Requested expiration {parsed.expiration.isoformat()} is not available for {parsed.symbol}."
            )
        strikes = self._strikes(underlying.spot)
        try:
            fixture_index = strikes.index(parsed.strike)
        except ValueError as error:
            raise UnknownContractError(f"Unknown mock option contract: {contract_id}") from error
        right = OptionRight.CALL if parsed.right == "C" else OptionRight.PUT
        return self._quote_for_contract(
            underlying,
            parsed.expiration,
            parsed.strike,
            right,
            fixture_index=fixture_index,
        )

    def _get_underlying(self, symbol: str) -> MockUnderlying:
        upper = symbol.upper()
        if upper not in self.underlyings:
            raise UnknownSymbolError(f"Unknown symbol: {upper}")
        return self.underlyings[upper]

    def close(self) -> None:
        """Mock mode owns no external resources."""

    def _expirations(self) -> list[date]:
        start = self.valuation_datetime.date()
        expirations: list[date] = []
        cursor = start
        while len(expirations) < 5:
            cursor += timedelta(days=1)
            if cursor.weekday() == 4:
                expirations.append(cursor)
        return expirations

    def _strikes(self, spot: float) -> list[float]:
        if spot < 75:
            step = 2.5
        elif spot < 250:
            step = 5.0
        elif spot < 600:
            step = 10.0
        else:
            step = 20.0
        atm = round(spot / step) * step
        return [round(atm + step * offset, 2) for offset in range(-8, 9)]

    def _seed(self, symbol: str, expiration: date, strike: float, right: OptionRight) -> int:
        digest = hashlib.sha256(
            f"{symbol}-{expiration.isoformat()}-{strike}-{right.value}".encode("utf-8")
        ).hexdigest()
        return int(digest[:16], 16)

    def _quote_for_contract(
        self,
        underlying: MockUnderlying,
        expiration: date,
        strike: float,
        right: OptionRight,
        *,
        fixture_index: int | None = None,
    ) -> dict[str, object]:
        rng = random.Random(self._seed(underlying.symbol, expiration, strike, right))
        now = self.valuation_datetime
        expiration_days = max((expiration - self.valuation_datetime.date()).days, 1)
        time_to_expiry = expiration_days / 365.0
        moneyness = strike / underlying.spot
        skew_component = 0.11 * max(0.0, 1.0 - moneyness) + 0.07 * abs(math.log(max(moneyness, 1e-6)))
        term_component = 0.015 * math.sqrt(time_to_expiry)
        implied_vol = max(
            underlying.base_iv + skew_component + term_component + rng.uniform(-0.01, 0.01), 0.05
        )
        model_price = black_scholes_price(
            spot=underlying.spot,
            strike=strike,
            time_to_expiry=time_to_expiry,
            risk_free_rate=self.default_rate,
            volatility=implied_vol,
            option_right=right,
            dividend_yield=underlying.dividend_yield,
        )
        mid = max(model_price * (1.0 + rng.uniform(-0.015, 0.015)), 0.01)
        spread = max(0.04, mid * (0.04 + 0.02 * rng.random()))
        bid = max(mid - spread / 2.0, 0.01)
        ask = bid + spread

        distance = abs(strike - underlying.spot) / underlying.spot
        liquidity_scale = max(0.08, 1.0 - distance * 3.5)
        volume = int(1800 * liquidity_scale * (0.4 + rng.random()))
        open_interest = int(9500 * liquidity_scale * (0.5 + rng.random()))
        last = max(mid + rng.uniform(-spread / 3.0, spread / 3.0), 0.01)

        fixture_index = (
            fixture_index if fixture_index is not None else self._strikes(underlying.spot).index(strike)
        )
        market_data_unavailable = False
        if fixture_index == 14 and right == OptionRight.PUT:
            ask = round(ask * 1.65, 4)
        if fixture_index == 0 and right == OptionRight.CALL:
            bid = None
        if fixture_index == 16 and right == OptionRight.PUT and bid is not None:
            ask = round(max(bid - 0.03, 0.01), 4)
        if fixture_index == 1 and right == OptionRight.PUT:
            bid = None
            ask = None
            last = None
            market_data_unavailable = True
        if fixture_index == 15 and right == OptionRight.CALL:
            now = now - timedelta(minutes=30)

        contract_id = f"{underlying.symbol}-{expiration.isoformat()}-{strike:.2f}-{right.value[0].upper()}"
        payload = {
            "contract_id": contract_id,
            "symbol": underlying.symbol,
            "exchange": underlying.exchange,
            "currency": underlying.currency,
            "expiration": expiration.isoformat(),
            "strike": strike,
            "right": right.value,
            "multiplier": 100,
            "local_symbol": f"{underlying.symbol} {expiration.strftime('%y%m%d')} {right.value[0].upper()}{int(strike * 1000):08d}",
            "trading_class": underlying.symbol,
            "bid": None if bid is None else round(bid, 4),
            "ask": None if ask is None else round(ask, 4),
            "last": None if last is None else round(last, 4),
            "model_price": round(model_price, 4),
            "volume": volume,
            "open_interest": open_interest,
            "timestamp": now.isoformat(),
            "is_delayed": False,
            "market_data_mode": MarketDataMode.MOCK.value,
            "market_data_unavailable": market_data_unavailable,
            "subscription_missing": False,
        }
        self._quote_cache[contract_id] = payload
        return payload
