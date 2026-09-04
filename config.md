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

**Construcción del grafo**: originalmente se planeaba construir los grafos
directamente desde `data/raw/peru-latest.osm.pbf` (ya descargado) usando `pyrosm`,
para evitar depender de Overpass API. Se descartó: `pyrosm` depende de `cykhash`,
que no tiene wheel precompilado para Windows/Python 3.11 y requiere un compilador
de C++ (Microsoft Visual C++ Build Tools) no instalado en esta máquina — instalarlo
es un cambio de sistema pesado, igual que Docker/WSL2, así que se evita por la misma
razón. En su lugar se usa `osmnx.graph_from_polygon()` directamente contra Overpass
API (descarga en vivo, con caché en disco vía `ox.settings.cache_folder =
"data/cache/osmnx"`, así que una segunda corrida no repite peticiones). El .pbf ya
descargado queda documentado como fuente pero no se usa como input directo del
grafo. Verificado el 2026-09-04: Lambayeque (grafo "drive") tardó ~5 minutos y
produjo 44,020 nodos / 123,182 aristas tras simplificación y quedarse con la
componente conexa más grande.

Resiliencia ante fallos de Overpass: durante la corrida real del 2026-09-04, la
instancia principal (overpass-api.de) dejó de responder a mitad de la Fase 2
(reset de conexión / SSL EOF en todos los reintentos) mientras el resto de
internet seguía accesible con normalidad, confirmando que era un problema del
servidor y no de la red local. src/routing.py reintenta cada mirror con
backoff (20s, 45s) y, si se agotan, hace failover al siguiente espejo público
de la lista (overpass-api.de -> overpass.kumi.systems -> overpass.osm.ch),
verificados accesibles ese mismo día. src/pipeline_phase2.py además envuelve
cada bloque car/foot/bike en try/except: un fallo en un perfil no bota el
resto de la corrida, y una segunda ejecución retoma desde lo que ya está
cacheado en disco.

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
  population_census2017:
    # SIGMED "Centros Poblados" (fuente de demanda) no trae población por
    # punto, y datosabiertos.gob.pe no tiene un dataset de población
    # distrital descargable en CKAN (su endpoint package_search no está
    # habilitado). INEI solo publica el Censo 2017 como PDFs por
    # departamento (sin CSV). Se extrajo una única vez con
    # scripts/extract_population_by_district.py (no forma parte del
    # pipeline reproducible regular — requiere pdfplumber/pypdf, no
    # incluidos en requirements.txt — porque el censo 2017 es un dato
    # estático que no cambia entre corridas).
    tomo1_urls:
      lambayeque: "https://www.inei.gob.pe/media/MenuRecursivo/publicaciones_digitales/Est/Lib1560/14TOMO_01.pdf"
      cusco: "https://www.inei.gob.pe/media/MenuRecursivo/publicaciones_digitales/Est/Lib1559/08TOMO_01.pdf"
      loreto: "https://www.inei.gob.pe/media/MenuRecursivo/publicaciones_digitales/Est/Lib1561/16TOMO_01.pdf"
    # "CUADRO N 1: POBLACION CENSADA, POR AREA URBANA Y RURAL; Y SEXO,
    # SEGUN PROVINCIA, DISTRITO Y EDADES SIMPLES" — solo se tomó la
    # columna Total. Verificado el 2026-09-04: la suma de distritos
    # coincide exactamente con el total impreso de cada provincia y
    # departamento (0 discrepancias) en los 3 departamentos.
    cuadro1_pages:
      lambayeque: "61-193"
      cusco: "65-471"
      loreto: "65-258"
    license: "INEI — Censos Nacionales 2017, dato público"
    local_raw_names:
      lambayeque: "poblacion_distrital_lambayeque_2017.csv"
      cusco: "poblacion_distrital_cusco_2017.csv"
      loreto: "poblacion_distrital_loreto_2017.csv"
    # Cusco: 4 distritos (Inkawasi, Villa Virgen, Villa Kintiarina,
    # Megantoni — todos de La Convención) y Loreto: 2 distritos (Rosa
    # Panduro, Yaguas, de Putumayo) fueron creados/reconocidos después del
    # corte de limites_distritales.geojson: su población 2017 SÍ se
    # extrajo correctamente, pero su columna ubigeo queda vacía (no se
    # inventa). Se documenta como limitación en el reporte.

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
  urban_rural_rule: "centro poblado con población estimada >= urban_pop_threshold, o marcado CAPITAL=1 (capital distrital) en SIGMED"
  urban_pop_threshold: 2000
  # De las opciones sugeridas por el enunciado (poverty rate, rurality,
  # población bajo 5, altitud), se eligió "rurality" porque es la única
  # que se puede calcular directamente de datos ya en mano (is_urban de
  # src/sampling.py, ponderado por population_est) sin adquirir una fuente
  # adicional. No se afirma causalidad: ver reporte, sección Discusión.
  cross_analysis_secondary_dimension: "rurality"

# --- Dashboard (Fase 4) ---
dashboard:
  default_time_threshold_minutes: 60
  simulator_upgradeable_categories: ["I-3", "I-4"]
```
