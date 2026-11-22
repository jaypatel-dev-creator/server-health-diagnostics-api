from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# Single shared definition of the three system states: HEALTHY, WARNING, CRITICAL.
# An Enum is used because status is one value from a fixed set, so typos fail early
# Returned by classify_status (services/metrics_service.py).
class SystemStatus(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# Raw readings from the machine, in percent: CPU, memory and disk.
# Created by _read_metrics (services/metrics_service.py).
# A BaseModel, not an Enum: it holds three values at once, while an Enum holds only one.
class Metrics(BaseModel):
    cpu_percent: float
    memory_percent: float
    disk_percent: float


# Passed to Gemini as response_schema (called in ai_service._call_llm). This is what makes
# structured output possible: the reply is forced into a summary and a recommendation.
# If the reply is unusable, _call_llm raises LLMUnavailableException and get_ai_analysis
# returns the fallback, so the client still gets a normal 200 (no 422 or 500).

class AIAnalysis(BaseModel):
    summary: str = Field(
        description="1-2 sentence plain-English summary of the system's current state."
    )
    recommendation: str = Field(
        description="One practical recommendation, or a note that no action is needed if HEALTHY."
    )


# Response schema  of GET /api/healthreport.Automatically serialized to JSON by Fastapi

class HealthReport(BaseModel):
    timestamp: datetime  # UTC time, serialized like 2026-11-21T16:30:00Z
    status: SystemStatus
    metrics: Metrics
    ai_analysis: AIAnalysis

    # Documentation only: shows this example response on the /docs page (development only).
    # It does not affect validation or the real response.


    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2026-11-21T16:30:00Z",
                "status": "WARNING",
                "metrics": {
                    "cpu_percent": 76.5,
                    "memory_percent": 68.2,
                    "disk_percent": 54.0,
                },
                "ai_analysis": {
                    "summary": "Your CPU utilization is elevated at 76.5%, while memory and disk remain within normal limits.",
                    "recommendation": "Check for background processes or heavy applications consuming high CPU cycles.",
                },
            }
        }
    )