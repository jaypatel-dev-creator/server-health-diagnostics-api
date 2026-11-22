import asyncio
from pathlib import Path

import psutil

from app.core.exceptions import MetricsCollectionException
from app.core.logging import get_logger
from app.schemas.health_report import Metrics, SystemStatus

logger = get_logger(__name__)

# Private helper (leading underscore), used only inside this file. Called by collect_metrics.
def _read_metrics() -> Metrics:
    """Read CPU, memory and disk usage. This call blocks, so it runs in a thread."""
    try:
        cpu = psutil.cpu_percent(interval=0.5) #read the cpu value 
        memory = psutil.virtual_memory().percent #read the memory value 
        disk = psutil.disk_usage(Path.home().anchor).percent #read the disk value 
    except Exception as e:
        raise MetricsCollectionException(f"Failed to read system metrics: {e}") from e

    return Metrics(
        cpu_percent=round(cpu, 1),
        memory_percent=round(memory, 1),
        disk_percent=round(disk, 1),
    )


    # psutil is a blocking (synchronous) library, not async, so it cannot be awaited.
    # Called directly inside an async function, it would run on the event loop and block it:
    # the CPU read waits 0.5 s, and no other request could be handled meanwhile.
    # asyncio.to_thread offloads it to a thread from the default thread pool,
    # so the event loop stays free. One blocking call on the loop would stall every request.

    # Called by the route (api/routes/health_report.py). Runs _read_metrics in a worker thread.
async def collect_metrics() -> Metrics:
    return await asyncio.to_thread(_read_metrics)




    # Take the highest of the three metrics and compare only that one value with the thresholds:
    # above critical -> CRITICAL, otherwise above warning -> WARNING, otherwise HEALTHY.
    # Called by the route (api/routes/health_report.py).
def classify_status(
    metrics: Metrics,
    warning_threshold: float,
    critical_threshold: float,
) -> SystemStatus:
    highest = max(metrics.cpu_percent, metrics.memory_percent, metrics.disk_percent)

    if highest > critical_threshold:
        return SystemStatus.CRITICAL
    if highest > warning_threshold:
        return SystemStatus.WARNING
    return SystemStatus.HEALTHY