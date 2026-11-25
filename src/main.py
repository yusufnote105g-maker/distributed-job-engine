"""Application entrypoint."""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.auth import RateLimiter, build_keys
from .api.routes import router
from .config import JobEngineConfig
from .logging_config import configure_logging, request_id_var
from .services.database import DatabaseService
from .services.job_processor import JobProcessor

VERSION = __version__

logger = logging.getLogger(__name__)


def create_app(config: Optional[JobEngineConfig] = None) -> FastAPI:
    config = config or JobEngineConfig.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(config)
        logger.info("Starting Job Engine API (workers=%d)", config.worker_count)

        db_service = DatabaseService(config)
        await db_service.initialize()

        processor = JobProcessor(config, db_service)
        if config.enable_workers:
            await processor.start()

        app.state.config = config
        app.state.db_service = db_service
        app.state.job_processor = processor
        app.state.version = VERSION

        try:
            yield
        finally:
            logger.info("Shutting down Job Engine API")
            await processor.stop()
            await db_service.close()

    app = FastAPI(
        title="Distributed Job Engine",
        description="Production-oriented asynchronous job processing engine",
        version=VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.api_keys = build_keys(config)
    app.state.rate_limiter = RateLimiter(config.rate_limit_per_minute)

    @app.middleware("http")
    async def request_context(request, call_next):
        """Attach a request id, log one access line, expose the id to clients."""
        request_id = request.headers.get(config.request_id_header) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        client = request.client.host if request.client else "-"
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "client": client,
                    "api_key": getattr(request.state, "api_key_name", None),
                },
            )
            request_id_var.reset(token)
            raise

        response.headers[config.request_id_header] = request_id
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "client": client,
                "api_key": getattr(request.state, "api_key_name", None),
            },
        )
        request_id_var.reset(token)
        return response

    app.include_router(router, prefix=config.api_prefix)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = JobEngineConfig.from_env()
    configure_logging(settings)
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
