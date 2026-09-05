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

**OSMnx (formato de grafo) + NetworkX (Dijkstra)**, sin Docker/OSRM. Justificación: la
máquina de desarrollo no tiene Docker Desktop ni WSL2 instalados, y levantarlos exige
reinicio del sistema y permisos de administrador. Es 100% Python, se instala con
`pip`, y es viable computacionalmente para 3 departamentos dentro del límite de 5,000
puntos de demanda fijado más abajo. Todo resultado de ruteo se cachea en disco
(`data/processed/routing_matrix_*.parquet`, `data/cache/graphs/*.graphml`) para que
una segunda corrida no recompute nada.

**Construcción del grafo — historia real de tres intentos (documentada porque el
enunciado pide justificar decisiones técnicas, no solo el resultado final):**

1. **`pyrosm` desde el .pbf local** (intento original): descartado porque su
   dependencia `cykhash` no tiene wheel precompilado para Windows/Python 3.11 y
   exige un compilador de C++ (MSVC Build Tools) no instalado — el mismo tipo de
   cambio de sistema pesado que Docker/WSL2.
2. **`osmnx.graph_from_polygon()` contra Overpass API en vivo** (segundo intento):
   funcionó para Lambayeque (~5 min, 44,020 nodos tras simplificar) pero falló
   reiteradamente para Cusco/Loreto durante la sesión de cómputo del 2026-09-04 al
   2026-09-05: la instancia principal (`overpass-api.de`) estuvo inalcanzable
   (SSL EOF) durante más de una hora; el failover a `overpass.kumi.systems`
   funcionó un rato pero luego también cayó; el failover a `overpass.osm.ch`
   respondía HTTP 200 pero devolvía **resultados vacíos** para áreas con
   carreteras reales confirmadas (verificado con una consulta de control cerca de
   Quillabamba, Cusco: 0 vías encontradas) — un fallo silencioso más peligroso que
   una caída limpia, porque no lanza excepción. Además, el tamaño de consulta por
   defecto de OSMnx (2,500 km²) partió el polígono de Cusco (~72,000 km²) en 62
   sub-consultas, cada una una oportunidad más de toparse con la inestabilidad del
   servidor — casi 3 horas para un solo departamento sin terminar.
3. **GDAL (driver `OSM`) sobre el .pbf local, vía `pyogrio`** (solución final): tanto
   `fiona` como `pyogrio` ya traen GDAL empaquetado (sin compilador extra), y GDAL
   incluye un driver nativo para `.osm.pbf`. `src/routing.py` lee la capa `lines`
   filtrada por bbox + `highway IS NOT NULL`, aplica los mismos filtros de
   categoría de vía que usa OSMnx internamente para `network_type='drive'`
   (capturados literalmente de la URL de consulta que Overpass recibió en los
   intentos anteriores) y filtros propios y documentados para `foot`/`bike`,
   y arma el grafo de NetworkX manualmente (nodos = vértices únicos, aristas con
   `length`/`travel_time`, sin simplificación topológica de OSMnx — ver
   Limitaciones). 100% offline, sin ninguna dependencia de red en tiempo de
   ejecución. Verificado el 2026-09-05: Lambayeque completo (lectura + filtrado +
   construcción de grafo + guardado en caché) en 55 s — contra los ~5 min
   (cuando funcionaba) o las horas (cuando no) del enfoque por Overpass — con
   resultados de ruteo idénticos (1,833/1,834 puntos de demanda alcanzables en
   auto, igual que con el grafo vía Overpass).

**Diferencia con un grafo de OSMnx real**: al no aplicar la simplificación
topológica de OSMnx (fusionar cadenas de nodos de grado 2 en una sola arista), el
grafo construido aquí tiene muchos más nodos/aristas para la misma red vial
(Lambayeque: 244,858 nodos aquí vs. 44,020 con OSMnx simplificado) — no afecta la
corrección de las distancias/tiempos calculados, solo el tamaño en memoria y el
tiempo de cómputo de Dijkstra (que sigue siendo de segundos por instalación, ver
Fase 2).

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
