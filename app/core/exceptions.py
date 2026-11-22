from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


# Base exception: every custom error carries a message and an HTTP status code.
class HealthDiagnosticsException(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


#  Raised in services/metrics_service.py (_read_metrics) when psutil cannot read a metric.
class MetricsCollectionException(HealthDiagnosticsException):
    pass


# Raised in services/ai_service.py (_call_llm) when Gemini's structured output fails 
class LLMUnavailableException(HealthDiagnosticsException):
    def __init__(self, message: str = "LLM service unavailable."):
        super().__init__(message=message, status_code=503) #503 ==> service unavailable 


# --- Exception handlers ---

async def health_exception_handler(
    request: Request,
    exc: HealthDiagnosticsException,
) -> JSONResponse:
    if exc.status_code >= 500:
        # Log the real reason, but give the client a generic message.
        logger.error(
            f"{exc.__class__.__name__} on {request.method} {request.url.path}: {exc.message}",
            exc_info=True,
        )
        error_name = "InternalServerError"
        client_message = "An unexpected error occurred."
    else:
         # Not reached with the current exceptions: all of them use a status of 500 or higher.
        # Kept so a future 4xx exception (for example 400 or 404) can show its own message.
        logger.warning(
            f"{exc.__class__.__name__} on {request.method} {request.url.path}: {exc.message}"
        )
        error_name = exc.__class__.__name__
        client_message = exc.message

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_name, "message": client_message},
    )


# Catch-all for any error we did not expect, so the API never returns a raw stack trace.
async def generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {str(exc)}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "InternalServerError", "message": "An unexpected error occurred."},
    )