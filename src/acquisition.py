"""Phase 1 — download. Re-runnable: skips files already present in data/raw/.

Every source URL and its known quirks are declared in config.md
(`sources` block) and were verified manually on 2026-09-04 — see the
comments there for how each URL was found (CKAN API, browser network
inspection, etc.) and what is unusual about it (WAF blocking non-browser
User-Agents, a national single-file shapefile that needs filtering to our
3 departments, an admin-boundaries substitution because INEI has no stable
direct-download link).
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import requests
from tqdm import tqdm

from src.config import load_config
from src.logging_utils import get_logger

logger = get_logger("acquisition")

# datosabiertos.gob.pe sits behind a WAF that returns HTTP 418 for the
# default requests/curl User-Agent, treating it as a bot attack. A normal
# browser UA is accepted. Used whenever a source declares
# requires_browser_user_agent: true in config.md.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-PE,es;q=0.9",
}


def download_file(url: str, dest: Path, *, force: bool = False, headers: dict | None = None) -> Path:
    """Stream `url` to `dest`, skipping the request entirely if `dest`
    already exists and `force` is False."""
    if dest.exists() and not force:
        logger.info("Ya existe, se omite descarga: %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
        return dest

    logger.info("Descargando %s -> %s", url, dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dest = dest.with_suffix(dest.suffix + ".part")

    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        with open(tmp_dest, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=dest.name
        ) as bar:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    bar.update(len(chunk))

    tmp_dest.replace(dest)
    logger.info("Descarga completa: %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
    return dest


def _latest_renipress_csv_url(ckan_api_url: str) -> str:
    """The CKAN dataset publishes one CSV resource per month; the current
    month's filename is not predictable by pattern, so we resolve it via the
    CKAN API and pick the resource whose filename date (DD-MM-YYYY) is
    latest."""
    resp = requests.get(ckan_api_url, headers=BROWSER_HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    result = payload["result"]
    if isinstance(result, list):
        result = result[0]

    date_pattern = re.compile(r"RENIPRESS_(\d{2})-(\d{2})-(\d{4})\.csv$", re.IGNORECASE)
    candidates: list[tuple[tuple[int, int, int], str]] = []
    for r in result.get("resources", []):
        if r.get("format", "").lower() != "csv":
            continue
        m = date_pattern.search(r["url"])
        if m:
            dd, mm, yyyy = (int(x) for x in m.groups())
            candidates.append(((yyyy, mm, dd), r["url"]))

    if not candidates:
        raise RuntimeError(f"No se encontró ningún recurso CSV con fecha en {ckan_api_url}")

    candidates.sort(key=lambda t: t[0])
    latest_date, latest_url = candidates[-1]
    logger.info("Recurso RENIPRESS más reciente detectado: %s (%s)", latest_url, latest_date)
    return latest_url


def download_renipress(force: bool = False) -> Path:
    cfg = load_config()
    src = cfg.sources["renipress"]
    url = _latest_renipress_csv_url(src["ckan_api_url"])
    dest = cfg.path("raw_dir") / src["local_raw_name"]
    return download_file(url, dest, force=force, headers=BROWSER_HEADERS)


def download_sigmed(force: bool = False) -> Path:
    """Downloads the single national "Centros Poblados" shapefile (zipped)
    and extracts it to data/raw/sigmed_centros_poblados/. The zip itself is
    left untouched in data/raw/ per the raw-data-is-never-modified rule;
    only the extraction is a derived copy."""
    cfg = load_config()
    src = cfg.sources["sigmed"]
    zip_dest = cfg.path("raw_dir") / src["local_raw_name"]
    download_file(src["url"], zip_dest, force=force)

    extract_dir = cfg.path("raw_dir") / "sigmed_centros_poblados"
    if not force and extract_dir.exists() and any(extract_dir.iterdir()):
        logger.info("Ya extraído, se omite: %s", extract_dir)
        return extract_dir

    logger.info("Extrayendo %s -> %s", zip_dest.name, extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_dest) as zf:
        zf.extractall(extract_dir)
    return extract_dir


def download_osm_extract(force: bool = False) -> Path:
    cfg = load_config()
    src = cfg.sources["osm_pbf"]
    dest = cfg.path("raw_dir") / src["local_raw_name"]
    return download_file(src["url"], dest, force=force)


def download_admin_boundaries(force: bool = False) -> Path:
    cfg = load_config()
    src = cfg.sources["admin_boundaries"]
    dest = cfg.path("raw_dir") / src["local_raw_name"]
    return download_file(src["url"], dest, force=force)


def run_all(force: bool = False) -> dict[str, Path]:
    cfg = load_config()
    logger.info("Departamentos en alcance: %s", cfg.department_names)

    results = {
        "renipress": download_renipress(force=force),
        "sigmed": download_sigmed(force=force),
        "osm_pbf": download_osm_extract(force=force),
        "admin_boundaries": download_admin_boundaries(force=force),
    }

    summary = {
        name: {"path": str(path), "size_mb": round(path.stat().st_size / 1e6, 1)}
        if path.is_file()
        else {"path": str(path), "size_mb": None}
        for name, path in results.items()
    }
    summary_path = cfg.path("logs_dir") / "acquisition_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Resumen de adquisición escrito en %s", summary_path)
    return results


if __name__ == "__main__":
    run_all()
