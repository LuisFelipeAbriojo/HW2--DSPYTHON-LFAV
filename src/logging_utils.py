"""Shared logging setup. Every long-running step (download, validation,
routing) must log to both stdout and a per-run file under logs/, per the
"no silent 40-minute run" requirement in the assignment (Phase 2)."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from src.config import load_config


def get_logger(name: str) -> logging.Logger:
    cfg = load_config()
    logs_dir = cfg.path("logs_dir")

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured (e.g. re-imported in a notebook)

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_handler = logging.FileHandler(
        logs_dir / f"{name}_{ts}.log", encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
