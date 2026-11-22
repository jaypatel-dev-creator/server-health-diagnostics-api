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

# Module-level singleton: one client is created on first use and reused for every request,
# which is safe because it holds no per-request state.
# Optional because it starts as None (lazy creation)(get_client initialies on first request, not on startup in lifespan ) ), so the app starts without an API key
# and the client is never built when the key is missing.
_client: Optional[genai.Client] = None



# Private helper. Called by _call_llm (this file) to get the shared Gemini client.

def _get_client() -> genai.Client:
    # Create the client once and reuse it.
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(
            api_key=settings.llm_api_key,
            http_options=types.HttpOptions(
                timeout=settings.llm_timeout_seconds * 1000,  #  timeout seconds ( the SDK expects milliseconds)
                retry_options=types.HttpRetryOptions(attempts=settings.llm_max_attempts), #attempts for retry 
            ),
        )
    return _client

# Builds the prompt text sent to Gemini: the three readings, the overall status with its
# thresholds, and which metric is the highest. It asks for a short summary and one recommendation.
# It states that the status is correct, so Gemini explains it instead of questioning it.
# Called by _call_llm (this file). The response shape comes from response_schema, not from this prompt
def _build_prompt(metrics: Metrics, status: SystemStatus) -> str:
    settings = get_settings()
    readings = {
        "CPU": metrics.cpu_percent,
        "memory": metrics.memory_percent,
        "disk": metrics.disk_percent,
    }
    busiest = max(readings, key=readings.get)  # metric with higest value 

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

# Sends the prompt to Gemini and returns the reply as an AIAnalysis object.
# Called by get_ai_analysis (this file). Raises LLMUnavailableException if the reply is unusable;
# timeouts and API errors also propagate, and get_ai_analysis catches all of them and returns the fallback.
async def _call_llm(metrics: Metrics, status: SystemStatus) -> AIAnalysis:
    settings = get_settings()

    # Creates the request using the async client (.aio). 
    request = _get_client().aio.models.generate_content(
        model=settings.llm_model,                    # model name, from settings (LLM_MODEL)
        contents=_build_prompt(metrics, status),     # the prompt text with the readings and status
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,  # the role of the model, sent separately from the data
            response_mime_type="application/json",   # the reply must be JSON
            response_schema=AIAnalysis,              # the JSON must match AIAnalysis (summary + recommendation) #structurd output is enforced here 
            temperature=0.2,                         # low randomness, so answers are consistent and factual
        ),
    )

 # Backstop timeout, in case the SDK's own timeout does not fire. We set the limits explicitly:
    # per-attempt timeout (LLM_TIMEOUT_SECONDS, default 10 s) x attempts (LLM_MAX_ATTEMPTS, default 2)
    # + 5 s slack = 25 s maximum in total with the defaults.
    hard_limit = settings.llm_timeout_seconds * settings.llm_max_attempts + _HARD_LIMIT_SLACK_SECONDS
    # Sends the request and waits for the reply; raises a timeout error if it takes longer than hard_limit.
    response = await asyncio.wait_for(request, timeout=hard_limit)

    # The SDK converts the JSON reply into an AIAnalysis object. It can be None, for example if the output is cut off.
    analysis = response.parsed
    if not isinstance(analysis, AIAnalysis):
        raise LLMUnavailableException("LLM returned no usable structured output.")
    # The reply has the right shape but the text is empty or only spaces, so it is not useful either.
    if not analysis.summary.strip() or not analysis.recommendation.strip():
        raise LLMUnavailableException("LLM returned an empty summary or recommendation.")
    return analysis

# Builds the fallback answer used when the LLM is not available: no API key, timeout, API error or unusable output. Same AIAnalysis shape as the real answer, so the JSON never changes.
# The summary says AI analysis is unavailable and shows the current status, and the recommendation
# is one fixed line per status from _FALLBACK_RECOMMENDATIONS. No LLM call is made here.
# Called by get_ai_analysis (this file).
def _fallback_analysis(status: SystemStatus) -> AIAnalysis:
    return AIAnalysis(
        summary=(
            f"AI analysis is currently unavailable. "
            f"The system status is {status.value}, based on the raw metrics."
        ),
        recommendation=_FALLBACK_RECOMMENDATIONS[status],
    )

# Main entry point of this file, called by the route (api/routes/health_report.py).
# Returns the LLM analysis, or the fallback if the LLM is not available. 
async def get_ai_analysis(metrics: Metrics, status: SystemStatus) -> AIAnalysis:
    settings = get_settings()
    # Missing key: return the fallback right away, without calling Gemini.
    if not settings.llm_api_key:
        logger.warning("LLM_API_KEY is not set. Using the fallback analysis.")
        return _fallback_analysis(status)

    try:
        return await _call_llm(metrics, status)
    except Exception as e:
        # Broad on purpose, so the API never crashes. It catches: a timeout (SDK or hard limit), a network error, an API error (including a wrong or rejected API key), and unusable output (LLMUnavailableException). The reason is logged and the fallback is returned.

        logger.warning(f"LLM call failed: {e!r}. Using the fallback analysis.")
        return _fallback_analysis(status)