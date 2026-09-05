# Golden Hour — Acceso vial a salud resolutiva en Perú

Proyecto integrador (Ciencia de Datos, 2026-II): estimar cuánto tarda, por
carretera, la población de tres departamentos peruanos en llegar a un
establecimiento de salud con capacidad resolutiva (categoría II-1 en
adelante), e identificar dónde están las peores brechas de acceso.

Todos los parámetros del proyecto — departamentos en alcance, motor de
ruteo, categorías resolutivas, umbrales de cobertura, rutas de datos — están
declarados en [`config.md`](config.md) y son editables sin tocar código.

## Alcance actual

| Región    | Departamento |
|-----------|--------------|
| Costa     | Lambayeque   |
| Andina    | Cusco        |
| Amazónica | Loreto       |

## Estado del proyecto

- [x] Entorno y estructura del repositorio
- [x] Fase 1 — Adquisición y validación de datos (3{,}631 establecimientos,
  21{,}095 centros poblados, reporte de calidad en `data/outputs/data_quality_report.csv`)
- [x] Fase 2 — Ruteo y matriz de tiempos de viaje (auto/bici/a pie, 3
  departamentos, 100\% offline — ver `config.md`)
- [x] Fase 3 — Construcción de métricas (cobertura, Gini, brechas críticas,
  cruce con ruralidad, línea recta vs.\ red vial, comparación entre modos)
- [x] Fase 4 — Dashboard en Streamlit (KPIs, mapa coroplético, capa de
  establecimientos, distribución, ranking, simulador de escenarios, panel
  de calidad de datos)
- [x] Fase 5 — Reporte en LaTeX (`report/main.tex` + `report/main.pdf`, 11
  páginas)
- [ ] Video de presentación (a cargo del estudiante, ver enunciado)

## Estructura del repositorio

```
├── config.md               # única fuente de verdad de parámetros
├── requirements.txt
├── src/
│   ├── config.py            # loader de config.md
│   ├── logging_utils.py     # logging consistente a stdout + logs/
│   ├── acquisition.py       # Fase 1 — descarga (RENIPRESS, SIGMED, OSM, límites)
│   ├── validation.py        # Fase 1 — reglas de calidad de datos
│   ├── routing.py           # Fase 2 — motor de ruteo (OSMnx + NetworkX) + caché
│   ├── metrics.py           # Fase 3 — métricas de acceso
│   └── export.py            # tablas/figuras para el reporte y el dashboard
├── data/
│   ├── raw/                 # descargas crudas (no versionadas, ver .gitignore)
│   ├── processed/           # GeoParquet/GeoPackage limpios + matrices de ruteo
│   └── outputs/             # CSV y tablas LaTeX finales
├── app.py                   # Fase 4 — dashboard Streamlit
├── report/
│   ├── main.tex              # Fase 5
│   └── figures/
├── logs/                    # incluye el reporte de calidad de datos
└── tests/
```

## Instalación

Requiere Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Ejecución

```bash
# Fase 1 — descarga (idempotente) + validación + GeoParquet en data/processed/
python -m src.pipeline_phase1

# Fase 2 — ruteo (auto/bici/a pie, 3 departamentos). Tarda ~1h50 la primera
# vez (grafos de Cusco/Loreto son grandes); las corridas siguientes son
# instantáneas gracias al caché en data/cache/graphs/ y data/processed/.
python -m src.pipeline_phase2

# Fase 3 — métricas + tablas/figuras para el reporte
python -m src.pipeline_phase3

# Tests
pytest

# Dashboard (lee únicamente los archivos precomputados de arriba)
streamlit run app.py
```

Para recompilar el reporte (Fase 5) hace falta una distribución de LaTeX
(este proyecto usa [MiKTeX](https://miktex.org/), instalado con
`winget install MiKTeX.MiKTeX`, sin necesidad de permisos de administrador):

```bash
cd report
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex   # segunda pasada, referencias cruzadas
```

## Fuentes de datos

Declaradas con URL y licencia en `config.md` (bloque `sources`):

- **Oferta** (RENIPRESS/SUSALUD): establecimientos de salud y su categoría/estado.
- **Demanda** (MINEDU/SIGMED): centros poblados georreferenciados.
- **Red vial** (OpenStreetMap / Geofabrik): extracto de Perú.
- **Límites administrativos**: distrito/provincia/departamento — fuente exacta y
  fecha de descarga documentadas en `logs/` al momento de correr `src.acquisition`.

## Motor de ruteo

Grafos viales construidos **localmente desde el extracto OSM de Perú**
(`data/raw/peru-latest.osm.pbf`) vía el driver `OSM` de GDAL
(`pyogrio`/`fiona`), enrutados con Dijkstra de NetworkX — sin Docker/OSRM
ni llamadas a Overpass API en tiempo de ejecución. Ver `config.md` para la
justificación completa: se intentó primero `pyrosm` (descartado por
requerir compilador de C++) y luego Overpass API en vivo (descartado tras
fallar repetidamente en la práctica — un espejo cayó, otro devolvía
resultados vacíos). Resultados cacheados en `data/cache/graphs/` y
`data/processed/`.

## Licencia de los datos

Cada fuente conserva su propia licencia (ver `config.md`); este repositorio
no redistribuye los archivos crudos por su tamaño — `src/acquisition.py` los
regenera localmente en `data/raw/`.
