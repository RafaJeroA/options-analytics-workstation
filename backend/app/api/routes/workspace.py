from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.models.api import SaveSettingsRequest, SaveStrategyRequest
from app.models.user import RecentChainView, SavedStrategyRecord, UserSettings
from app.services.market_service import MarketService, get_market_service, get_workspace_repository
from app.services.repositories.workspace import WorkspaceRepository

router = APIRouter()


@router.get("/recent-chains", response_model=list[RecentChainView])
def recent_chains(
    repository: WorkspaceRepository = Depends(get_workspace_repository),
) -> list[RecentChainView]:
    return repository.list_recent_chains()


@router.get("/settings", response_model=UserSettings)
def get_settings(
    repository: WorkspaceRepository = Depends(get_workspace_repository),
) -> UserSettings:
    return repository.load_settings()


@router.put("/settings", response_model=UserSettings)
def save_settings(
    payload: SaveSettingsRequest,
    repository: WorkspaceRepository = Depends(get_workspace_repository),
    market_service: MarketService = Depends(get_market_service),
) -> UserSettings:
    saved = repository.save_settings(payload.settings)
    market_service.invalidate_market_caches()
    return saved


@router.get("/strategies", response_model=list[SavedStrategyRecord])
def list_saved_strategies(
    repository: WorkspaceRepository = Depends(get_workspace_repository),
) -> list[SavedStrategyRecord]:
    return repository.list_saved_strategies()


@router.post("/strategies", response_model=SavedStrategyRecord)
def save_strategy(
    payload: SaveStrategyRequest,
    repository: WorkspaceRepository = Depends(get_workspace_repository),
) -> SavedStrategyRecord:
    return repository.save_strategy(
        strategy=payload.strategy,
        name=payload.name,
        strategy_id=payload.strategy_id,
    )


@router.delete("/strategies/{strategy_id}")
def delete_strategy(
    strategy_id: str,
    repository: WorkspaceRepository = Depends(get_workspace_repository),
) -> dict[str, bool]:
    deleted = repository.delete_strategy(strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Unknown strategy: {strategy_id}")
    return {"deleted": True}
