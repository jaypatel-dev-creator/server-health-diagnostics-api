from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# The three possible overall statuses. Inheriting from str makes it serialize as plain text.
class SystemStatus(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# Raw numbers read from the machine, in percent.
class Metrics(BaseModel):
    cpu_percent: float
    memory_percent: float
    disk_percent: float


# What the LLM must return. We also pass this class to Gemini as the response schema,
# so the model's reply is forced into exactly these two fields.
class AIAnalysis(BaseModel):
    summary: str = Field(
        description="1-2 sentence plain-English summary of the system's current state."
    )
    recommendation: str = Field(
        description="One practical recommendation, or a note that no action is needed if HEALTHY."
    )


# Response of GET /api/healthreport.
class HealthReport(BaseModel):
    timestamp: datetime  # UTC time, serialized like 2026-11-21T16:30:00Z
    status: SystemStatus
    metrics: Metrics
    ai_analysis: AIAnalysis

    # Example shown in the /docs page.
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