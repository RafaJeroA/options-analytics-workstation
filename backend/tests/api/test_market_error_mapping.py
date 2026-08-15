from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.adapters.base import (
    AdapterUnavailableError,
    AmbiguousContractError,
    UnknownSymbolError,
)
from app.services.market_service import get_market_service


class FailingMarketService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def get_underlying_summary(self, symbol: str):
        raise self.error


def test_unknown_symbol_maps_to_404(client: TestClient) -> None:
    client.app.dependency_overrides[get_market_service] = lambda: FailingMarketService(
        UnknownSymbolError("Unknown symbol: NOPE")
    )

    response = client.get("/underlyings/NOPE/summary")

    assert response.status_code == 404
    assert "Unknown symbol" in response.json()["detail"]


def test_adapter_unavailability_maps_to_503(client: TestClient) -> None:
    client.app.dependency_overrides[get_market_service] = lambda: FailingMarketService(
        AdapterUnavailableError("IBKR is disconnected")
    )

    response = client.get("/underlyings/SPY/summary")

    assert response.status_code == 503
    assert response.json()["detail"] == "IBKR is disconnected"


def test_ambiguous_contract_maps_to_409(client: TestClient) -> None:
    client.app.dependency_overrides[get_market_service] = lambda: FailingMarketService(
        AmbiguousContractError("Multiple contracts")
    )

    response = client.get("/underlyings/SPY/summary")

    assert response.status_code == 409


def test_lifespan_closes_market_service(monkeypatch, tmp_path) -> None:
    class CloseRecorder:
        closed = False

        def close(self) -> None:
            self.closed = True

    recorder = CloseRecorder()
    monkeypatch.setenv("MODELLATOR_DATABASE_PATH", str(tmp_path / "lifespan.db"))
    monkeypatch.setattr("app.main.get_market_service", lambda: recorder)
    app = create_app()

    with TestClient(app):
        pass

    assert recorder.closed is True
