import asyncio
from pathlib import Path

import psutil

from app.core.exceptions import MetricsCollectionException
from app.core.logging import get_logger
from app.schemas.health_report import Metrics, SystemStatus

logger = get_logger(__name__)


def _read_metrics() -> Metrics:
    """Read CPU, memory and disk usage. This call blocks, so it runs in a thread."""
    try:
        # Sample CPU over half a second. Without an interval, the first reading is always 0.0.
        cpu = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory().percent
        # Drive of the user's home folder (usually the system drive): C:\ on Windows, / on Linux.
        disk = psutil.disk_usage(Path.home().anchor).percent
    except Exception as e:
        raise MetricsCollectionException(f"Failed to read system metrics: {e}") from e

    return Metrics(
        cpu_percent=round(cpu, 1),
        memory_percent=round(memory, 1),
        disk_percent=round(disk, 1),
    )


async def collect_metrics() -> Metrics:
    # psutil blocks, so we run it in a worker thread to keep the event loop free.
    return await asyncio.to_thread(_read_metrics)


def classify_status(
    metrics: Metrics,
    warning_threshold: float,
    critical_threshold: float,
) -> SystemStatus:
    """Overall status is decided by the highest of the three metrics."""
    highest = max(metrics.cpu_percent, metrics.memory_percent, metrics.disk_percent)

    # Strictly greater than: exactly 85% is WARNING, and exactly 70% is HEALTHY.
    if highest > critical_threshold:
        return SystemStatus.CRITICAL
    if highest > warning_threshold:
        return SystemStatus.WARNING
    return SystemStatus.HEALTHY