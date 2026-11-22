from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health_report
from app.core.config import get_settings
from app.core.exceptions import (
    HealthDiagnosticsException,
    generic_exception_handler,
    health_exception_handler,
)
from app.core.logging import get_logger, setup_logging

# Settings are loaded when the app is imported, so a bad .env stops the server right away.(fail fast)
settings = get_settings()
#setting out app level logging 
setup_logging(settings.app_env)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: runs once, before the first request.
    logger.info(f"Starting Server Health Diagnostics API (env: {settings.app_env})")
    if not settings.llm_api_key:
        logger.warning("LLM_API_KEY is not set. Reports will use the fallback analysis.")

    yield  # the app handles requests while paused here

    # Shutdown: runs once, when the server stops.
    logger.info("Shutting down Server Health Diagnostics API")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Server Health Diagnostics API",
        description="Reports CPU, memory and disk health and adds an AI-generated diagnosis.",
        version="1.0.0",
        lifespan=lifespan,
        # The interactive docs are shown only in development.
        docs_url="/docs" if settings.app_env == "development" else None,
        # ReDoc (the alternative docs page at /redoc) is switched off in every environment.
        redoc_url=None,
    )

    # Our own errors first, then a catch-all for anything unexpected.
    app.add_exception_handler(HealthDiagnosticsException, health_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # Final URL: /api + /healthreport = /api/healthreport
    app.include_router(health_report.router, prefix="/api")

    return app


app = create_app()