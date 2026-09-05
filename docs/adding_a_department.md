# Cómo agregar o cambiar un departamento de análisis

El pipeline (`src/`) es agnóstico al departamento: no hay ningún nombre de
departamento en la lógica de acquisition, validation, routing o metrics —
todo se lee de `config.md`. La **única excepción** es la población
distrital (Censo 2017), porque INEI la publica solo como PDF, no como CSV
descargable, y `scripts/extract_population_by_district.py` es un script de
extracción de un solo uso, no parte del pipeline reproducible regular (ver
`config.md`, sección "Estimación de población").

Cambiar de departamento (o agregar uno más a los 3 actuales) implica 2
pasos: uno de configuración (siempre) y uno manual de extracción de
población (solo la primera vez que se usa ese departamento).

## Paso 1 — `config.md`

Edita el bloque `departments` con el nombre exacto tal como aparece en
RENIPRESS/SIGMED (mayúsculas, sin tildes al comparar — el pipeline ya
normaliza eso) y su código de departamento (2 dígitos, ubigeo):

```yaml
departments:
  - name: Piura
    ubigeo_dep: "20"
    region_type: coastal
```

RENIPRESS, SIGMED, el extracto de OSM y los límites distritales son
fuentes **nacionales** ya descargadas — no hace falta re-descargar nada
para agregar un departamento nuevo, `src/pipeline_phase1.py` simplemente
filtra por el nombre declarado aquí.

## Paso 2 — Población distrital (Censo 2017)

Este es el único paso manual. Se hace una sola vez por departamento.

1. **Encuentra el PDF "Tomo I"** del departamento en
   <https://censo2017.inei.gob.pe> (lista los 24 departamentos con enlace
   directo). El patrón de URL observado es:

   ```
   https://www.inei.gob.pe/media/MenuRecursivo/publicaciones_digitales/Est/Lib{NNNN}/{ubigeo}TOMO_01.pdf
   ```

   El número `{NNNN}` (ej. 1559 para Cusco, 1560 para Lambayeque, 1561
   para Loreto) no sigue el orden de ubigeo — se obtiene navegando el
   índice de censo2017.inei.gob.pe, no adivinando.

2. **Descarga el PDF** a `data/raw/censo2017_<departamento>_tomo1.pdf`
   (no se commitea — ver `.gitignore`).

3. **Ubica las páginas de "CUADRO N° 1"** (población censada por
   provincia y distrito) dentro del PDF — busca el texto "CUADRO N 1" o
   "CUADRO Nº 1" y anota la página de inicio; el final es la página
   anterior a donde empieza "CUADRO N° 2". El rango varía mucho por
   departamento (Lambayeque: 133 páginas; Cusco: 407 páginas, por tener
   muchas más provincias).

4. **Agrega una entrada** en `scripts/extract_population_by_district.py`
   (diccionario `DEPARTMENTS`) con el path del PDF, `start`/`end` de esas
   páginas, el CSV de salida, y `nombdep`.

5. **Corre la extracción**:

   ```bash
   python scripts/extract_population_by_district.py <clave_del_departamento>
   ```

   Requiere `pdfplumber` y `pypdf` (no están en `requirements.txt` por ser
   de un solo uso): `pip install pdfplumber pypdf`.

   El script **falla explícitamente** (no escribe el CSV) si la suma de
   distritos no coincide exactamente con el total de provincia/departamento
   impreso en la misma tabla del PDF — eso generalmente significa que el
   rango de páginas de `start`/`end` está mal y hay que ajustarlo.

6. **Declara la fuente** en `config.md`, bloque `sources.population_census2017`
   (`tomo1_urls`, `cuadro1_pages`, `local_raw_names`), igual que los 3
   departamentos existentes — es solo para documentación/trazabilidad, el
   pipeline lee directamente los `local_raw_names` declarados ahí.

## Paso 3 — Correr el pipeline

```bash
python -m src.pipeline_phase1   # minutos
python -m src.pipeline_phase2   # ver nota de tiempos abajo
python -m src.pipeline_phase3   # segundos
```

Si estás **reemplazando** uno de los 3 departamentos actuales (no
agregando un cuarto), borra su caché para que no quede mezclada con
resultados viejos:

```bash
rm data/cache/graphs/<departamento_viejo>_*.graphml
rm data/processed/routing_*_<departamento_viejo>_*.parquet
```

### Tiempos esperados de la Fase 2 (referencia real, 2026-09-05)

El tiempo depende del tamaño del departamento y de cuántos distritos
tiene (no solo del área), porque eso determina el tamaño del grafo vial:

| Departamento | Área aprox. | Tiempo real (auto, 1 corrida) |
|---|---|---|
| Lambayeque (costa, pequeño) | ~14,000 km² | ~5 min |
| Loreto (selva, red vial dispersa) | ~368,000 km² | ~1 min (grafo chico pese al área — poca red vial mapeada) |
| Cusco (sierra, muchas provincias) | ~72,000 km² | ~58 min |

Departamentos con muchas provincias/distritos (ej. Cajamarca, Puno,
Áncash, Arequipa) probablemente se comporten más como Cusco que como
Lambayeque. Un departamento nuevo puede tomar entre minutos y ~1 hora para
la matriz de auto, más un tiempo similar para peatonal y bici cada uno —
el pipeline ya cachea todo, así que solo se paga ese costo una vez.
