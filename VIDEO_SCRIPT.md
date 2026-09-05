# Guion del video de presentación (≤12 min)

Basado en los criterios de evaluación: framing del problema (2.0), demo en
vivo (2.5), defensa de metodología y decisiones técnicas (2.0), hallazgos +
limitaciones + recomendaciones (1.5). No leas diapositivas — habla como si
le explicaras esto a tu director regional de salud, con el dashboard
abierto la mayor parte del tiempo.

---

## 0:00 – 0:45 | El problema (framing)

> "En una emergencia obstétrica o de trauma grave, un puesto de salud puede
> estabilizar a un paciente, pero no operarlo. Solo los establecimientos
> categoría II-1 en adelante — los que llamo 'resolutivos' — pueden hacerlo.
> La pregunta de este proyecto es simple de decir y difícil de responder
> bien: ¿cuánto tarda REALMENTE, por carretera, la población de una región
> en llegar a uno de esos establecimientos, y dónde están las peores
> brechas?"

Muestra el título del reporte / el mapa de los 3 departamentos (Lambayeque,
Cusco, Loreto — costa, sierra, selva) y explica en una frase por qué se
eligió ese contraste geográfico.

---

## 0:45 – 2:15 | Los datos: qué estaba mal, y qué hiciste al respecto

Abre `data/outputs/data_quality_report.csv` o el panel de calidad de datos
del dashboard.

> "Usé 4 fuentes: RENIPRESS para la oferta de salud, SIGMED para los
> centros poblados, OpenStreetMap para la red vial, y el Censo 2017 del
> INEI para población. Ninguna vino limpia."

Menciona 2-3 hallazgos concretos (no los 8, elige los más impactantes):
- **32.4% de los establecimientos de RENIPRESS en los 3 departamentos no
  tienen coordenadas usables** — se mantienen en el registro pero se
  excluyen del cómputo geoespacial, nunca se descartan en silencio.
- **23.75% de los registros nacionales usan el valor literal `"0"` como
  categoría** en vez de una categoría real — los traté como no
  resolutivos, nunca asumí capacidad.
- **SIGMED (la fuente de demanda) no trae población por punto** — tuve que
  extraerla del Censo 2017, que INEI solo publica como PDF, no como CSV.

> "La regla que seguí en todo el proyecto: nunca borrar un dato sospechoso
> en silencio. Se documenta, se decide qué hacer, y se justifica por qué."

---

## 2:15 – 4:00 | El método: motor de ruteo y parámetros

> "Para calcular tiempos reales necesitaba un motor de ruteo sobre la red
> vial real — una línea recta no es una carretera, eso lo prohibe
> explícitamente el enunciado."

Explica brevemente:
- Se usó **OSMnx (formato de grafo) + Dijkstra de NetworkX**, no OSRM/Docker,
  porque la máquina no tenía Docker Desktop ni WSL2 instalados.
- El grafo se construye **localmente desde el archivo `.pbf` de Perú**
  (vía el driver OSM de GDAL), no contra una API en vivo.
- Categoría resolutiva: `ACTIVO` + categoría en {II-1, II-2, II-E, III-1,
  III-2, III-E}.
- Velocidades: auto por tipo de vía (imputación tipo OSMnx), a pie 4.5 km/h,
  bici 12 km/h — parametrizado en `config.md`, no hardcodeado.
- Matriz completa (no solo el más cercano) enrutada también a candidatos
  I-3/I-4, para que el simulador de la Fase 4 pueda usarlo.

---

## 4:00 – 6:00 | 3 decisiones técnicas + el obstáculo real (defensa de metodología)

Esta sección es la que más puntúa (2.0 de defensa de metodología). Cuenta
**una historia real**, no una lista.

**Decisión 1 — Por qué no Overpass API en vivo, al final.**

> "El plan original era descargar los grafos en vivo contra Overpass API,
> como hace OSMnx normalmente. Funcionó para Lambayeque en 5 minutos. Para
> Cusco y Loreto, fallé durante más de un día: el servidor principal
> estuvo caído más de una hora: cuando probé un espejo alternativo,
> respondía HTTP 200 — pero devolvía **cero resultados** para una zona con
> carreteras confirmadas. Fallo silencioso, sin excepción — el peor tipo
> de bug porque parece que funcionó."

> "La decisión: en vez de seguir peleando con un servicio público que no
> controlo, construí los grafos **localmente desde el `.pbf` que ya había
> descargado**, usando el driver OSM de GDAL. Cien por ciento offline,
> mismos resultados verificados, y ya no dependo de que un servidor
> externo esté de humor."

**Decisión 2 — Cómo estimé población por punto de demanda (sin datos).**

> "SIGMED no trae población. Usé la jerarquía real del campo CAPITAL —
> capital departamental, provincial o distrital — para repartir la
> población censal del distrito entre sus centros poblados, dándole más
> peso a las capitales. Es un supuesto documentado, no una medición, y lo
> digo explícitamente en las limitaciones."

**Decisión 3 — Por qué ruteo también a los candidatos I-3/I-4, no solo a
los resolutivos.**

> "Al probar mi propio simulador de escenarios, descubrí que no podía
> simular elevar un I-3 a resolutivo — porque nunca lo había ruteado como
> destino. Sin eso, el simulador no sirve para nada. Lo corregí: ahora la
> matriz completa enruta a resolutivos Y candidatos por igual."

*(Este último punto también sirve como tu "obstáculo diagnosticado y
arreglado" si el video pide esa sección aparte — encontrado probando la
app de verdad, no leyendo el código.)*

---

## 6:00 – 9:30 | Demo en vivo del dashboard

Corre `streamlit run app.py` y muéstralo en tiempo real. Sugerido, en este
orden:

1. **KPIs** (arriba): población en alcance, % a más de 60 min, peor
   distrito, mediana de acceso. Cambia el umbral en la barra lateral y
   muestra que los KPIs se actualizan.
2. **Mapa coroplético**: filtra a un solo departamento (ej. Cusco) y
   señala visualmente los distritos rojos (Paucartambo, Quispicanchi).
3. **Capa de establecimientos**: activa/desactiva resolutivos vs. no
   resolutivos, filtra por categoría o institución.
4. **Distribución**: cambia entre "Departamento" y "Urbano/Rural" en el
   histograma — señala la brecha urbano/rural (8.0 vs. 19.8 min).
5. **Ranking de distritos** + botón de descarga CSV.
6. **Simulador de escenarios**: selecciona Cusco, elige un candidato I-3/I-4
   real (ideal: uno de Paucartambo o Quispicanchi) y muestra la ganancia
   marginal en vivo.
7. **Innovación — recomendación de ubicación (MCLP)**: esta es tu cierre
   de la demo. Muestra la tabla y el gráfico de barras, y di:

   > "En vez de que yo elija a mano qué establecimiento simular, este
   > algoritmo recorre TODOS los candidatos y los ordena por impacto. Miren
   > esto: en Cusco, la recomendación número uno es el propio
   > establecimiento de **Paucartambo** — el mismo distrito que identificamos
   > como el peor del estudio. Y en Lambayeque, un solo establecimiento en
   > Olmos agregaría más de 42 mil personas cubiertas — casi tanto como los
   > otros cuatro candidatos recomendados juntos."

8. **Panel de calidad de datos** (cierre de la demo, transición a
   hallazgos): vuelve a mostrar brevemente el reporte de la Fase 1.

---

## 9:30 – 10:45 | Hallazgos y recomendaciones

Con números reales, no solo texto:

> "Con los 3 departamentos: 78.4% de la población llega en 30 minutos o
> menos, pero con un Gini de acceso de 0.670 — muy desigual. Cusco tiene
> el mejor promedio de los tres (15.4 min) pero también el peor distrito
> individual de todo el estudio (Paucartambo, casi 195 minutos). Caminar
> toma, en mediana, **12 veces más** que ir en auto — sorprendentemente
> parecido entre los tres departamentos, algo que no esperaba."

> "La recomendación concreta: priorizar la elevación de categoría de los
> establecimientos I-3/I-4 que mi algoritmo de siting identificó, empezando
> por Paucartambo en Cusco y el establecimiento de Olmos en Lambayeque —
> antes que construir infraestructura nueva desde cero."

---

## 10:45 – 11:45 | Limitaciones (obligatorio y evaluado)

No lo apures — esto es lo que distingue a un analista de alguien que solo
corrió un script. Elige 3-4:

- 32% de RENIPRESS sin coordenadas usables — el panorama real de oferta
  puede ser más denso de lo que este análisis ve.
- Un establecimiento listado no implica uno operativo con personal real.
- No modela disponibilidad de ambulancias.
- **Loreto es un caso especial**: el factor de desvío ahí da un número
  matemáticamente imposible (0.014x) porque el snapping mueve puntos hasta
  470 km — lo documenté como hallazgo metodológico, no lo escondí ni lo
  "arreglé" para que se viera bien.
- El buen promedio de Loreto es un artefacto del muestreo ponderado por
  población, no evidencia de buena infraestructura — correlación, no
  causalidad.
- Población por punto es una heurística (reparto por capital), no una
  medición directa.

---

## 11:45 – 12:00 | Cierre

> "Este proyecto no termina en un número — termina en una lista accionable
> y honesta sobre qué no puede probar. El código completo, los datos
> procesados, la matriz de ruteo precomputada y el reporte están en mi
> repositorio de GitHub."

---

## Notas prácticas para grabar

- El dashboard debe estar corriendo ANTES de empezar a grabar
  (`streamlit run app.py`) — no pierdas tiempo de video esperando que cargue.
- Ten `data/outputs/data_quality_report.csv` y `report/main.pdf` abiertos
  en pestañas listas para alternar.
- Practica la transición 6:00→9:30 (la demo) al menos una vez cronometrada
  — es la sección más larga y la que más fácil se te va de tiempo.
- Si te quedas corto de tiempo en algún lado, recorta la sección de
  hallazgos (9:30-10:45) antes que Limitaciones o la Demo — son las que
  más puntos valen.
