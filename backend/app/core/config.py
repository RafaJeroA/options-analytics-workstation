from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MODELLATOR_",
        extra="ignore",
    )

    app_name: str = "Options Analytics Workstation API"
    environment: str = "development"
    debug: bool = False
    frontend_origin: str = "http://localhost:3000"
    data_mode: str = "mock"
    database_path: Path = Field(default=BACKEND_ROOT / "data" / "modellator.db")
    default_rate: float = 0.0425
    default_dividend_yield: float = 0.0
    mock_valuation_datetime: datetime = datetime(2026, 7, 31, 15, 30, tzinfo=timezone.utc)
    market_summary_cache_ttl_seconds: float = 4.0
    market_chain_cache_ttl_seconds: float = 12.0
    market_option_quote_cache_ttl_seconds: float = 4.0
    market_vol_skew_cache_ttl_seconds: float = 12.0
    market_term_structure_cache_ttl_seconds: float = 45.0
    market_settings_cache_ttl_seconds: float = 5.0

    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_client_id: int = 9001
    ibkr_use_delayed: bool = True
    ibkr_option_quote_include_optional_stats: bool = False
    ibkr_contract_cache_ttl_seconds: float = 1800.0
    ibkr_option_quote_cache_ttl_seconds: float = 8.0
    ibkr_chain_quote_wait_seconds: float = 1.2
    ibkr_chain_default_strike_count: int = 10
    ibkr_chain_spot_window_pct: float = 0.15

    ws_quote_interval_seconds: float = 4.0
    ws_chain_interval_seconds: float = 10.0

    strategy_pricing_cache_ttl_seconds: float = 2.0
    strategy_scenario_cache_ttl_seconds: float = 8.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
