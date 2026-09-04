"""Tables and figures consumed by both the LaTeX report (Phase 5) and the
data quality panel in the dashboard (Phase 4). Figures are written as vector
PDF to report/figures/; tables as booktabs LaTeX to data/outputs/ and as CSV."""

from __future__ import annotations

import pandas as pd

from src.config import load_config


def run_data_quality_report(report_rows: list[dict]) -> pd.DataFrame:
    """Assemble the Phase 1 validation report rows into one table and write
    it to data/outputs/data_quality_report.csv + logs/."""
    raise NotImplementedError


def df_to_latex_table(df: pd.DataFrame, out_name: str, caption: str, label: str) -> None:
    """Write df.to_latex(..., booktabs=True) to data/outputs/<out_name>.tex."""
    raise NotImplementedError


def save_figure(fig, out_name: str) -> None:
    """Save a matplotlib/plotly figure as vector PDF to report/figures/<out_name>.pdf."""
    raise NotImplementedError
