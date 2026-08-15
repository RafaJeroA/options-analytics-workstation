from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings
from app.models.api import HealthResponse
from app.services.market_service import get_adapter_status, get_store

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    store = get_store()
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc),
        data_mode=settings.data_mode,
        database_ready=store.db_path.exists(),
        adapter_status=get_adapter_status(),
    )
