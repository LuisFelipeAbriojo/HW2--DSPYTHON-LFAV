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
    url: "https://www.datosabiertos.gob.pe/dataset/registro-nacional-de-entidades-prestadoras-de-servicios-de-salud-renipress"
    license: "Datos Abiertos Perú — ODbL-like, ver portal"
    local_raw_name: "renipress_raw.csv"
  sigmed:
    url: "https://sigmed.minedu.gob.pe/descargas/"
    license: "MINEDU — dato público, ver portal"
    local_raw_name: "sigmed_centros_poblados.csv"
  osm_pbf:
    url: "https://download.geofabrik.de/south-america/peru-latest.osm.pbf"
    license: "ODbL — OpenStreetMap contributors"
    local_raw_name: "peru-latest.osm.pbf"
  admin_boundaries:
    # Fuente declarada y citada en el reporte (Fase 5): INEI / Geo GPS Perú.
    # URL exacta y fecha de descarga se documentan en logs/data_quality_report.md
    # una vez descargada, por si el portal cambia de dirección.
    url: "TBD — se documenta al momento de la descarga (Fase 1, día 1)"
    license: "INEI — dato público"
    local_raw_name: "limites_distritales.gpkg"

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
active_status_values:
  - "ACTIVO"
  - "EN FUNCIONAMIENTO"

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
