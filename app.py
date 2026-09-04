"""Phase 4 — Streamlit dashboard. Reads only precomputed files from
data/processed/ and data/outputs/; never calls a routing engine or rebuilds a
graph at load time (see config.md and src/routing.py for how those files are
produced ahead of time)."""

from __future__ import annotations

import streamlit as st

from src.config import load_config

st.set_page_config(page_title="Golden Hour — Acceso a salud resolutiva", layout="wide")

cfg = load_config()

st.title("Golden Hour: acceso vial a salud resolutiva")
st.caption(
    f"Departamentos en alcance: {', '.join(cfg.department_names)} · "
    f"Motor de ruteo: {cfg.routing['engine']}"
)

st.info(
    "Estructura base del dashboard. Las vistas (KPIs, mapa coroplético, capa de "
    "establecimientos, distribución, ranking, simulador de escenarios y panel de "
    "calidad de datos) se implementan en la Fase 4, una vez que existan los "
    "archivos precomputados en data/processed/ y data/outputs/."
)
