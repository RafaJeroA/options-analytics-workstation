from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from statistics import fmean
from typing import Any

from app.core.config import get_settings
from app.db.sqlite import SQLiteStore
from app.models.market import ChainSnapshot, OptionQuote, TermStructurePoint, UnderlyingQuote, VolSurfacePoint
from app.services.adapters.base import AdapterUnavailableError, BrokerAdapter
from app.services.adapters.ibkr import IBKRAdapter
from app.services.adapters.mock_ibkr import MockIBKRAdapter
from app.services.cache import KeyedLockPool, TTLCache
from app.services.normalization.market import (
    NormalizationContext,
    normalize_chain_payload,
    normalize_option_quote,
    normalize_search_result,
    normalize_underlying_quote,
)
from app.services.repositories.watchlist import WatchlistRepository
from app.services.repositories.workspace import WorkspaceRepository


class MarketService:
    def __init__(
        self,
        adapter: BrokerAdapter,
        *,
        default_rate: float,
        default_dividend_yield: float,
        store: SQLiteStore | None = None,
        summary_cache_ttl_seconds: float = 4.0,
        chain_cache_ttl_seconds: float = 12.0,
        quote_cache_ttl_seconds: float = 4.0,
        skew_cache_ttl_seconds: float = 12.0,
        term_structure_cache_ttl_seconds: float = 45.0,
        settings_cache_ttl_seconds: float = 5.0,
        valuation_datetime: datetime | None = None,
    ) -> None:
        self.adapter = adapter
        self.default_rate = default_rate
        self.default_dividend_yield = default_dividend_yield
        self.store = store
        self.valuation_datetime = valuation_datetime or getattr(adapter, "valuation_datetime", None)
        self._summary_cache = TTLCache(ttl_seconds=summary_cache_ttl_seconds)
        self._chain_cache = TTLCache(ttl_seconds=chain_cache_ttl_seconds)
        self._quote_cache = TTLCache(ttl_seconds=quote_cache_ttl_seconds)
        self._skew_cache = TTLCache(ttl_seconds=skew_cache_ttl_seconds)
        self._term_structure_cache = TTLCache(ttl_seconds=term_structure_cache_ttl_seconds)
        self._settings_cache = TTLCache(ttl_seconds=settings_cache_ttl_seconds)
        self._cache_locks = KeyedLockPool()

    def search_underlyings(self, query: str) -> list[dict[str, object]]:
        raw_results = self.adapter.search_underlyings(query)
        return [normalize_search_result(item) for item in raw_results]

    def get_underlying_summary(self, symbol: str) -> UnderlyingQuote:
        cache_key = (symbol.upper(),)
        return self._cached_value(
            self._summary_cache,
            "summary",
            cache_key,
            lambda: normalize_underlying_quote(
                self.adapter.get_underlying_summary(symbol),
                context=self._normalization_context(),
            ),
        )

    def get_chain(self, symbol: str, expiration: str | None = None) -> ChainSnapshot:
        cache_key = (symbol.upper(), expiration)
        return self._cached_value(
            self._chain_cache,
            "chain",
            cache_key,
            lambda: self._normalize_chain(symbol, expiration),
        )

    def get_option_quote(self, contract_id: str) -> OptionQuote:
        cache_key = (contract_id,)
        return self._cached_value(
            self._quote_cache,
            "option-quote",
            cache_key,
            lambda: self._normalize_option_quote(contract_id),
        )

    def get_volatility_skew(self, symbol: str, expiration: str | None = None) -> list[VolSurfacePoint]:
        cache_key = (symbol.upper(), expiration)
        return self._cached_value(
            self._skew_cache,
            "volatility-skew",
            cache_key,
            lambda: self._build_volatility_skew(symbol, expiration),
        )

    def get_term_structure(self, symbol: str) -> list[TermStructurePoint]:
        cache_key = (symbol.upper(),)
        return self._cached_value(
            self._term_structure_cache,
            "term-structure",
            cache_key,
            lambda: self._build_term_structure(symbol),
        )

    def invalidate_market_caches(self) -> None:
        self._summary_cache.clear()
        self._chain_cache.clear()
        self._quote_cache.clear()
        self._skew_cache.clear()
        self._term_structure_cache.clear()
        self._settings_cache.clear()

    def close(self) -> None:
        self.invalidate_market_caches()
        close = getattr(self.adapter, "close", None)
        if callable(close):
            close()

    def _normalize_option_quote(self, contract_id: str) -> OptionQuote:
        raw = self.adapter.get_option_quote(contract_id)
        underlying = self.get_underlying_summary(str(raw["symbol"]))
        return normalize_option_quote(
            raw,
            underlying.spot,
            context=self._normalization_context(),
            expect_broker_model=self.adapter.mode == "ibkr",
        )

    def _normalize_chain(self, symbol: str, expiration: str | None = None) -> ChainSnapshot:
        try:
            raw_chain = self.adapter.get_option_chain(symbol, expiration)
        except AdapterUnavailableError as error:
            if not self._should_fallback_expiration(error, expiration):
                raise
            raw_chain = self.adapter.get_option_chain(symbol, None)

        return normalize_chain_payload(
            raw_chain,
            context=self._normalization_context(),
            expect_broker_model=self.adapter.mode == "ibkr",
        )

    def _build_volatility_skew(self, symbol: str, expiration: str | None = None) -> list[VolSurfacePoint]:
        chain = self.get_chain(symbol, expiration)
        points: list[VolSurfacePoint] = []
        for quote in chain.calls + chain.puts:
            if quote.implied_vol is None:
                continue
            points.append(
                VolSurfacePoint(
                    symbol=chain.symbol,
                    expiration=quote.contract.expiration,
                    strike=quote.contract.strike,
                    moneyness=quote.contract.strike / chain.underlying.spot,
                    implied_vol=quote.implied_vol,
                    option_right=quote.contract.right,
                    updated_at=quote.updated_at,
                )
            )
        return sorted(points, key=lambda item: (item.expiration, item.strike, item.option_right))

    def _build_term_structure(self, symbol: str) -> list[TermStructurePoint]:
        structure: list[TermStructurePoint] = []
        base_chain = self.get_chain(symbol)
        for expiration in base_chain.expirations[:6]:
            days_to_expiry = max((expiration - base_chain.updated_at.date()).days, 0)
            try:
                chain = self.get_chain(symbol, expiration.isoformat())
            except (AdapterUnavailableError, LookupError):
                structure.append(
                    TermStructurePoint(
                        symbol=symbol.upper(),
                        expiration=expiration,
                        days_to_expiry=days_to_expiry,
                        sample_size=0,
                        status="unavailable",
                        updated_at=base_chain.updated_at,
                    )
                )
                continue

            usable_quotes = [quote for quote in chain.calls + chain.puts if quote.implied_vol is not None]
            if not usable_quotes:
                structure.append(
                    TermStructurePoint(
                        symbol=symbol.upper(),
                        expiration=expiration,
                        days_to_expiry=days_to_expiry,
                        sample_size=0,
                        status="unavailable",
                        updated_at=chain.updated_at,
                    )
                )
                continue

            atm_strike = min(
                {quote.contract.strike for quote in usable_quotes},
                key=lambda strike: (abs(strike - chain.underlying.spot), strike),
            )
            atm_quotes = [quote for quote in usable_quotes if quote.contract.strike == atm_strike]
            atm_iv = fmean(quote.implied_vol for quote in atm_quotes if quote.implied_vol is not None)
            structure.append(
                TermStructurePoint(
                    symbol=symbol.upper(),
                    expiration=expiration,
                    days_to_expiry=max((expiration - chain.updated_at.date()).days, 0),
                    atm_strike=atm_strike,
                    atm_iv=atm_iv,
                    method="nearest-strike call/put mean",
                    sample_size=len(atm_quotes),
                    status="available",
                    updated_at=chain.updated_at,
                )
            )
        structure.sort(key=lambda item: (item.expiration, item.days_to_expiry))
        return structure

    @staticmethod
    def _should_fallback_expiration(error: AdapterUnavailableError, expiration: str | None) -> bool:
        if expiration is None:
            return False
        message = str(error)
        return "Requested expiration" in message and "is not available" in message

    def _normalization_context(self) -> NormalizationContext:
        risk_free_rate, dividend_yield = self._pricing_defaults()
        return NormalizationContext(
            valuation_datetime=self.valuation_datetime or datetime.now(timezone.utc),
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )

    def _pricing_defaults(self) -> tuple[float, float]:
        cache_key = ("pricing-defaults",)
        cached = self._settings_cache.get(cache_key)
        if cached is not None:
            return cached

        risk_free_rate = self.default_rate
        dividend_yield = self.default_dividend_yield
        if self.store is not None:
            persisted = self.store.get_setting("user_settings") or {}
            if isinstance(persisted.get("default_rate"), (int, float)):
                risk_free_rate = float(persisted["default_rate"])
            if isinstance(persisted.get("default_dividend_yield"), (int, float)):
                dividend_yield = float(persisted["default_dividend_yield"])

        defaults = (risk_free_rate, dividend_yield)
        self._settings_cache.set(cache_key, defaults)
        return defaults

    def _cached_value(
        self,
        cache: TTLCache,
        namespace: str,
        key: tuple[Any, ...],
        loader,
    ) -> Any:
        cached = cache.get(key)
        if cached is not None:
            return cached

        with self._cache_locks.hold((namespace, *key)):
            cached = cache.get(key)
            if cached is not None:
                return cached
            value = loader()
            cache.set(key, value)
            return value


@lru_cache
def get_store() -> SQLiteStore:
    settings = get_settings()
    return SQLiteStore(settings.database_path)


@lru_cache
def get_market_service() -> MarketService:
    settings = get_settings()
    if settings.data_mode == "ibkr":
        adapter = IBKRAdapter(
            host=settings.ibkr_host,
            port=settings.ibkr_port,
            client_id=settings.ibkr_client_id,
            use_delayed=settings.ibkr_use_delayed,
            include_optional_option_stats=settings.ibkr_option_quote_include_optional_stats,
            contract_cache_ttl_seconds=settings.ibkr_contract_cache_ttl_seconds,
            quote_cache_ttl_seconds=settings.ibkr_option_quote_cache_ttl_seconds,
            option_quote_wait_seconds=settings.ibkr_chain_quote_wait_seconds,
            default_chain_strike_count=settings.ibkr_chain_default_strike_count,
            default_chain_spot_window_pct=settings.ibkr_chain_spot_window_pct,
        )
    else:
        adapter = MockIBKRAdapter(
            default_rate=settings.default_rate,
            valuation_datetime=settings.mock_valuation_datetime,
        )
    return MarketService(
        adapter,
        default_rate=settings.default_rate,
        default_dividend_yield=settings.default_dividend_yield,
        store=get_store(),
        summary_cache_ttl_seconds=settings.market_summary_cache_ttl_seconds,
        chain_cache_ttl_seconds=settings.market_chain_cache_ttl_seconds,
        quote_cache_ttl_seconds=settings.market_option_quote_cache_ttl_seconds,
        skew_cache_ttl_seconds=settings.market_vol_skew_cache_ttl_seconds,
        term_structure_cache_ttl_seconds=settings.market_term_structure_cache_ttl_seconds,
        settings_cache_ttl_seconds=settings.market_settings_cache_ttl_seconds,
        valuation_datetime=(settings.mock_valuation_datetime if adapter.mode == "mock" else None),
    )


def get_watchlist_repository() -> WatchlistRepository:
    return WatchlistRepository(get_store())


def get_workspace_repository() -> WorkspaceRepository:
    return WorkspaceRepository(get_store())


def get_adapter_status() -> str:
    try:
        return get_market_service().adapter.status()
    except AdapterUnavailableError as error:
        return str(error)
