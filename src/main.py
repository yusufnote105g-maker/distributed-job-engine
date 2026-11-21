import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import JobEngineConfig
from .services.database import DatabaseService
from .services.job_processor import JobProcessor
from .api.routes import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Job Engine API")
    
    # Initialize services
    config = JobEngineConfig()
    db_service = DatabaseService(config)
    job_processor = JobProcessor(config, db_service)
    
    # Start job processor
    await job_processor.start()
    
    # Store services in app state
    app.state.db_service = db_service
    app.state.job_processor = job_processor
    app.state.config = config
    
    yield
    
    # Shutdown
    logger.info("Shutting down Job Engine API")
    await job_processor.stop()


# Create FastAPI app
app = FastAPI(
    title="Distributed Job Engine",
    description="A production-oriented distributed job processing engine",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")


# Signal handlers for graceful shutdown
def handle_shutdown():
    logger.info("Received shutdown signal")
    sys.exit(0)


def handle_sigterm(signum, frame):
    handle_shutdown()


def handle_sigint(signum, frame):
    handle_shutdown()


signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigint)


if __name__ == "__main__":
    import uvicorn
    
    config = JobEngineConfig()
    uvicorn.run(
        "src.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=False,
        log_level=config.log_level.lower()
    )