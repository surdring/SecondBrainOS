from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from starlette.exceptions import HTTPException as StarletteHTTPException

from sbo_core.errors import (
    AppError,
    ErrorResponse,
    ErrorCode,
    get_request_id,
    internal_error,
    validation_error,
)
from sbo_core.routes import ingest_router, query_router, manage_router, episodic_router
from sbo_core.database import get_database, init_database
from sbo_core.config import load_settings

_logger = logging.getLogger("sbo_core")

def create_app() -> FastAPI:
    app = FastAPI(title="SecondBrainOS Core")
    
    # 初始化数据库
    try:
        _ = get_database()
    except Exception:
        settings = load_settings()
        init_database(settings.postgres_dsn)
        _logger.info("Database initialized successfully")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        inbound_request_id = request.headers.get("X-Request-ID")
        request_id = inbound_request_id.strip() if inbound_request_id else ""
        if not request_id:
            request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.middleware("http")
    async def access_log_middleware(request: Request, call_next):
        start = time.perf_counter()
        status_code: int | None = None
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            _logger.info(
                "request",
                extra={
                    "request_id": get_request_id(request),
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        payload = ErrorResponse(
            code=exc.code,
            message=exc.message,
            request_id=get_request_id(request),
            details=exc.details,
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        payload = ErrorResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed",
            request_id=get_request_id(request),
            details={"validation_errors": [str(error) for error in exc.errors()]},
        )
        _logger.warning(
            "validation_error",
            extra={
                "request_id": get_request_id(request),
                "errors": exc.errors(),
            },
        )
        return JSONResponse(status_code=HTTP_422_UNPROCESSABLE_ENTITY, content=payload.model_dump())

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        payload = ErrorResponse(
            code=ErrorCode.HTTP_ERROR,
            message="HTTP error",
            request_id=get_request_id(request),
            details={"status_code": exc.status_code, "detail": exc.detail},
        )
        _logger.warning(
            "http_error",
            extra={
                "request_id": get_request_id(request),
                "status_code": exc.status_code,
                "detail": exc.detail,
            },
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        payload = ErrorResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message="Internal server error",
            request_id=get_request_id(request),
        )
        _logger.exception(
            "unhandled_error",
            extra={
                "request_id": get_request_id(request),
            },
        )
        return JSONResponse(status_code=HTTP_500_INTERNAL_SERVER_ERROR, content=payload.model_dump())

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}
    
    # 注册路由
    app.include_router(ingest_router)
    app.include_router(query_router)
    app.include_router(manage_router)
    app.include_router(episodic_router)
    
    return app
