# run.ps1 - Golden Hour: puesta en marcha en una maquina limpia (Windows / PowerShell)
#
#   Uso:
#     .\run.ps1              # setup + tests + Fase 3 + dashboard (NO descarga nada)
#     .\run.ps1 -Pipeline    # ademas corre Fases 1 y 2 desde cero (descarga ~256 MB, ~2 h)
#     .\run.ps1 -NoDashboard # setup + tests + Fase 3, sin abrir Streamlit
#
# Requiere Python 3.11 o 3.12 (3.14 rompe el stack geoespacial: fiona no compila).

param(
    [switch]$Pipeline,
    [switch]$NoDashboard
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# --- 1. Encontrar un interprete Python 3.11 / 3.12 --------------------------
$py = $null
foreach ($v in @("3.12", "3.11")) {
    try {
        & py -$v --version *> $null
        if ($LASTEXITCODE -eq 0) { $py = @("py", "-$v"); break }
    } catch {}
}
if (-not $py) {
    Write-Error "No se encontro Python 3.11 o 3.12. Instala con:  winget install Python.Python.3.12"
}
Write-Host "==> Usando: $($py -join ' ')" -ForegroundColor Cyan

# --- 2. Crear el venv si no existe ----------------------------------------
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "==> Creando entorno virtual (.venv)" -ForegroundColor Cyan
    & $py[0] $py[1] -m venv .venv
}
$vpy = ".\.venv\Scripts\python.exe"

# --- 3. Instalar dependencias -------------------------------------------
Write-Host "==> Instalando dependencias (requirements.txt)" -ForegroundColor Cyan
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install -r requirements.txt

# --- 4. Tests ----------------------------------------------------------
Write-Host "==> pytest" -ForegroundColor Cyan
& $vpy -m pytest -q

# --- 5. (opcional) Fases 1 y 2 desde cero -------------------------------
if ($Pipeline) {
    Write-Host "==> Fase 1 - adquisicion + validacion (descarga si hace falta)" -ForegroundColor Cyan
    & $vpy -m src.pipeline_phase1
    Write-Host "==> Fase 2 - ruteo (puede tardar ~2 h la primera vez)" -ForegroundColor Cyan
    & $vpy -m src.pipeline_phase2
}

# --- 6. Fase 3 - metricas + tablas + figuras ----------------------------
Write-Host "==> Fase 3 - metricas, tablas y figuras" -ForegroundColor Cyan
& $vpy -m src.pipeline_phase3

# --- 7. Dashboard ----------------------------------------------------
if (-not $NoDashboard) {
    Write-Host "==> Abriendo el dashboard (Ctrl+C para detener)" -ForegroundColor Green
    & $vpy -m streamlit run app.py
}
