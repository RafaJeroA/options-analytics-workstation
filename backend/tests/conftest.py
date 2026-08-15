from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services.market_service import get_market_service, get_store


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("MODELLATOR_DATA_MODE", "mock")
    monkeypatch.setenv("MODELLATOR_DATABASE_PATH", str(tmp_path / "modellator.db"))
    get_settings.cache_clear()
    get_market_service.cache_clear()
    get_store.cache_clear()

    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()
    get_market_service.cache_clear()
    get_store.cache_clear()
