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

**Decisión 4 (bonus, una sola frase — ver nota de tiempos abajo) — Por qué
automaticé la generación del reporte.**

Con las Decisiones 1-3 ya llenas las 2 minutos del bloque (ver "Chequeo de
tiempos" al final del documento) — usa la versión corta, no la larga:

> "Un profesor me preguntó algo razonable: ¿qué pasa si cambian los
> departamentos o llega data nueva? Construí una Fase 5 que recalcula
> automáticamente cada cifra del reporte desde los datos y recompila el
> PDF con un comando — y al construirla, encontró y corrigió un error
> real en mi propia redacción sobre cuál era el distrito peor ubicado."

*Versión larga (NO la leas en el video salvo que te sobre tiempo en otra
sección — son ~155 palabras, ~1 minuto, y no hay presupuesto para eso
aquí): cuenta que habías escrito a mano "Paucartambo" como el distrito
con peor acceso, pero RENIPRESS autorreporta el distrito de un
establecimiento (un campo de texto) que no es lo mismo que el distrito
real por polígono — el verdadero es Kosñipata, un distrito vecino dentro
de la misma provincia — y que tu propia automatización encontró ese bug
en tu propia redacción, no en tu código.*

---

## 6:00 – 9:30 | Demo en vivo del dashboard

Corre `streamlit run app.py` y muéstralo en tiempo real. Sugerido, en este
orden:

1. **KPIs** (arriba): población en alcance, % a más de 60 min, peor
   distrito, mediana de acceso. Cambia el umbral en la barra lateral y
   muestra que los KPIs se actualizan.
2. **Mapa coroplético**: filtra a un solo departamento (ej. Cusco) y
   señala visualmente los distritos rojos — Kosñipata, Camanti y Marcapata,
   en las provincias de Paucartambo y Quispicanchi respectivamente.
3. **Capa de establecimientos**: activa/desactiva resolutivos vs. no
   resolutivos, filtra por categoría o institución.
4. **Distribución**: cambia entre "Departamento" y "Urbano/Rural" en el
   histograma — señala la brecha urbano/rural (8.0 vs. 19.8 min).
5. **Ranking de distritos** + botón de descarga CSV.
6. **Simulador de escenarios**: selecciona Cusco, busca y elige
   **PILCOPATA (I-3, Kosñipata)** — el establecimiento del distrito con
   peor acceso de todo el estudio, la elección "obvia". El panel muestra
   población cubierta actual 541,425 → con el escenario 541,621:
   **ganancia marginal de solo 196 personas.** No lo escondas ni pases
   rápido por ese número — es el gancho para el siguiente paso.

   > "La elección obvia sería elevar el establecimiento del distrito con
   > peor tiempo de acceso, Kosñipata. Pero miren: la ganancia real es de
   > apenas 196 personas — porque Kosñipata, aunque tiene el peor tiempo
   > individual, tiene muy poca población. El peor *tiempo* no es lo mismo
   > que el mayor *impacto*."

7. **Innovación — recomendación de ubicación (MCLP)**: esta es tu cierre
   de la demo, y responde directamente a lo que acabas de mostrar. Muestra
   la tabla y el gráfico de barras, y di:

   > "Por eso construí esto: en vez de que yo elija a mano y adivine, un
   > algoritmo voraz recorre TODOS los candidatos y los ordena por impacto
   > real, no por intuición. En Cusco, la recomendación número uno no es
   > Pilcopata — es el establecimiento **Paucartambo**, en la misma
   > provincia, con una ganancia de 4,608 personas: 23 veces más que la
   > elección obvia. Y en Lambayeque, un solo establecimiento en Olmos
   > agregaría más de 42 mil personas cubiertas — casi el doble de lo que
   > suman los otros cuatro candidatos recomendados juntos."

8. **Panel de calidad de datos** (cierre de la demo, transición a
   hallazgos): vuelve a mostrar brevemente el reporte de la Fase 1.

---

## 9:30 – 10:45 | Hallazgos y recomendaciones

Con números reales, no solo texto:

> "Con los 3 departamentos: 78.4% de la población llega en 30 minutos o
> menos, pero con un Gini de acceso de 0.669 — muy desigual. Cusco tiene un
> promedio saludable (15.4 min, mejor que Lambayeque aunque no el mejor de
> los tres — ese es Loreto con 11.7 min, por una razón de muestreo que
> explico en Limitaciones, no por mejor infraestructura) pero también el
> peor distrito individual de todo el estudio: Kosñipata, casi 195
> minutos. Caminar toma, en mediana, **12.2 veces más** que ir en auto —
> sorprendentemente parecido entre los tres departamentos, algo que no
> esperaba."

> "La recomendación concreta: priorizar la elevación de categoría de los
> establecimientos I-3/I-4 que mi algoritmo de siting identificó, empezando
> por el establecimiento Paucartambo en esa misma provincia de Cusco y el
> establecimiento de Olmos en Lambayeque — antes que construir
> infraestructura nueva desde cero."

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

## Chequeo de tiempos (antes de grabar)

Conteo de palabras de todo lo que va entre comillas (lo que realmente se
dice en voz alta), a ritmo conservador de presentación (130 palabras/min
— más lento que una conversación normal, a propósito, porque grabando
uno tiende a ir más lento que leyendo en silencio):

| Sección | Presupuesto | Texto guionado | Estimado a 130 ppm |
|---|---|---|---|
| 0:00–0:45 Problema | 45 s | 72 palabras | ~33 s — sobra tiempo para señalar la pantalla |
| 0:45–2:15 Datos | 90 s | 91 palabras | ~42 s — sobra bastante, úsalo para dejar que los números se asienten |
| 2:15–4:00 Método | 105 s | 85 palabras | ~39 s — igual, sobra tiempo |
| 4:00–6:00 Decisiones | 120 s | 277 palabras (con la Decisión 4 en versión corta) | ~128 s — ajustado, prácticamente al límite |
| 6:00–9:30 Demo | 210 s | 213 palabras guionadas | ~98 s de texto + ~112 s de clicks/espera reales — sobra margen |
| 9:30–10:45 Hallazgos | 75 s | 142 palabras | ~66 s |
| 10:45–11:45 Limitaciones | 60 s | 63 palabras (notas, no oraciones completas) | elabóralas, no las leas tal cual |
| 11:45–12:00 Cierre | 15 s | 40 palabras | ~19 s — ligeramente ajustado |

**La única sección realmente en riesgo es "4:00–6:00 Decisiones"** — por
eso la Decisión 4 quedó como una sola frase corta por defecto, con la
versión larga marcada explícitamente como "no la leas" salvo que te sobre
tiempo en otra parte. Con eso, las 4 decisiones caben en ~2 minutos
hablando a ritmo normal. Si de todos modos se te va el tiempo ahí, el
orden de recorte es: (1) recorta Decisión 4 a cero — ni la frase corta,
(2) acorta Decisión 2 (población) a una sola oración, (3) nunca recortes
Decisión 1 (Overpass) ni Decisión 3 (I-3/I-4) — son las que responden
directamente al criterio de "defensa de metodología".

Las demás secciones tienen margen de sobra (sobre todo Datos y Método) —
si notas que te faltan segundos en Decisiones, puedes literalmente hablar
un poco más lento en Datos/Método sin que el video se pase de 12 minutos.

---

## Notas prácticas para grabar

- El dashboard debe estar corriendo ANTES de empezar a grabar
  (`streamlit run app.py`) — no pierdas tiempo de video esperando que cargue.
- Ten `data/outputs/data_quality_report.csv` y `report/main.pdf` abiertos
  en pestañas listas para alternar.
- Practica la transición 6:00→9:30 (la demo) al menos una vez cronometrada
  — es la sección más larga y la que más fácil se te va de tiempo.
- El selector de establecimientos del simulador es un multiselect que
  filtra mientras escribes: haz clic en el campo, escribe "PILCOPATA" y
  selecciona la única opción que aparece ("PILCOPATA (I-3, KOSÑIPATA)").
  **No hagas doble clic ni cliquees cerca después de seleccionar** — el
  dropdown queda abierto y un clic de más agrega establecimientos que no
  quieres (me pasó probándolo). Si se llena de chips de más, recarga la
  página (F5) y empieza de nuevo — es más rápido que sacarlos uno a uno.
  Practica esta selección un par de veces antes de grabar.
- Si te quedas corto de tiempo en algún lado, recorta primero la
  Decisión 4 completa (ver "Chequeo de tiempos"), luego la sección de
  hallazgos (9:30-10:45) — Limitaciones y la Demo son las que más puntos
  valen y no deberían recortarse.
- Corre `python -m src.pipeline_phase5` una vez antes de grabar si tocaste
  cualquier número del reporte, para que `report/main.pdf` (la pestaña
  que vas a mostrar) tenga las cifras más recientes.
