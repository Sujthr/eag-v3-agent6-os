"""
Structured logging for Agent6.

setup_logging()         — configure root logger (call once at startup)
get_logger(name)        — get a namespaced agent6.* logger
add_run_file_handler()  — attach a per-run log file to the agent6 logger
remove_run_file_handler()— detach and flush the per-run log file
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

_CONSOLE_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
_FILE_FORMAT    = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
_DATE_FORMAT    = "%H:%M:%S"
_FILE_DATE_FMT  = "%Y-%m-%d %H:%M:%S"

# Registry: run_id → FileHandler, so we can remove them cleanly
_run_handlers: dict[str, logging.FileHandler] = {}


def setup_logging(level: int = logging.INFO, log_file: str | None = None) -> logging.Logger:
    """Configure root logger once; return the agent6 logger."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        h = logging.FileHandler(log_file, encoding="utf-8")
        h.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_FILE_DATE_FMT))
        handlers.append(h)

    logging.basicConfig(
        level=level,
        format=_CONSOLE_FORMAT,
        datefmt=_DATE_FORMAT,
        handlers=handlers,
        force=True,
    )

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "crawl4ai", "mcp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logging.getLogger("agent6")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"agent6.{name}")


def add_run_file_handler(run_id: str, logs_dir: str | Path) -> Path:
    """
    Attach a FileHandler that writes this run's events to a dedicated log file.
    File name: logs/YYYYMMDD_HHMMSS_<run_id[:8]>.log
    Returns the log file path.
    """
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"{ts}_{run_id[:8]}.log"

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(_FILE_FORMAT, datefmt=_FILE_DATE_FMT)
    )

    agent6_log = logging.getLogger("agent6")
    agent6_log.addHandler(handler)
    _run_handlers[run_id] = handler

    agent6_log.info("═══ Run %s — log file: %s ═══", run_id[:8], log_path.name)
    return log_path


def remove_run_file_handler(run_id: str) -> None:
    """Flush and detach the per-run file handler."""
    handler = _run_handlers.pop(run_id, None)
    if handler:
        handler.flush()
        handler.close()
        logging.getLogger("agent6").removeHandler(handler)
