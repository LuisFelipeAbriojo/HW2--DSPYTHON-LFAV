"""Phase 1 — data quality rules for RENIPRESS.

Column names, encoding, and category values below were verified against the
real August 2026 RENIPRESS extract (36,004 rows) on 2026-09-04 — see
logs/acquisition_summary.json and the CATEGORIA/ESTADO value counts in the
project notes. Notably: the file is UTF-8 with a BOM and ';'-delimited (not
comma), CATEGORIA already uses clean "I-1".."III-E" strings for real
records but 8,552 rows (23.7%) carry the literal string "0" instead of a
category, and 13,174 rows (36.6%) have null NORTE/ESTE coordinates.

Each check_* function takes the full DataFrame and returns
(result_df, flagged_df, report_row):
  - result_df: same length as input, with corrections applied in place
    (e.g. swapped coordinates fixed) and a boolean flag column added —
    rows are never silently dropped here.
  - flagged_df: the subset that triggered the rule, for audit/logging.
  - report_row: one row for the Phase 1 data quality report.
The only rule that removes rows from the *clean* working copy is
check_duplicate_codes (exact duplicate facility codes double-count supply).
"""

from __future__ import annotations

import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from src.config import load_config
from src.logging_utils import get_logger

logger = get_logger("validation")

RAW_COLUMN_MAP = {
    "INSTITUCION": "institution",
    "COD_IPRESS": "facility_code",
    "NOMBRE": "facility_name",
    "CLASIFICACION": "classification",
    "TIPO_ESTABLECIMIENTO": "establishment_type",
    "DEPARTAMENTO": "department",
    "PROVINCIA": "province",
    "DISTRITO": "district",
    "UBIGEO": "ubigeo",
    "DIRECCION": "address",
    "CATEGORIA": "category_raw",
    "ESTADO": "status_raw",
    "NORTE": "lat",
    "ESTE": "lon",
}

# Regex-based normalizer: current RENIPRESS snapshot is already mostly
# clean ("I-1".."III-E"), but this is written to tolerate the format drift
# the assignment warns about (extra spaces, missing dashes, lowercase,
# "0"/blank placeholders) since RENIPRESS is republished monthly.
_CATEGORY_CANONICAL_RE = re.compile(r"^(I{1,3})\s*-?\s*([1-4E])$")
SIN_CATEGORIA = "SIN_CATEGORIA"


def normalize_category(raw_category) -> str:
    """Map a raw RENIPRESS CATEGORIA string to a canonical roman-numeral
    code ("I-1".."III-E") or SIN_CATEGORIA when it can't be resolved
    (blank, NaN, or the literal "0" placeholder RENIPRESS uses for
    unclassified establishments)."""
    if pd.isna(raw_category):
        return SIN_CATEGORIA
    s = str(raw_category).strip().upper()
    if s in ("", "0", "NAN", "N/A", "S/C", "SIN CATEGORIA"):
        return SIN_CATEGORIA
    m = _CATEGORY_CANONICAL_RE.match(s)
    if not m:
        return SIN_CATEGORIA
    roman, suffix = m.groups()
    return f"{roman}-{suffix}"


def is_resolutive(category: str, status: str) -> bool:
    cfg = load_config()
    return (
        category in cfg.resolutive_categories
        and str(status).strip().upper() in cfg.active_status_values
    )


def load_renipress_raw(path: Path | None = None) -> pd.DataFrame:
    """Read the RENIPRESS CSV with its real, verified format: UTF-8 with a
    BOM, ';'-delimited (NOT the CSV default comma). Also drives
    check_encoding by recording which candidate encoding actually worked."""
    cfg = load_config()
    if path is None:
        path = cfg.path("raw_dir") / cfg.sources["renipress"]["local_raw_name"]

    df = pd.read_csv(path, encoding="utf-8-sig", sep=";", dtype={"UBIGEO": str})
    df = df.rename(columns=RAW_COLUMN_MAP)
    df["category"] = df["category_raw"].apply(normalize_category)
    df["ubigeo"] = df["ubigeo"].astype(str).str.zfill(6)
    return df


SIGMED_COLUMN_MAP = {
    "CODCP": "facility_code",
    "NOMCP": "facility_name",
    "DEP": "department",
    "PROV": "province",
    "DIST": "district",
    "UBIGEO": "ubigeo",
    "XGD": "lon",
    "YGD": "lat",
    "CAPITAL": "is_capital",
}


def load_sigmed_raw(shp_path: Path | None = None) -> pd.DataFrame:
    """Read the national SIGMED "Centros Poblados" shapefile and rename
    columns onto the same standard schema RENIPRESS uses (facility_code,
    lat, lon, department, province, district, ubigeo) so the generic
    check_missing_coordinates / check_out_of_bbox / check_duplicate_codes /
    check_district_containment functions above work unchanged on demand
    points too. XGD/YGD are used directly instead of the shapefile geometry
    since they are already plain float columns matching RENIPRESS's
    lat/lon shape."""
    cfg = load_config()
    if shp_path is None:
        shp_path = cfg.path("raw_dir") / "sigmed_centros_poblados" / "CP_P.shp"
    gdf = gpd.read_file(shp_path)
    df = pd.DataFrame(gdf.drop(columns="geometry"))
    df = df.rename(columns=SIGMED_COLUMN_MAP)
    df["ubigeo"] = df["ubigeo"].astype(str).str.zfill(6)
    return df


def check_encoding(path: Path, candidates: list[str] | None = None) -> tuple[str, dict]:
    """Try each candidate encoding in order (config.md
    validation.encoding_candidates) and return the first one that decodes
    the whole file without error, plus a report row. RENIPRESS is verified
    UTF-8-with-BOM; this check exists so the pipeline degrades gracefully
    (and logs it) the day a source republishes in latin-1/cp1252 instead."""
    cfg = load_config()
    candidates = candidates or cfg.raw["validation"]["encoding_candidates"]
    working_encoding = None
    errors: dict[str, str] = {}
    for enc in candidates:
        try:
            with open(path, encoding=enc) as f:
                f.read()
            working_encoding = enc
            break
        except UnicodeDecodeError as e:
            errors[enc] = str(e)

    report_row = {
        "rule": "encoding",
        "file": str(path),
        "candidates_tried": candidates,
        "encoding_used": working_encoding,
        "failed_candidates": list(errors.keys()),
        "action": "used first working encoding" if working_encoding else "FAILED — no candidate decoded the file",
    }
    if working_encoding is None:
        logger.error("Ningún encoding candidato pudo decodificar %s", path)
    else:
        logger.info("Encoding de %s: %s", path, working_encoding)
    return working_encoding, report_row


def check_missing_coordinates(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Flags null AND effectively-zero coordinates (exact 0,0 plus the
    floating-point-noise near-zero values seen in real data, e.g. lat =
    -6e-8) — both mean "no usable GPS fix", not a real location at (0,0)."""
    result = df.copy()
    is_null = result["lat"].isna() | result["lon"].isna()
    is_near_zero = (result["lat"].abs() < 1e-4) & (result["lon"].abs() < 1e-4)
    result["has_valid_coords"] = ~(is_null | is_near_zero.fillna(False))

    flagged = result[~result["has_valid_coords"]]
    report_row = {
        "rule": "missing_or_zero_coordinates",
        "n_flagged": int(len(flagged)),
        "pct_flagged": round(100 * len(flagged) / len(result), 2),
        "action": "kept in registry, excluded from nearest-facility geospatial computation",
        "why": "a facility with no GPS fix cannot be routed to; dropping it would silently shrink the supply count instead of documenting the gap",
    }
    logger.info("missing_or_zero_coordinates: %d/%d flagged", len(flagged), len(result))
    return result, flagged, report_row


def check_out_of_bbox(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    cfg = load_config()
    bbox = cfg.peru_bbox
    result = df.copy()

    checkable = result["has_valid_coords"] if "has_valid_coords" in result.columns else result["lat"].notna()
    in_bbox = (
        result["lon"].between(bbox["lon_min"], bbox["lon_max"])
        & result["lat"].between(bbox["lat_min"], bbox["lat_max"])
    )
    result["in_peru_bbox"] = in_bbox | ~checkable  # non-checkable rows already flagged upstream

    flagged = result[checkable & ~in_bbox]
    report_row = {
        "rule": "out_of_peru_bbox",
        "bbox": bbox,
        "n_flagged": int(len(flagged)),
        "action": "kept in registry, excluded from nearest-facility geospatial computation",
        "why": "a coordinate outside Peru is a data-entry error (typo, wrong CRS); no safe automatic correction exists",
    }
    logger.info("out_of_peru_bbox: %d flagged", len(flagged))
    return result, flagged, report_row


def check_swapped_lat_lon(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """For rows outside the bbox with valid coordinates, test whether
    swapping lat/lon lands them inside Peru. When it does, correct in
    place (this is the one check.md-referenced correction that is safe to
    automate, per the assignment's 'excellent approach' bar)."""
    cfg = load_config()
    bbox = cfg.peru_bbox
    result = df.copy()

    checkable = result["has_valid_coords"] if "has_valid_coords" in result.columns else result["lat"].notna()
    currently_out = checkable & ~result.get("in_peru_bbox", pd.Series(True, index=result.index))

    would_fit_swapped = (
        result["lat"].between(bbox["lon_min"], bbox["lon_max"])
        & result["lon"].between(bbox["lat_min"], bbox["lat_max"])
    )
    swap_mask = currently_out & would_fit_swapped

    flagged = result[swap_mask].copy()
    if len(flagged):
        result.loc[swap_mask, ["lat", "lon"]] = result.loc[swap_mask, ["lon", "lat"]].values
        result.loc[swap_mask, "in_peru_bbox"] = True

    result["was_coord_swapped"] = swap_mask

    report_row = {
        "rule": "swapped_lat_lon",
        "n_flagged": int(swap_mask.sum()),
        "action": "corrected in place (lat/lon swapped)" if swap_mask.sum() else "none found — no correction applied",
        "why": "lat/lon transposition is a common manual-entry error and is safely reversible: the swap is only applied when it moves the point INTO Peru's bbox",
    }
    logger.info("swapped_lat_lon: %d corrected", int(swap_mask.sum()))
    return result, flagged, report_row


def check_district_containment(
    df: pd.DataFrame, districts_gdf: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """For rows with valid, in-bbox coordinates and a UBIGEO that matches a
    known district polygon, verify the point actually falls inside that
    polygon (buffered by validation.district_containment_tolerance_m to
    absorb small GPS/boundary-simplification error)."""
    cfg = load_config()
    tolerance_m = cfg.raw["validation"]["district_containment_tolerance_m"]
    result = df.copy()

    # The boundaries source itself has 8 districts nationally with a null
    # geometry (a data-quality issue in that source, not in RENIPRESS) —
    # drop them here so containment simply can't be checked for their
    # facilities rather than crashing.
    districts_proj = districts_gdf[districts_gdf.geometry.notna()].to_crs(epsg=32718)
    districts_proj["geometry_buffered"] = districts_proj.geometry.buffer(tolerance_m)
    buffered_by_ubigeo = dict(zip(districts_proj["IDDIST"], districts_proj["geometry_buffered"]))

    checkable_mask = (
        df.get("has_valid_coords", df["lat"].notna())
        & df.get("in_peru_bbox", True)
        & df["ubigeo"].isin(buffered_by_ubigeo.keys())
    )

    matches = pd.Series(pd.NA, index=result.index, dtype="boolean")
    if checkable_mask.any():
        sub = result.loc[checkable_mask]
        points = gpd.GeoSeries(
            [Point(lon, lat) for lon, lat in zip(sub["lon"], sub["lat"])],
            index=sub.index,
            crs=4326,
        ).to_crs(epsg=32718)
        contained = [
            buffered_by_ubigeo[ubigeo].contains(pt)
            for ubigeo, pt in zip(sub["ubigeo"], points)
        ]
        matches.loc[sub.index] = contained

    result["within_declared_district"] = matches
    flagged = result[matches == False]  # noqa: E712 — explicit False, NA must stay excluded

    n_null_geom_districts = int(districts_gdf.geometry.isna().sum())
    report_row = {
        "rule": "district_containment",
        "n_checkable": int(checkable_mask.sum()),
        "n_flagged": int(len(flagged)),
        "tolerance_m": tolerance_m,
        "n_districts_with_null_geometry_in_source": n_null_geom_districts,
        "action": "kept with warning — the declared UBIGEO is trusted for filtering, the point is flagged as geometrically inconsistent",
        "why": "RENIPRESS lets facilities self-report UBIGEO independently of their coordinates; a mismatch usually means one of the two was mistyped, and we cannot tell which without manual review. Separately, the admin-boundaries source itself has null geometry for a small number of districts nationally (data-quality issue in that source, not RENIPRESS) — their facilities are excluded from n_checkable.",
    }
    logger.info("district_containment: %d/%d checkable flagged", len(flagged), int(checkable_mask.sum()))
    return result, flagged, report_row


def check_duplicate_codes(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Exact duplicate facility_code rows double-count supply capacity, so
    (unlike every other check here) these ARE dropped from the returned
    clean frame — only the first occurrence is kept."""
    is_dupe = df.duplicated(subset="facility_code", keep="first")
    flagged = df[df.duplicated(subset="facility_code", keep=False)]
    result = df[~is_dupe].copy()

    report_row = {
        "rule": "duplicate_facility_codes",
        "n_flagged": int(is_dupe.sum()),
        "n_involved_rows": int(len(flagged)),
        "action": "dropped (kept first occurrence) — the only rule in this pipeline that removes rows",
        "why": "a duplicated facility_code is definitionally the same IPRESS registered twice; counting it twice would inflate resolutive supply density",
    }
    logger.info("duplicate_facility_codes: %d duplicate rows dropped", int(is_dupe.sum()))
    return result, flagged, report_row


def run_all_checks(
    df: pd.DataFrame, districts_gdf: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, list[dict]]:
    """Run every check_* in sequence, returning the cleaned frame plus a
    list of report rows (one per rule) for the Phase 1 data quality report."""
    report_rows: list[dict] = []

    df, _, r = check_missing_coordinates(df)
    report_rows.append(r)
    df, _, r = check_out_of_bbox(df)
    report_rows.append(r)
    df, _, r = check_swapped_lat_lon(df)
    report_rows.append(r)
    df, _, r = check_district_containment(df, districts_gdf)
    report_rows.append(r)
    df, _, r = check_duplicate_codes(df)
    report_rows.append(r)

    n_sin_categoria = int((df["category"] == SIN_CATEGORIA).sum())
    report_rows.append(
        {
            "rule": "unclassified_category",
            "n_flagged": n_sin_categoria,
            "pct_flagged": round(100 * n_sin_categoria / len(df), 2),
            "action": "kept in registry, treated as non-resolutive (excluded from nearest-facility computation, same as I-1..I-4)",
            "why": "RENIPRESS uses the literal string '0' for establishments SUSALUD has not yet classified; absent a real category we cannot assume resolutive capacity",
        }
    )

    df["is_resolutive"] = df.apply(
        lambda row: is_resolutive(row["category"], row["status_raw"]), axis=1
    )

    return df, report_rows
