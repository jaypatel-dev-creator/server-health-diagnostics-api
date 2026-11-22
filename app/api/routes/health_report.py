from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.health_report import HealthReport
from app.services.ai_service import get_ai_analysis
from app.services.metrics_service import classify_status, collect_metrics

router = APIRouter(tags=["Health Report"])

# GET /api/healthreport: the only endpoint. Registered in main.py with the /api prefix.
# Flow: collect_metrics -> classify_status -> get_ai_analysis -> return a HealthReport.
# response_model makes FastAPI validate the response and turn it into JSON.
# The route only coordinates; all the logic is in the two services.
@router.get(
    "/healthreport",
    response_model=HealthReport,
    summary="Get a live system health report",
)
async def get_health_report() -> HealthReport:
    """Read live CPU, memory and disk usage, classify the status, and add an AI diagnosis."""
    settings = get_settings()

    # Step 1: collect the metrics and classify the overall status.
    metrics = await collect_metrics()
    status = classify_status(metrics, settings.warning_threshold, settings.critical_threshold)

    # Step 2: ask the LLM for a summary,  on failure it returns a fallback.
    ai_analysis = await get_ai_analysis(metrics, status)

    return HealthReport(
        timestamp=datetime.now(timezone.utc).replace(microsecond=0),  # UTC, no microseconds
        status=status,
        metrics=metrics,
        ai_analysis=ai_analysis,
    )