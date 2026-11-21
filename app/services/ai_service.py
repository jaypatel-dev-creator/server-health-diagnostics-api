import asyncio
from typing import Optional

from google import genai
from google.genai import types

from app.core.config import get_settings
from app.core.exceptions import LLMUnavailableException
from app.core.logging import get_logger
from app.schemas.health_report import AIAnalysis, Metrics, SystemStatus

logger = get_logger(__name__)

# Extra seconds on top of the SDK's own timeouts, as a last-resort limit.
_HARD_LIMIT_SLACK_SECONDS = 5

_SYSTEM_INSTRUCTION = (
    "You are a server diagnostics assistant. You receive CPU, memory and disk usage "
    "percentages and an overall status. The status is always correct and is already "
    "computed from the metrics, so explain it and never say it is inconsistent. "
    "Be concise and factual. Do not invent metrics that were not provided."
)

# Generic advice used when the LLM is unavailable, one line per status.
_FALLBACK_RECOMMENDATIONS = {
    SystemStatus.HEALTHY: "No action is needed.",
    SystemStatus.WARNING: "Check which processes are using the most resources.",
    SystemStatus.CRITICAL: "Investigate high resource usage now and free up resources.",
}

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    # Create the client once and reuse it.
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(
            api_key=settings.llm_api_key,
            http_options=types.HttpOptions(
                timeout=settings.llm_timeout_seconds * 1000,  # the SDK expects milliseconds
                retry_options=types.HttpRetryOptions(attempts=settings.llm_max_attempts),
            ),
        )
    return _client


def _build_prompt(metrics: Metrics, status: SystemStatus) -> str:
    settings = get_settings()
    readings = {
        "CPU": metrics.cpu_percent,
        "memory": metrics.memory_percent,
        "disk": metrics.disk_percent,
    }
    busiest = max(readings, key=readings.get)  # the metric that decides the status

    return (
        "System metrics:\n"
        f"- CPU utilization: {metrics.cpu_percent}%\n"
        f"- Memory utilization: {metrics.memory_percent}%\n"
        f"- Disk utilization: {metrics.disk_percent}%\n"
        f"Overall status: {status.value} "
        f"(WARNING above {settings.warning_threshold}%, CRITICAL above {settings.critical_threshold}%).\n"
        f"The status comes from the highest reading, which is {busiest} at {readings[busiest]}%. "
        "The status is correct.\n\n"
        "Return:\n"
        "1. summary: 1-2 plain-English sentences about the system's current state.\n"
        "2. recommendation: one practical action for the busiest resource. "
        "If the status is HEALTHY, say that no action is needed."
    )


async def _call_llm(metrics: Metrics, status: SystemStatus) -> AIAnalysis:
    settings = get_settings()

    # Passing the Pydantic class as response_schema forces the reply into summary + recommendation.
    request = _get_client().aio.models.generate_content(
        model=settings.llm_model,
        contents=_build_prompt(metrics, status),
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=AIAnalysis,
            temperature=0.2,
        ),
    )

    # Hard time limit, in case the SDK's own timeout does not fire.
    hard_limit = settings.llm_timeout_seconds * settings.llm_max_attempts + _HARD_LIMIT_SLACK_SECONDS
    response = await asyncio.wait_for(request, timeout=hard_limit)

    # "parsed" can be None, for example when the output is cut off.
    analysis = response.parsed
    if not isinstance(analysis, AIAnalysis):
        raise LLMUnavailableException("LLM returned no usable structured output.")
    if not analysis.summary.strip() or not analysis.recommendation.strip():
        raise LLMUnavailableException("LLM returned an empty summary or recommendation.")
    return analysis


def _fallback_analysis(status: SystemStatus) -> AIAnalysis:
    return AIAnalysis(
        summary=(
            f"AI analysis is currently unavailable. "
            f"The system status is {status.value}, based on the raw metrics."
        ),
        recommendation=_FALLBACK_RECOMMENDATIONS[status],
    )


async def get_ai_analysis(metrics: Metrics, status: SystemStatus) -> AIAnalysis:
    """Return the LLM analysis, or a fallback. This function never raises."""
    settings = get_settings()

    if not settings.llm_api_key:
        logger.warning("LLM_API_KEY is not set. Using the fallback analysis.")
        return _fallback_analysis(status)

    try:
        return await _call_llm(metrics, status)
    except Exception as e:
        # Broad on purpose: a timeout, network error, API error or bad output must not crash the API.
        # CancelledError is not caught here, so a cancelled request still stops normally.
        logger.warning(f"LLM call failed: {e!r}. Using the fallback analysis.")
        return _fallback_analysis(status)