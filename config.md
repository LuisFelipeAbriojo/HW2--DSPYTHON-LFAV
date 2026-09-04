# Configuración del proyecto — "Golden Hour"

Este archivo es la **única fuente de verdad** para todos los parámetros del pipeline
(Fases 1–5) y del dashboard de Streamlit. Ningún módulo en `src/` debe tener rutas,
departamentos, umbrales o listas de categorías escritos directamente en el código:
todos se leen desde el bloque YAML de abajo mediante `src/config.py`.

Para cambiar de departamentos, engine de ruteo o umbrales, se edita **solo este
archivo** — no hace falta tocar código.

## Alcance del análisis

Tres departamentos, uno por región geográfica, según lo exigido por el enunciado:

| Región     | Departamento | Justificación |
|------------|--------------|----------------|
| Costa      | Lambayeque   | Alta densidad poblacional, red vial relativamente completa en OSM. |
| Andina     | Cusco        | Relieve fuerte, buena cobertura OSM (turismo), permite comparar car-vs-foot en terreno accidentado. |
| Amazónica  | Loreto       | Caso extremo de desconexión vial — gran parte del territorio no tiene carreteras, solo ríos. Es el caso más interesante para el hallazgo del proyecto. |

## Motor de ruteo

**OSMnx + NetworkX**, sin Docker/OSRM. Justificación: la máquina de desarrollo no
tiene Docker Desktop ni WSL2 instalados, y levantarlos exige reinicio del sistema y
permisos de administrador. OSMnx + NetworkX es 100% Python, se instala con `pip`, y
es viable computacionalmente para 3 departamentos dentro del límite de 5,000 puntos
de demanda fijado más abajo. Todo resultado de ruteo se cachea en disco
(`data/processed/routing_matrix_*.parquet`) para que una segunda corrida no
recompute nada.

---

```yaml
# ============================================================
# BLOQUE MÁQUINA-LEGIBLE — parseado por src/config.py
# ============================================================

project:
  name: "golden-hour"
  random_seed: 42

departments:
  - name: Lambayeque
    ubigeo_dep: "14"
    region_type: coastal
  - name: Cusco
    ubigeo_dep: "08"
    region_type: andean
  - name: Loreto
    ubigeo_dep: "16"
    region_type: amazonian

paths:
  raw_dir: "data/raw"
  processed_dir: "data/processed"
  outputs_dir: "data/outputs"
  cache_dir: "data/cache"
  logs_dir: "logs"
  report_dir: "report"
  figures_dir: "report/figures"

sources:
  renipress:
    # Portal CKAN de datosabiertos.gob.pe publica un CSV nuevo cada mes; la
    # URL de "último mes" no es predecible por patrón porque el nombre de
    # archivo lleva la fecha exacta de publicación. Por eso acquisition.py
    # resuelve la URL vigente vía la API CKAN package_show en vez de tenerla
    # fija aquí. Verificada manualmente el 2026-09-04 (archivo de agosto
    # 2026, 19.7 MB): https://www.datosabiertos.gob.pe/sites/default/files/RENIPRESS_31-08-2026.csv
    dataset_page_url: "https://www.datosabiertos.gob.pe/dataset/registro-nacional-de-entidades-prestadoras-de-servicios-de-salud-renipress"
    ckan_api_url: "https://www.datosabiertos.gob.pe/api/3/action/package_show?id=registro-nacional-de-entidades-prestadoras-de-servicios-de-salud-renipress"
    license: "Open Data Commons Attribution License — SUSALUD"
    local_raw_name: "renipress_raw.csv"
    # El portal está detrás de un WAF que bloquea el User-Agent por defecto
    # de curl/requests (HTTP 418 "posible ataque"). Con un User-Agent de
    # navegador responde 200 normalmente. acquisition.py debe enviar ese
    # header siempre.
    requires_browser_user_agent: true
  sigmed:
    # sigmed.minedu.gob.pe/descargas/ es una app interactiva sin URL de
    # descarga directa visible en el HTML; el botón "Descarga Centros
    # Poblados" dispara esta petición (confirmada inspeccionando la red del
    # navegador el 2026-09-04, 12.18 MB, archivo de un único shapefile a
    # nivel nacional que hay que filtrar a los 3 departamentos en el
    # pipeline). La página anuncia "Actualizado al 05/02/2020" pero el
    # Last-Modified real del servidor es 2021-12-10 — se documenta la
    # discrepancia en el reporte de calidad de datos.
    url: "https://sigmed.minedu.gob.pe/descargas/archivos/CP_MED.zip"
    license: "MINEDU — dato público, ver portal"
    local_raw_name: "sigmed_centros_poblados.zip"
    requires_browser_user_agent: false
  osm_pbf:
    url: "https://download.geofabrik.de/south-america/peru-latest.osm.pbf"
    license: "ODbL — OpenStreetMap contributors"
    local_raw_name: "peru-latest.osm.pbf"
    requires_browser_user_agent: false
  admin_boundaries:
    # INEI no publica un enlace de descarga directa estable para los
    # polígonos distritales. Se usa el GeoJSON derivado de cartografía INEI
    # republicado en el repositorio público juaneladio/peru-geojson (fuente
    # estándar en proyectos de ciencia de datos sobre Perú), verificado el
    # 2026-09-04 (1.87 MB). Esta sustitución se documenta como hallazgo
    # legítimo sobre el estado de los datos abiertos peruanos, tal como
    # contempla el enunciado.
    url: "https://raw.githubusercontent.com/juaneladio/peru-geojson/master/peru_distrital_simple.geojson"
    license: "Datos INEI, republicados por terceros — ver repositorio de origen"
    local_raw_name: "limites_distritales.geojson"
    requires_browser_user_agent: false

# --- Definición de capacidad resolutiva (Fase 1) ---
resolutive_categories:
  - "II-1"
  - "II-2"
  - "II-E"
  - "III-1"
  - "III-2"
  - "III-E"

non_resolutive_categories:
  - "I-1"
  - "I-2"
  - "I-3"
  - "I-4"

# Valores de "estado" en RENIPRESS que cuentan como activo, ya normalizados
# a mayúsculas/sin tildes. La normalización real (regex, mapeo) vive en
# src/validation.py — esta lista es la whitelist que consume esa función.
# Verificado contra los 36,004 registros reales del CSV de agosto 2026: los
# 7 valores distintos de ESTADO son ACTIVO, CIERRE TEMPORAL DE OFICIO, BAJA
# DEFINITIVA, BAJA PROVISIONAL, BAJA DEFINITIVA DE OFICIO, BAJA PROVISIONAL
# DE OFICIO, CIERRE TEMPORAL DE PARTE. Solo ACTIVO cuenta como operativo.
active_status_values:
  - "ACTIVO"

# --- Reglas de validación (Fase 1) ---
validation:
  peru_bbox:
    lon_min: -81.4
    lon_max: -68.6
    lat_min: -18.4
    lat_max: -0.04
  duplicate_key_field: "codigo_renipress"
  encoding_candidates: ["utf-8", "latin-1", "cp1252"]
  district_containment_tolerance_m: 500  # margen antes de marcar "fuera del polígono declarado"

# --- Ruteo (Fase 2) ---
routing:
  engine: "osmnx_networkx"
  profiles: ["car", "foot", "bike"]
  # Velocidades usadas cuando OSM no trae "maxspeed" en la vía (km/h)
  fallback_speeds_kmh:
    car: 40
    bike: 12
    foot: 4.5
  max_demand_points: 5000
  sampling_strategy: "population_weighted"  # aplica solo si se excede max_demand_points
  urban_walk_analysis: true  # walking analizado solo para puntos de demanda urbanos
  straight_line_detour_factor_default: 1.3  # solo como fallback documentado; se valida empíricamente contra rutas reales

# --- Métricas (Fase 3) ---
metrics:
  coverage_bands_minutes: [30, 60, 120]
  inequality_measure: "gini"
  urban_rural_rule: "centro poblado con >= 2000 habitantes y clasificado 'urbano' en SIGMED"
  cross_analysis_secondary_dimension: "poverty_rate"

# --- Dashboard (Fase 4) ---
dashboard:
  default_time_threshold_minutes: 60
  simulator_upgradeable_categories: ["I-3", "I-4"]
```
