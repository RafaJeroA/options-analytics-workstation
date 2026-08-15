from __future__ import annotations

import asyncio
import math
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.services.adapters.base import (
    AdapterUnavailableError,
    AmbiguousContractError,
    MarketDataNotFoundError,
)
from app.services.market_service import get_market_service, get_store


def _json_safe_validation_value(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {key: _json_safe_validation_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_validation_value(item) for item in value]
    return str(value)


def create_app() -> FastAPI:
    settings = get_settings()
    get_store()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            close = getattr(get_market_service(), "close", None)
            if callable(close):
                close()

    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": _json_safe_validation_value(error.errors())},
        )

    @app.exception_handler(MarketDataNotFoundError)
    async def market_data_not_found_handler(
        _request: Request, error: MarketDataNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(AmbiguousContractError)
    async def ambiguous_contract_handler(_request: Request, error: AmbiguousContractError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(AdapterUnavailableError)
    async def adapter_unavailable_handler(_request: Request, error: AdapterUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    app.include_router(api_router)

    async def stream_snapshot(
        websocket: WebSocket,
        *,
        channel: str,
        interval_seconds: float,
        loader,
    ) -> None:
        await websocket.accept()
        last_payload_json: str | None = None
        try:
            while True:
                try:
                    snapshot = loader()
                except AdapterUnavailableError as error:
                    await websocket.send_json(
                        {
                            "channel": channel,
                            "payload": None,
                            "status": "degraded",
                            "message": str(error),
                        }
                    )
                    await websocket.close(code=1013)
                    return
                except Exception:
                    await websocket.send_json(
                        {
                            "channel": channel,
                            "payload": None,
                            "status": "degraded",
                            "message": "Refresh stream stopped because market data could not be refreshed safely.",
                        }
                    )
                    await websocket.close(code=1011)
                    return

                payload_json = snapshot.model_dump_json()
                if payload_json != last_payload_json:
                    await websocket.send_json(
                        {
                            "channel": channel,
                            "payload": snapshot.model_dump(mode="json"),
                            "status": "ok",
                        }
                    )
                    last_payload_json = payload_json
                await asyncio.sleep(interval_seconds)
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/quotes/{symbol}")
    async def quotes_stream(websocket: WebSocket, symbol: str) -> None:
        market_service = get_market_service()
        await stream_snapshot(
            websocket,
            channel="quotes",
            interval_seconds=settings.ws_quote_interval_seconds,
            loader=lambda: market_service.get_underlying_summary(symbol),
        )

    @app.websocket("/ws/chains/{symbol}")
    async def chain_stream(websocket: WebSocket, symbol: str) -> None:
        market_service = get_market_service()
        expiration = websocket.query_params.get("expiration")
        await stream_snapshot(
            websocket,
            channel="chains",
            interval_seconds=settings.ws_chain_interval_seconds,
            loader=lambda: market_service.get_chain(symbol, expiration),
        )

    return app


app = create_app()
