from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services.adapters.base import AdapterUnavailableError
from app.services.market_service import get_market_service, get_store


def test_chain_websocket_degrades_gracefully_on_refresh_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MODELLATOR_DATA_MODE", "mock")
    monkeypatch.setenv("MODELLATOR_DATABASE_PATH", str(tmp_path / "modellator.db"))
    get_settings.cache_clear()
    get_market_service.cache_clear()
    get_store.cache_clear()

    import app.main as main_module

    class StubService:
        def get_chain(self, symbol: str, expiration: str | None = None):
            raise AdapterUnavailableError("No usable market data was received from IBKR.")

    monkeypatch.setattr(main_module, "get_market_service", lambda: StubService())

    app = main_module.create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws/chains/SPY") as websocket:
            payload = websocket.receive_json()

    assert payload["channel"] == "chains"
    assert payload["status"] == "degraded"
    assert payload["payload"] is None
    assert "No usable market data was received from IBKR." in payload["message"]

    get_settings.cache_clear()
    get_market_service.cache_clear()
    get_store.cache_clear()
