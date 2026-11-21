import logging
import sys


def setup_logging(app_env: str = "development") -> None:
    # Debug logs while developing, info and above in production.
    log_level = logging.DEBUG if app_env == "development" else logging.INFO

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Quiet noisy third-party loggers: show only warnings and above.
    for noisy in ["httpx", "httpcore", "google_genai"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)