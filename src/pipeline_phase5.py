"""Phase 5: automated report generation. Regenerates
report/generated_stats.tex from whatever Phase 3 last wrote to
data/outputs/, then compiles report/main.tex to a fresh PDF -- two
pdflatex passes (the first resolves cross-references/citations, the
second prints them), same as the manual recipe in the README, just
scripted and with the log actually checked for failure instead of
trusting a 0 exit code.

This is the step that makes "the data changed" (a fresh Phase 1-3 run,
whether from an updated source or a different set of departments in
config.md) turn into an updated PDF without anyone hand-copying numbers
into main.tex. It does NOT rewrite the report's prose -- see
src/report_stats.py's docstring and docs/adding_a_department.md for why
that stays a manual/LLM-assisted step.

Run with: python -m src.pipeline_phase5
"""

from __future__ import annotations

import shutil
import subprocess
import sys

from src import report_stats
from src.config import load_config
from src.logging_utils import get_logger

logger = get_logger("pipeline_phase5")

_ERROR_LINE_PREFIX = "!"


def _find_pdflatex() -> str:
    exe = shutil.which("pdflatex")
    if exe:
        return exe
    raise FileNotFoundError(
        "pdflatex no está en el PATH. Este proyecto usa MiKTeX "
        "(winget install MiKTeX.MiKTeX); si acabas de instalarlo, abre una "
        "terminal nueva para que el PATH se actualice."
    )


def _run_pdflatex(pdflatex: str, report_dir) -> subprocess.CompletedProcess:
    return subprocess.run(
        [pdflatex, "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
        cwd=report_dir,
        capture_output=True,
        text=True,
    )


def compile_report() -> bool:
    """Returns True iff main.pdf came out clean (no '!' error lines in
    main.log). A pdflatex exit code of 0 is necessary but NOT sufficient --
    with -halt-on-error a real LaTeX error still exits non-zero, but a
    missing \\input file or a broken reference can print a warning and a
    zero exit code, so the log is checked explicitly either way."""
    cfg = load_config()
    report_dir = cfg.path("report_dir")
    pdflatex = _find_pdflatex()

    logger.info("Compilando %s (pasada 1/2)...", report_dir / "main.tex")
    _run_pdflatex(pdflatex, report_dir)
    logger.info("Compilando %s (pasada 2/2, referencias cruzadas)...", report_dir / "main.tex")
    result = _run_pdflatex(pdflatex, report_dir)

    log_path = report_dir / "main.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    error_lines = [line for line in log_text.splitlines() if line.startswith(_ERROR_LINE_PREFIX)]

    pdf_path = report_dir / "main.pdf"
    if error_lines or not pdf_path.exists():
        logger.error("La compilación falló. Errores en main.log:")
        for line in error_lines[:10]:
            logger.error("  %s", line)
        if result.returncode != 0:
            logger.error("pdflatex salió con código %d. stderr:\n%s", result.returncode, result.stdout[-2000:])
        return False

    logger.info("Reporte compilado sin errores: %s", pdf_path)
    return True


def run() -> None:
    logger.info("Fase 5, paso 1/2: recalculando macros desde data/outputs/...")
    report_stats.generate()
    logger.info("Fase 5, paso 2/2: compilando el PDF...")
    ok = compile_report()
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    run()
