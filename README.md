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

Este repositorio está en construcción por fases, siguiendo el cronograma
sugerido del enunciado. Estado actual:

- [x] Entorno y estructura del repositorio
- [ ] Fase 1 — Adquisición y validación de datos
- [ ] Fase 2 — Ruteo y matriz de tiempos de viaje
- [ ] Fase 3 — Construcción de métricas
- [ ] Fase 4 — Dashboard en Streamlit
- [ ] Fase 5 — Reporte en LaTeX

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
# Fase 1 — descarga (idempotente: no vuelve a descargar lo que ya existe)
python -m src.acquisition

# Verificar que la configuración carga correctamente
python -m src.config

# Tests
pytest

# Dashboard (una vez que existan los archivos precomputados en data/processed/)
streamlit run app.py
```

## Fuentes de datos

Declaradas con URL y licencia en `config.md` (bloque `sources`):

- **Oferta** (RENIPRESS/SUSALUD): establecimientos de salud y su categoría/estado.
- **Demanda** (MINEDU/SIGMED): centros poblados georreferenciados.
- **Red vial** (OpenStreetMap / Geofabrik): extracto de Perú.
- **Límites administrativos**: distrito/provincia/departamento — fuente exacta y
  fecha de descarga documentadas en `logs/` al momento de correr `src.acquisition`.

## Motor de ruteo

**OSMnx + NetworkX**, sin Docker/OSRM — ver la justificación completa en
`config.md`. En resumen: la máquina de desarrollo no tiene Docker Desktop ni
WSL2 instalados, y OSMnx+NetworkX es una alternativa 100% Python, viable para
tres departamentos dentro del límite de 5,000 puntos de demanda del
enunciado, con resultados cacheados en `data/processed/`.

## Licencia de los datos

Cada fuente conserva su propia licencia (ver `config.md`); este repositorio
no redistribuye los archivos crudos por su tamaño — `src/acquisition.py` los
regenera localmente en `data/raw/`.
