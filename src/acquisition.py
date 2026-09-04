"""Phase 1 — download. Re-runnable: skips files already present in data/raw/."""

from __future__ import annotations

from pathlib import Path

from src.config import load_config
from src.logging_utils import get_logger

logger = get_logger("acquisition")


def download_file(url: str, dest: Path, *, force: bool = False) -> Path:
    """Stream `url` to `dest`, skipping the request entirely if `dest` already
    exists and `force` is False."""
    raise NotImplementedError


def download_renipress(force: bool = False) -> Path:
    raise NotImplementedError


def download_sigmed(force: bool = False) -> Path:
    raise NotImplementedError


def download_osm_extract(force: bool = False) -> Path:
    raise NotImplementedError


def download_admin_boundaries(force: bool = False) -> Path:
    raise NotImplementedError


def run_all(force: bool = False) -> None:
    cfg = load_config()
    logger.info("Departamentos en alcance: %s", cfg.department_names)
    download_renipress(force=force)
    download_sigmed(force=force)
    download_osm_extract(force=force)
    download_admin_boundaries(force=force)


if __name__ == "__main__":
    run_all()
