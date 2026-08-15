from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.options import router as options_router
from app.api.routes.strategies import router as strategies_router
from app.api.routes.underlyings import router as underlyings_router
from app.api.routes.volatility import router as volatility_router
from app.api.routes.watchlist import router as watchlist_router
from app.api.routes.workspace import router as workspace_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(underlyings_router, prefix="/underlyings", tags=["underlyings"])
api_router.include_router(options_router, prefix="/options", tags=["options"])
api_router.include_router(strategies_router, prefix="/strategies", tags=["strategies"])
api_router.include_router(volatility_router, prefix="/volatility", tags=["volatility"])
api_router.include_router(watchlist_router, prefix="/watchlist", tags=["watchlist"])
api_router.include_router(workspace_router, prefix="/workspace", tags=["workspace"])
