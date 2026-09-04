# -*- coding: utf-8 -*-
"""One-time extraction of total district population from the INEI Censo
2017 Tomo I "CUADRO N 1" (POBLACION CENSADA, POR AREA URBANA Y RURAL; Y
SEXO, SEGUN PROVINCIA, DISTRITO Y EDADES SIMPLES) for Lambayeque, Cusco and
Loreto.

Why this lives in scripts/ and not src/: SIGMED's "Centros Poblados" demand
layer (data/raw/sigmed_centros_poblados/) has no population field, and no
machine-readable population-by-district dataset was found on
datosabiertos.gob.pe (its CKAN package_search endpoint is not enabled on
that deployment). INEI only publishes this as scanned-layout PDFs per
department, so this is a one-time, source-specific extraction rather than a
re-runnable pipeline step — the 2017 census won't change. Output feeds
src/metrics.py's population weighting (config.md metrics block).

Approach:
- The relevant pages are physically rotated (rotation=270) in the source
  PDF. We counter-rotate each page (+90) with pypdf so pdfplumber can read
  words in correct left-to-right / top-to-bottom order with reliable x/y
  coordinates.
- For each page we locate the header words 'Total' and 'Hombres' (leftmost
  instances = the "Poblacion" group) to compute the x-band of the first
  numeric column (Total poblacion), since thousands-separator spaces make
  naive whitespace tokenisation of the number ambiguous.
- Words are clustered into visual rows by their 'top' coordinate.
- For each row, words whose x0 falls inside the Total-poblacion x-band and
  are purely digits are concatenated (no thousands separator) to form the
  integer value; all other (non-digit) words to the left form the row
  label.
- Rows are classified as DEPARTAMENTO / PROVINCIA / DISTRITO (no digits, no
  "ano"/"anos" in the label) vs. age-breakdown rows (skipped).
- Every DISTRITO row is cross-checked: sum of districts must equal the
  PROVINCIA row printed in the same table, and sum of provinces must equal
  the DEPARTAMENTO row — this is a real arithmetic check against the
  source PDF, not a plausibility guess. A department is only written to
  CSV if every province balances exactly.

Page ranges (`start`/`end`) were located manually by scanning each PDF's
Tomo I for "CUADRO N 1" and its end (start of "CUADRO N 2"); see the
project's data quality notes for the exact page numbers.

Requires: pdfplumber, pypdf (not in the main requirements.txt — this
script runs once and its output is committed to data/raw/, so those
packages are not a dependency of the regular pipeline).

Usage: python scripts/extract_population_by_district.py [lambayeque|cusco|loreto]
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber
from pypdf import PdfReader, PdfWriter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW = PROJECT_ROOT / "data" / "raw"
CACHE_DIR = RAW / "_population_extraction_cache"

DEPARTMENTS = {
    "lambayeque": {
        "pdf": RAW / "censo2017_lambayeque_tomo1.pdf",
        "start": 61,
        "end": 193,  # CUADRO N 2 starts at 194
        "csv": RAW / "poblacion_distrital_lambayeque_2017.csv",
        "nombdep": "LAMBAYEQUE",
    },
    "cusco": {
        "pdf": RAW / "censo2017_cusco_tomo1.pdf",
        "start": 65,
        "end": 471,  # CUADRO N 2 starts at 472
        "csv": RAW / "poblacion_distrital_cusco_2017.csv",
        "nombdep": "CUSCO",
    },
    "loreto": {
        "pdf": RAW / "censo2017_loreto_tomo1.pdf",
        "start": 65,
        "end": 258,  # CUADRO N 2 starts at 259
        "csv": RAW / "poblacion_distrital_loreto_2017.csv",
        "nombdep": "LORETO",
    },
}

AGE_HINTS = ("ANO", "ANOS")  # after accent-stripping "año"/"años" -> "ANO"/"ANOS"


def strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def norm(s: str) -> str:
    s = strip_accents(s).upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def title_es(s: str) -> str:
    words = s.split()
    small = {"de", "del", "la", "las", "los", "y"}
    out = []
    for i, w in enumerate(words):
        wl = w.lower()
        out.append(wl if i > 0 and wl in small else wl[:1].upper() + wl[1:])
    return " ".join(out)


def is_age_or_junk_label(label_norm: str) -> bool:
    if not label_norm:
        return True
    if any(ch.isdigit() for ch in label_norm):
        return True
    return any(t in AGE_HINTS for t in label_norm.split())


def build_rotated_pdf(src_pdf: Path, start: int, end: int, out_pdf: Path) -> None:
    reader = PdfReader(str(src_pdf))
    writer = PdfWriter()
    for i in range(start - 1, end):
        page = reader.pages[i]
        page.rotate(90)
        writer.add_page(page)
    with open(out_pdf, "wb") as f:
        writer.write(f)


def cluster_rows(words, tol: float = 4.0):
    words_sorted = sorted(words, key=lambda w: w["top"])
    rows, current, last_top = [], [], None
    for w in words_sorted:
        if last_top is None or (w["top"] - last_top) <= tol:
            current.append(w)
        else:
            rows.append(current)
            current = [w]
        last_top = w["top"] if last_top is None else max(last_top, w["top"])
    if current:
        rows.append(current)
    return rows


def extract_entries(key: str, cfg: dict) -> list[tuple[str, str, int | None, int]]:
    print(f"\n=== {key.upper()}: extrayendo Cuadro N 1 (paginas {cfg['start']}-{cfg['end']}) ===", flush=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    rotated_pdf = CACHE_DIR / f"{key}_rotated_cuadro1.pdf"
    build_rotated_pdf(cfg["pdf"], cfg["start"], cfg["end"], rotated_pdf)

    entries: list[tuple[str, str, int | None, int]] = []
    last_bounds = None
    anomalies = []

    with pdfplumber.open(str(rotated_pdf)) as pdf:
        for idx, page in enumerate(pdf.pages):
            page_no = cfg["start"] + idx
            words = [w for w in page.extract_words() if w.get("upright", True)]
            if not words:
                continue

            total_hdrs = sorted([w for w in words if w["text"] == "Total"], key=lambda w: w["x0"])
            hombres_hdrs = sorted([w for w in words if w["text"] == "Hombres"], key=lambda w: w["x0"])

            if total_hdrs and hombres_hdrs:
                total_hdr, hombres_hdr = total_hdrs[0], hombres_hdrs[0]
                gap = hombres_hdr["x0"] - total_hdr["x1"]
                col1_left = total_hdr["x0"] - gap
                col1_right = (total_hdr["x1"] + hombres_hdr["x0"]) / 2.0
                last_bounds = (col1_left, col1_right)
            elif last_bounds is not None:
                col1_left, col1_right = last_bounds
            else:
                anomalies.append((page_no, "NO_HEADER_FOUND"))
                continue

            header_bottom = 0.0
            for w in words:
                if w["text"] in ("Hombres", "Mujeres") and w["top"] < 130:
                    header_bottom = max(header_bottom, w["bottom"])
            header_bottom = header_bottom or 120.0

            data_words = [w for w in words if w["top"] > header_bottom + 3]
            if not data_words:
                continue

            for row in cluster_rows(data_words, tol=4.0):
                row_sorted = sorted(row, key=lambda w: w["x0"])
                col1_tokens = [
                    w for w in row_sorted
                    if w["text"].isdigit() and (col1_left - 2) <= w["x0"] <= (col1_right + 2)
                ]
                label_tokens = [w for w in row_sorted if w["x0"] < col1_left]
                label = re.sub(r"\s+", " ", " ".join(w["text"] for w in label_tokens)).strip()
                if not label:
                    continue

                value = None
                if col1_tokens:
                    digits = "".join(w["text"] for w in col1_tokens)
                    if digits.isdigit():
                        value = int(digits)

                lab_norm = norm(label)
                if lab_norm.startswith("DEPARTAMENTO "):
                    entries.append(("DEPARTAMENTO", label, value, page_no))
                elif lab_norm.startswith("PROVINCIA "):
                    entries.append(("PROVINCIA", label, value, page_no))
                elif is_age_or_junk_label(lab_norm):
                    continue
                else:
                    entries.append(("DISTRITO", label, value, page_no))

    if anomalies:
        print(f"  ADVERTENCIA — paginas sin encabezado detectado: {anomalies[:10]}", flush=True)

    dump_path = CACHE_DIR / f"{key}_raw_entries.json"
    dump_path.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    return entries


def load_ubigeo_map(nombdep: str) -> dict[str, str]:
    gj_path = RAW / "limites_distritales.geojson"
    with open(gj_path, encoding="utf-8") as f:
        gj = json.load(f)
    return {
        norm(feat["properties"]["NOMBDIST"]): feat["properties"]["IDDIST"]
        for feat in gj["features"]
        if norm(feat["properties"]["NOMBDEP"]) == norm(nombdep)
    }


def build_csv(key: str, cfg: dict, entries: list[tuple[str, str, int | None, int]]) -> None:
    ubigeo_map = load_ubigeo_map(cfg["nombdep"])

    dept_total = None
    current_prov = None
    prov_check: dict[str, dict] = {}
    rows_out = []
    unmatched_geo = []

    for kind, label, value, _page in entries:
        if kind == "DEPARTAMENTO":
            dept_total = value
            continue
        if kind == "PROVINCIA":
            current_prov = label[len("PROVINCIA "):].strip()
            prov_check[current_prov] = {"declared": value, "dist_sum": 0}
            continue
        dist_name = label[len("DISTRITO "):].strip() if label.startswith("DISTRITO ") else label
        prov_check[current_prov]["dist_sum"] += value or 0
        ubigeo = ubigeo_map.get(norm(dist_name), "")
        if not ubigeo:
            unmatched_geo.append(dist_name)
        rows_out.append(
            {
                "departamento": title_es(cfg["nombdep"]),
                "provincia": title_es(current_prov),
                "distrito": title_es(dist_name),
                "poblacion_2017": value if value is not None else "",
                "ubigeo": ubigeo,
            }
        )

    prov_mismatches = [p for p, v in prov_check.items() if v["declared"] != v["dist_sum"]]
    total_sum = sum(r["poblacion_2017"] for r in rows_out if r["poblacion_2017"] != "")
    n_missing = sum(1 for r in rows_out if r["poblacion_2017"] == "")

    print(f"  Distritos extraidos: {len(rows_out)}")
    print(f"  Suma poblacion distrital: {total_sum:,}")
    print(f"  Total DEPARTAMENTO (tabla PDF): {dept_total:,}" if dept_total else "  Total DEPARTAMENTO: N/A")
    print(f"  Provincias con mismatch interno (declared vs suma distritos): {prov_mismatches}")
    print(f"  Distritos sin ubigeo (creados despues del corte de limites_distritales.geojson) [{len(unmatched_geo)}]: {unmatched_geo}")
    print(f"  Filas con poblacion_2017 vacio: {n_missing}")

    if dept_total is not None and total_sum != dept_total:
        raise ValueError(
            f"{key}: la suma de distritos ({total_sum}) no coincide con el total de departamento "
            f"impreso en el PDF ({dept_total}) — no se escribe el CSV, revisar extraccion."
        )
    if prov_mismatches:
        raise ValueError(f"{key}: provincias con suma de distritos inconsistente: {prov_mismatches}")

    with open(cfg["csv"], "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["departamento", "provincia", "distrito", "poblacion_2017", "ubigeo"])
        for r in rows_out:
            writer.writerow([r["departamento"], r["provincia"], r["distrito"], r["poblacion_2017"], r["ubigeo"]])
    print(f"  Escrito: {cfg['csv']}")


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for key, cfg in DEPARTMENTS.items():
        if only and key != only:
            continue
        entries = extract_entries(key, cfg)
        build_csv(key, cfg, entries)


if __name__ == "__main__":
    main()
