"""Tables and figures consumed by both the LaTeX report (Phase 5) and the
data quality panel in the dashboard (Phase 4). Figures are written as vector
PDF to report/figures/; tables as booktabs LaTeX + CSV to data/outputs/."""

from __future__ import annotations

import pandas as pd

from src.config import load_config


def run_data_quality_report(report_rows: list[dict]) -> pd.DataFrame:
    """Assemble the Phase 1 validation report rows into one table and write
    it to data/outputs/data_quality_report.csv and logs/data_quality_report.md."""
    cfg = load_config()
    df = pd.DataFrame(report_rows)

    csv_path = cfg.path("outputs_dir") / "data_quality_report.csv"
    df.to_csv(csv_path, index=False)

    md_lines = ["# Reporte de calidad de datos — Fase 1\n"]
    for row in report_rows:
        md_lines.append(f"## {row.get('rule')}\n")
        for k, v in row.items():
            if k == "rule":
                continue
            md_lines.append(f"- **{k}**: {v}")
        md_lines.append("")
    md_path = cfg.path("logs_dir") / "data_quality_report.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    return df


def df_to_latex_table(df: pd.DataFrame, out_name: str, caption: str, label: str) -> None:
    cfg = load_config()
    path = cfg.path("outputs_dir") / f"{out_name}.tex"
    df.to_latex(path, index=False, float_format="%.2f", caption=caption, label=label)


def save_figure(fig, out_name: str) -> None:
    """Save a matplotlib Figure (or a plotly Figure, via its write_image)
    as vector PDF to report/figures/<out_name>.pdf."""
    cfg = load_config()
    path = cfg.path("figures_dir") / f"{out_name}.pdf"
    if hasattr(fig, "savefig"):
        fig.savefig(path, bbox_inches="tight")
    else:
        fig.write_image(str(path))
