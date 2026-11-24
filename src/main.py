"""Application entrypoint."""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.routes import router
from .config import JobEngineConfig
from .services.database import DatabaseService
from .services.job_processor import JobProcessor

VERSION = __version__

logger = logging.getLogger(__name__)


def configure_logging(config: JobEngineConfig) -> None:
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )


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
