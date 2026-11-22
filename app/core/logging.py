import logging
import sys


def setup_logging(app_env: str = "development") -> None:
    # Debug logs while developing, info and above in production.
    log_level = logging.DEBUG if app_env == "development" else logging.INFO
    # One log line format for the terminal: time | level | module | message.
    # Example: 2026-11-22 03:10:05 | INFO     | app.main | Starting Server Health Diagnostics API
    # The level is padded to 8 characters so the columns line up, and logs go to stdout.
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Quiet noisy third-party loggers: show only warnings and above.
    for noisy in ["httpx", "httpcore", "google_genai"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

# Returns a logger named after the calling file (use get_logger(__name__)), so each log line shows which module wrote it.
def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)