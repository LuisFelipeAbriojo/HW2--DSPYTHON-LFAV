# Golden Hour — Acceso vial a salud resolutiva en Perú

Proyecto integrador (Data Science con Python, 2026-II): estimar cuánto tarda, por
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

Cambiar de departamento (o agregar más) es solo edición de `config.md` en
casi todo el pipeline; el único paso manual (extracción de población del
Censo 2017, ya que INEI la publica solo en PDF) está documentado en
[docs/adding_a_department.md](docs/adding_a_department.md).

## Estado del proyecto

- [x] Entorno y estructura del repositorio
- [x] Fase 1 — Adquisición y validación de datos (3,631 establecimientos,
  21,095 centros poblados, reporte de calidad en `data/outputs/data_quality_report.csv`)
- [x] Fase 2 — Ruteo y matriz de tiempos de viaje (auto/bici/a pie, 3
  departamentos, 100% offline — ver `config.md`)
- [x] Fase 3 — Construcción de métricas (cobertura, Gini, brechas críticas,
  cruce con ruralidad, línea recta vs. red vial, comparación entre modos)
- [x] Fase 4 — Dashboard en Streamlit (KPIs, mapa coroplético, capa de
  establecimientos, distribución, ranking, simulador de escenarios, panel
  de calidad de datos)
- [x] Fase 5 — Reporte en LaTeX (`report/main.tex` + `report/main.pdf`, 11
  páginas), con cifras y compilación automatizadas (`python -m
  src.pipeline_phase5`) — ver "Regenerar el reporte" más abajo
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
│   ├── optimization.py      # Innovación — siting de facilities (MCLP voraz)
│   ├── export.py            # tablas/figuras para el reporte y el dashboard
│   ├── report_stats.py      # Fase 5 — macros LaTeX con cifras recalculadas
│   └── pipeline_phase5.py   # Fase 5 — orquesta report_stats + compila el PDF
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

## Puesta en marcha (máquina limpia)

**Requiere Python 3.11 o 3.12.** Python 3.14 **no** sirve: `fiona` no tiene
wheel para 3.14 y falla al compilar (necesita GDAL). Si no lo tienes:
`winget install Python.Python.3.12`.

### Opción rápida — un solo comando (Windows / PowerShell)

```powershell
git clone https://github.com/LuisFelipeAbriojo/HW2--DSPYTHON-LFAV.git
cd HW2--DSPYTHON-LFAV
.\run.ps1
```

`run.ps1` crea el venv, instala dependencias, corre los tests, regenera las
métricas/tablas/figuras (Fase 3) y abre el dashboard. **No descarga nada**:
`data/processed/` (incluida la matriz de ruteo de la Fase 2) y `data/outputs/`
están versionados. Flags: `.\run.ps1 -Pipeline` corre además las Fases 1 y 2
desde cero (descarga ~256 MB, ~2 h); `.\run.ps1 -NoDashboard` omite Streamlit.

### Opción manual (cualquier SO)

```bash
py -3.12 -m venv .venv           # o: python3.12 -m venv .venv
.venv\Scripts\activate           # Windows  ·  source .venv/bin/activate en Linux/Mac
pip install -r requirements.txt

pytest                           # 41 tests
python -m src.pipeline_phase3    # métricas + tablas + figuras (segundos, lee data/processed/)
streamlit run app.py             # dashboard en http://localhost:8501
```

### Pipeline completo desde cero (opcional)

Solo si quieres reconstruir todo en vez de usar los archivos versionados. Las
Fases 1–2 tardan y descargan; el resultado es idéntico al ya commiteado.

```bash
python -m src.pipeline_phase1    # descarga (idempotente) RENIPRESS/SIGMED/OSM/límites + validación
python -m src.pipeline_phase2    # ruteo auto/bici/a pie — ~1h50 la 1ª vez, luego instantáneo (caché en data/cache/)
python -m src.pipeline_phase3    # métricas
```

## Regenerar el reporte (Fase 5)

Para recompilar el reporte (Fase 5) hace falta una distribución de LaTeX
(este proyecto usa [MiKTeX](https://miktex.org/), instalado con
`winget install MiKTeX.MiKTeX`, sin necesidad de permisos de administrador).

```bash
# Recalcula report/generated_stats.tex (macros LaTeX con las cifras que
# cita el texto -- Gini, cobertura, tiempos por departamento, etc.) desde
# lo último que haya en data/outputs/, y compila main.pdf (2 pasadas,
# validando main.log en vez de solo el código de salida).
python -m src.pipeline_phase5
```

Esto es lo que hace que "cambió la data" (una fuente actualizada, u otros
departamentos en `config.md`) se traduzca en un PDF actualizado sin copiar
números a mano: `src/report_stats.py` computa cada cifra citada en el
texto directamente desde `data/outputs/*.csv`, así que solo hace falta
correr `python -m src.pipeline_phase3` (que ya llama a `report_stats`
automáticamente al final) y luego `pipeline_phase5` para compilar. **Lo
que esto NO automatiza** es la prosa interpretativa (qué departamento
"sale mejor" y por qué, qué distrito se nombra en una oración) -- eso es
redacción de análisis, no aritmética, y sigue siendo un paso manual (o
asistido por Claude) al cambiar de departamentos. Ver
[docs/adding_a_department.md](docs/adding_a_department.md) para el
alcance exacto.

Para compilar a mano sin recalcular nada (por ejemplo, tras un cambio de
texto que no toca ninguna cifra):

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

## Licencia

El código de este repositorio se distribuye bajo licencia [MIT](LICENSE).

Los **datos** son otra cosa: cada fuente conserva su propia licencia
original (Open Data Commons Attribution para RENIPRESS, ODbL para
OpenStreetMap, dato público de MINEDU/INEI para SIGMED y el Censo — ver el
detalle en `config.md`, bloque `sources`). La licencia MIT del código no
se extiende a los datos ni los relicencia; este repositorio tampoco
redistribuye los archivos crudos por su tamaño — `src/acquisition.py` los
regenera localmente en `data/raw/`.
