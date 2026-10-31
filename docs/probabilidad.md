# Motor probabilístico

Código: `src/musst/probability/` (Python estándar, funciona igual en el servidor y en el
navegador con Pyodide) y `src/musst/agents/mathematical.py`. Pruebas:
`tests/unit/test_probabilidad.py` y `tests/unit/test_bayes_y_decision.py`. Experimentos:
`experiments/probability.py`.

## 1. Diagnóstico del código existente

| Pieza | Dónde | Estado antes de este cambio |
|---|---|---|
| Carta | `engine/cards.py` | `Card(rank, suit)` inmutable; baraja de 40; con ocho reyes el 3 cuenta como rey y el 2 como as (`normalized_rank`) |
| Mano | `engine/game.py` | Lista de 4 `Card` por asiento; el bot solo ve la suya (`Observation.hand`) |
| Evaluación de lances | `engine/evaluation.py` | Claves comparables por lance y `best_seat` (empate: el más cercano al mano). El ganador del lance y el valor de las jugadas estaban **duplicados** en `MusGame`, `bots/toolkit.py` y `agents/specialists.py` |
| Acciones legales | `engine/actions.py` | `ActionSpec` con importes mínimo/máximo; `MusGame.validate` es la única autoridad |
| Información del bot | `engine/observation.py` | `Observation` por lista blanca: su mano, historial público, declaraciones, señas vistas, apuesta en curso |
| Orquestador | `agents/orchestrator.py` | Elige agentes por nivel, análisis profundo en jugadas críticas, `Judge` por EV ajustado por riesgo |
| Probabilidad | `agents/specialists.py` (`ProbabilityAgent`) | Monte Carlo con `toolkit.sample_world` |
| Muestreo | `bots/toolkit.py` (`sample_world`) | **Sesgado**: rechazo asiento a asiento sin corregir pesos y, si falla 50 veces, **ignora** las declaraciones y señas |
| Bayes | `ProbabilityAgent`, `BluffAgent` | Ponderación de mundos por verosimilitudes heurísticas del envite; el farol se estima con un muestreo aparte |
| Valor esperado | `agents/strategy.py` | Fórmulas ad hoc en tantos con un factor `point_utility` |
| Aprendizaje | `learning/player_model.py` | Tasas Beta por contexto (lance × marcador) con back-off jerárquico |
| Explicación | `agents/base.py` (`Decision.explanation`) | Factores, alternativas y narrativa |

No había: cálculo exacto, intervalos de confianza, criterio de convergencia, distinción entre
probabilidad exacta, estimada y a posteriori, ni una utilidad basada en ganar la partida.

## 2. Qué se ha cambiado (incremental)

1. **Reglas en un solo sitio**: `evaluation.lance_keys`, `evaluation.lance_winner` y
   `evaluation.play_points` son funciones puras que usan el motor (`MusGame`), los bots, el
   análisis y el motor probabilístico. Nadie más reimplementa quién gana un lance.
2. **`musst.probability`** (nuevo): combinatoria, muestreo, estimadores, Bayes, lances,
   equidad y decisión (secciones 3-6).
3. **Agentes nuevos** (sección 7) y **niveles nuevos** `mat_exacto`, `mat_bayes`, `mat_mc`,
   `mat_utilidad` y `matematico`. Los niveles `sencillo`, `medio` y `profesional` no cambian.
4. `AgentContext.shared` (representación común) y `Decision.math` (explicación matemática).

## 3. Combinatoria (`combinatorics.py`)

Todos los lances dependen solo del **rango normalizado** de cada carta. Una mano se resume sin
pérdida en un multiconjunto de clases de rango: con ocho reyes hay 8 clases
(1, 4, 5, 6, 7, 10, 11, 12) y C(8+4−1, 4) = 330 tipos de mano.

**Hipergeométrica multivariante** (muestreo sin reemplazo). Si quedan N cartas desconocidas,
n_r de la clase r:

```
P(m) = Π_r C(n_r, m_r) / C(N, 4),     con Σ_r m_r = 4
```

y suma 1 por la identidad de Vandermonde. No es una binomial: las cartas no se reponen
(`test_hipergeometrica_no_es_binomial`).

**Condicionar** a una información cierta C (p. ej. «tiene juego») es Bayes con verosimilitud
0/1: P(t | C) = P(t)·1[C(t)] / P(C).

**Cálculo exacto** (`enumerate_deals`): para k asientos desconocidos,

```
P(t_1, …, t_k) = Π_j [ Π_r C(n_r^(j), m_r^(j)) / C(N_j, 4) ]
```

con las cartas que quedan tras repartir a los anteriores. Con las 36 cartas desconocidas de
una jugada real hay del orden de 10⁷ estados, así que se usa en **casos reducidos** (pocas
cartas desconocidas) para validar Monte Carlo.

**Aproximación analítica** (`lances.analytic_win_probability`): marginal exacta de cada
asiento, combinada **como si fueran independientes**. Se etiqueta `analitica_aproximada`,
nunca `exacta`.

## 4. Monte Carlo sin sesgo (`sampler.py`, `estimators.py`)

Distribución objetivo: **uniforme sobre los repartos compatibles** con lo que sabe el asiento:
mis cartas y mis descartes (no los tiene nadie), declaraciones de pares/juego y señas vistas
(siempre verdaderas, FEM VIII.4).

Muestreo secuencial exacto: para cada asiento s, con las N_s cartas que quedan,

```
Z_s = Σ_{t compatible} Π_r C(n_r, m_r) / C(N_s, 4)
```

y se toma su mano de la distribución condicionada exacta. El peso de importancia de cada
reparto es Π_s Z_s, así que el estimador autonormalizado converge al valor exacto (a diferencia
de `toolkit.sample_world`, que relaja restricciones).

Estimadores (pesos w_i, valor f(x_i)):

```
p̂   = Σ w_i·f(x_i) / Σ w_i
ESS = (Σ w_i)² / Σ w_i²
SE  = √( Σ w_i²·(f(x_i) − p̂)² ) / Σ w_i
```

IC95 de Wilson con n = ESS. **Número adaptativo**: lotes de 100 repartos hasta que
SE(P(ganar el lance actual)) ≤ 0,025 **y** ESS a posteriori ≥ 30 (con menos muestra efectiva el
propio SE no es fiable), con un mínimo de 200 y un máximo de 600 repartos por decisión. Si no
converge, la explicación lo dice (`converge: false`).
**Semilla**: cada bot usa su `random.Random(seed)`: mismas semillas, mismas decisiones
(`test_reproducible_con_la_misma_semilla`, `test_las_cartas_ocultas_nunca_se_usan`).

Cada probabilidad lleva su método (`Method`):

| Etiqueta | Significado |
|---|---|
| `exacta` | Enumeración completa, sin error de muestreo |
| `analitica_aproximada` | Marginales exactas + independencia |
| `monte_carlo` | Frecuencia ponderada sobre repartos, a priori (sin usar las acciones) |
| `posterior_bayesiana` | P(· \| acciones observadas), estimada con Monte Carlo ponderado |

## 5. Inferencia bayesiana (`bayes.py`)

Dos modelos separados:

* **Cartas**, P(H): combinatoria (secciones 3-4). Es objetivo.
* **Decisiones**, P(E | H): con qué probabilidad un jugador con la mano H hace lo observado.
  **Se estima con datos** (inferencia estadística): al final de cada jugada se enseñan las
  cartas (FEM VII.9), así que de cada decisión se conoce la mano de quien la tomó. Para cada
  lance y tipo de decisión se ajusta por **máxima verosimilitud** (Newton-Raphson) una
  regresión logística sobre la fuerza de la mano s:

  ```
  P(y = 1 | s) = σ(a + b·s)
  ```

  con y ∈ {envida, echa órdago al abrir, quiere un envite, responde con órdago, quiere un
  órdago}. Datos: 126 584 decisiones de 1000 partidas entre bots de nivel medio
  (`scripts/behaviour_fit.py`, semillas 0-999, distintas de las de evaluación); coeficientes
  en `behaviour_data.py`. El PlayerModel adapta el modelo a cada rival desplazando el
  intercepto en escala logit: Δa = (logit(tasa aprendida) − logit(tasa a priori))·confianza.
  Mus/corte y número de cartas pedidas usan las verosimilitudes heurísticas existentes de
  `agents/specialists.py` (sin ajuste).

```
P(H | E) = P(E | H)·P(H) / P(E),     P(E) = Σ_H P(E | H)·P(H)
P(E | H) = Π_e P(e | mano de quien actuó en H)
```

(independencia condicional de las acciones dada la mano: hipótesis del modelo).

Evidencias usadas (de la jugada actual y solo del historial público): mus y corte de la
**última** ronda de mus (los anteriores se decidieron con otras cartas), cartas pedidas en
cada descarte, envites, subidas, órdagos, pasos, «quiero» y «no quiero». Las señas y las
declaraciones son certezas y van como restricciones. Ninguna acción es una certeza: todas las
verosimilitudes tienen un suelo > 0, así que **un envite a grande desplaza la distribución
hacia manos con reyes pero no descarta un farol** (`test_un_envite_desplaza_la_creencia_pero_no_es_una_certeza`,
validado contra la posterior exacta en un caso reducido).

## 6. Valor esperado y equidad de partida (`decision.py`, `equity.py`)

```
EV(a) = Σ_s P(s | E) · U(a, s)
```

**Utilidad**: U(a, s) = P(ganar la partida) tras resolver el lance con la acción a si el reparto
es s. Se calcula con una cadena de Markov sobre los tantos que faltan (a, b):

```
E(a, b) = Σ_{x,y} D(x, y) · f(a − x, b − y)
```

con f = 1 si llego yo, 0 si llegan ellos, ½ si llegan los dos en la misma jugada (supuesto) y
E(a′, b′) en otro caso. D(x, y) **se mide**: tantos por jugada en 1000 partidas del motor entre
bots de nivel medio (`scripts/round_points.py`, semillas 0-999, 4836 jugadas), simetrizada.

Consecuencias que se modelan con el tanteo real del motor: paso, envite querido, envite no
querido (negada en el acto y deje en pares/juego/punto), órdago (U = 1 si gano el lance en s),
subidas, y la respuesta del compañero si aún puede querer. La respuesta rival a mi envite sale
de P(quiere | su mano en s), de modo que la **selección adversa** es automática:
P(gano | lo quieren) < P(gano). Tras **pasar**, si un rival envida, mi pareja responde con una
sola respuesta elegida en su **conjunto de información** (lo que sabría entonces, no las cartas
de s): r* = argmax_r Σ_s w_s·b(s)·U(r, s).

Magnitudes distintas que no se mezclan: P(ganar un lance) (`lances.py`), tantos de la jugada
en paso (su distribución), P(ganar la partida) (`equity.py`) y EV de una decisión
(`decision.py`). Además de E[U] se dan Var[U] y la media y varianza de la diferencia de
tantos. La decisión maximiza E[U], que ya incorpora el riesgo a través del marcador, con dos
reglas de **decisión bajo incertidumbre del modelo** (sección 10.3 explica por qué):

* **Echar un órdago — decisión robusta (maximin de Wald).** No se usa la P(lo quieren) del
  modelo, sino la peor política de aceptación posible: el rival lo quiere justo en los
  repartos en que me gana:

  ```
  EV_robusto(órdago) = Σ_s w_s · min( U(no lo quieren, s), U(lo quieren, s) )
  ```

* **Querer un órdago — decisión prudente.** E[U] = P(gano el lance | E); se compara la
  **cota inferior del IC95** de esa probabilidad (Wilson con n = ESS) con el valor de no
  quererlo. Con poca información efectiva, el intervalo es ancho y se rechaza.

**Teoría de juegos (información imperfecta)**: cada decisión se toma sobre el conjunto de
información (distribución a posteriori), no sobre un reparto concreto; la respuesta futura de
mi pareja también. Simplificaciones: una sola respuesta tras cada acción (sin resubidas) y los
demás lances de la jugada se tratan como parte del resto de la partida.

## 7. Integración multiagente

```
Orquestador
 ├─ comportamiento   PlayerModel → parámetros P(E|H) de cada rival
 ├─ bayesiano        repartos (Monte Carlo exacto) + pesos a priori y a posteriori → ctx.shared["belief"]
 ├─ analista         P(gana/pierde/nadie/empate de cartas) de cada lance, a priori y a posteriori; tantos en paso
 ├─ evaluador        EV(a) = Σ P(s|E)·U(a,s) para cada acción legal → ctx.shared["values"]
 └─ juez matemático  valida (probabilidades en [0,1] que suman 1, EV finitos, acciones legales)
                     y elige argmax EV; si algo falla, jugada conservadora y lo dice
```

Todos comparten la misma creencia (`ctx.shared`): nadie vuelve a muestrear por su cuenta.
Las decisiones de mus y descarte siguen en `MusPlanner`. Solo leen la `Observation`; los bots
externos y la API pública no cambian. Nivel nuevo en el registro: `matematico`.

## 8. Explicación de cada decisión

`bot.last_decision.explanation()["matematica"]` contiene: estado (lance, marcador, P(ganar la
partida) ahora), información conocida (mis cartas, declaraciones, señas, acciones observadas),
información desconocida (cartas y asientos), método (repartos, ESS a priori y a posteriori,
convergencia, SE), probabilidades de cada lance con su método e IC95, distribución de tantos,
EV y varianza de cada acción, acción elegida y justificación con la probabilidad de que la
elegida sea de verdad mejor que la segunda, Φ(Δ/√(SE₁²+SE₂²)). No se rellena ningún valor que
no se haya calculado.

## 9. Validación (pruebas automáticas)

| Propiedad | Prueba |
|---|---|
| La hipergeométrica suma 1 y coincide con la fórmula; no es binomial | `test_hipergeometrica_*` |
| Distribución exacta de una mano = fuerza bruta sobre las C(36,4) = 58 905 manos | `test_distribucion_exacta_de_una_mano_coincide_con_fuerza_bruta` |
| Condicionar es Bayes con verosimilitud 0/1 | `test_condicionar_es_bayes_con_verosimilitud_cero_uno` |
| Los descartes cambian el espacio muestral | `test_mis_descartes_cambian_el_espacio_muestral` |
| Repartos exactos: suman 1, cartas reales y distintas | `test_enumeracion_de_repartos_suma_uno` |
| Monte Carlo = exacto (± 4 SE) en los 5 lances, con restricciones | `test_monte_carlo_converge_al_valor_exacto_con_restricciones` |
| Restricciones y cartas conocidas respetadas en cada reparto | `test_el_muestreo_respeta_*`, `test_la_restriccion_de_declaraciones_se_respeta` |
| Reproducibilidad | `test_reproducible_con_la_misma_semilla`, `test_la_tabla_de_tantos_es_reproducible` |
| Bayes con un ejemplo conocido (prueba diagnóstica) | `test_bayes_con_un_ejemplo_conocido` |
| Posterior por Monte Carlo = posterior exacta; un envite no es certeza | `test_un_envite_desplaza_la_creencia_pero_no_es_una_certeza` |
| Ninguna verosimilitud es 0 | `test_todas_las_verosimilitudes_tienen_suelo` |
| Equidad: simétrica, monótona, en [0, 1] | `test_equidad_simetrica_monotona_y_en_rango` |
| Querer un órdago: E[U] = P(ganar el lance) y se decide con la cota inferior del IC95; EV de un envite = fórmula a mano | `test_querer_un_ordago_*`, `test_valor_esperado_de_un_envite_*` |
| Órdago propio: EV robusto = Σ w·min(U(no), U(sí)) | `test_echar_un_ordago_es_robusto_frente_a_la_peor_aceptacion` |
| El ajuste logístico por máxima verosimilitud recupera parámetros conocidos; todas las decisiones ajustadas con pendiente > 0 | `test_el_ajuste_logistico_*`, `test_el_modelo_de_decisiones_*` |
| Las cartas ocultas nunca se usan (misma observación y decisión si cambian las cartas ajenas) | `test_las_cartas_ocultas_nunca_se_usan` |
| Partidas completas sin errores con todas las variantes; explicación serializable | `test_el_bot_matematico_*`, `test_todas_las_variantes_*` |
| El juez rechaza cálculos inválidos | `test_el_juez_matematico_rechaza_calculos_invalidos` |

## 10. Experimentos

Todo es reproducible con semillas fijas (`experiments/probability.py`; resultados en
`experiments/results/probabilidad_*.json`). Ninguna cifra de esta sección está retocada.

### 10.1 Error de estimación de P(ganar el lance)

300 situaciones reales de partida (decisiones en lances de partidas entre bots medios, 77 con
declaraciones o señas). Referencia: Monte Carlo exacto con 20 000 repartos (SE ≤ 0,0036).

```
python -m experiments.probability estimacion 300
```

| Estimador | Sesgo (± SE) | RMSE | Cobertura IC95 |
|---|---|---|---|
| Monte Carlo nuevo, 200 repartos | +0,0000 (± 0,0018) | 0,031 | **95,0 %** |
| Monte Carlo antiguo (`toolkit.sample_world`), 200 | −0,0016 (± 0,0017) | 0,029 | — |
| Analítica (marginales exactas + independencia) | **+0,0102 (± 0,0007)** | 0,016 | — |

* El IC95 del Monte Carlo nuevo cubre la referencia en el 95,0 % de los casos: el error
  estándar está bien calculado.
* El sesgo teórico del muestreador antiguo (relaja restricciones si falla) **no es medible**
  en estas situaciones: la relajación casi nunca se activa en partidas reales.
* La aproximación analítica tiene un **sesgo sistemático significativo** (+1 punto) por
  suponer independencia, pero menor RMSE que Monte Carlo con 200 repartos (no tiene varianza
  de muestreo): un ejemplo de compromiso sesgo-varianza.

### 10.2 Partidas

Cada variante juega en pareja contra dos bots *medio* (rival de referencia común); 200
semillas (500 000-500 199), cada una dos veces cambiando de asiento (mus duplicado): 400
partidas por variante, las mismas cartas para todas. Comparación **pareada por semilla** con
A_pro y corrección de Holm. Calibración: Brier y log-loss de la P(ganar el lance) usada en
cada decisión frente al resultado real del lance (SE por conglomerados de partida).

```
python -m experiments.probability partidas 200
```

| Variante | Nivel | % victorias [IC95 Wilson] | Δ tantos/partida [IC95] | Brier (± SE) | Log-loss (± SE) | ms/decisión (p95) |
|---|---|---|---|---|---|---|
| A_medio | `medio` | 48,0 [43,1-52,9] | −0,91 [−2,52, +0,71] | 0,176 (± 0,002) | 0,529 (± 0,006) | 9 (25) |
| A_pro | `profesional` | **54,8** [49,9-59,6] | +1,77 [+0,09, +3,44] | 0,174 (± 0,002) | 0,519 (± 0,004) | 40 (125) |
| B | `mat_exacto` | 40,2 [35,6-45,1] | +0,40 [−1,19, +1,98] | 0,194 (± 0,002) | 0,570 (± 0,005) | 42 (70) |
| C | `mat_bayes` | 49,8 [44,9-54,6] | −1,71 [−3,49, +0,07] | 0,139 (± 0,002) | 0,432 (± 0,007) | 74 (249) |
| D | `mat_mc` | 37,0 [32,4-41,8] | −3,49 [−5,19, −1,79] | 0,191 (± 0,002) | 0,564 (± 0,006) | 35 (126) |
| E | `mat_utilidad` | 28,0 [23,8-32,6] | −6,26 [−8,40, −4,11] | 0,197 (± 0,003) | 0,580 (± 0,009) | 90 (223) |
| F | `matematico` | 44,2 [39,5-49,1] | −3,89 [−6,18, −1,60] | **0,132** (± 0,003) | **0,414** (± 0,007) | 148 (390) |

Ningún bot falló en las 2800 partidas (ni excepciones, ni jugadas ilegales, ni tiempos
excedidos). Una ejecución anterior encontró un fallo (un `KeyError` cuando un reparto resultaba
imposible a mitad de muestreo, en 1 partida de E y 1 de F); se corrigió, tiene prueba de
regresión y esta tabla es la de después del arreglo.

Diferencia de % de victorias frente a A_pro (pareada por semilla):

| Variante | Diferencia [IC95] | p | p (Holm) |
|---|---|---|---|
| A_medio | −6,8 [−11,5, −2,0] | 0,006 | 0,012 |
| B | −14,5 [−19,5, −9,5] | < 0,001 | < 0,001 |
| C | −5,0 [−10,1, +0,1] | 0,055 | 0,055 (no significativa) |
| D | −17,8 [−22,9, −12,6] | < 0,001 | < 0,001 |
| E | −26,8 [−32,2, −21,3] | < 0,001 | < 0,001 |
| F | −10,5 [−15,5, −5,5] | < 0,001 | < 0,001 |

### 10.3 Interpretación

1. **Las probabilidades del motor nuevo son mejores.** Con Bayes (C y F) la P(ganar el lance)
   está mucho mejor calibrada que en el bot actual: Brier 0,132-0,139 frente a 0,174, y
   log-loss 0,41-0,43 frente a 0,52. Las diferencias son de unos 12 errores estándar.
2. **Mejores probabilidades no bastan para ganar más partidas.** Ninguna variante nueva supera
   al profesional actual frente a este rival. C (probabilidades nuevas con la estrategia de
   siempre) no se distingue estadísticamente de él; F queda 10,5 puntos por debajo.
3. **Leer al rival es imprescindible.** Sin Bayes (B, D, E) las variantes pierden mucho:
   las acciones observadas contienen información que el reparto a priori no tiene.
4. **El punto débil es el modelo de decisiones del rival, P(E | H)**, no la combinatoria.
   Historia del diagnóstico (60 semillas, 500 000-500 059, 120 partidas por bot):
   * Primera versión (umbrales del modelo de decisiones puestos a mano; commit `a378004`): en
     el experimento completo F ganaba **más tantos** que nadie (+3,4 por partida) pero menos
     partidas (48,5 %). El diagnóstico mostró por qué: echaba 373 órdagos (el profesional, 105)
     y perdía 52 partidas por órdago (el profesional, 14).
   * Se sustituyeron los umbrales por regresiones logísticas **ajustadas con datos**. Peor
     aún: 204 órdagos propios y 69 partidas perdidas por órdago. Midiendo predicción frente a
     realidad en 100 órdagos: P(lo quieren) predicha 0,14, real 0,28; P(gano si lo quieren)
     predicha 0,20, real 0,07. Causa: **sesgo de población**. El modelo se ajustó con órdagos
     de bots que solo los echan con manos muy fuertes (y casi nunca se quieren); frente a
     órdagos de farol, el rival los quiere el doble.
   * Respuesta: órdago propio con **decisión robusta** (maximin) y aceptación de órdagos con
     la **cota inferior del IC95**, más ESS mínimo de 30. Partidas perdidas por órdago: 19.
     Ante un órdago rival, P(gano) a posteriori 0,14 frente a 0,10 real (a priori, 0,51).
   * Con estas reglas F apenas echa órdagos y pierde la fuente de tantos de los faroles; el
     resultado final es el de la tabla 10.2.
5. **Coste.** F tarda 148 ms de media por decisión (p95 0,39 s) en CPython, frente a
   40 ms del profesional. Es usable en la web (Pyodide es más lento, del orden de 2-3×), pero
   no es gratis.

**Conclusión para la defensa.** El motor cumple su objetivo matemático: probabilidades
correctas, reproducibles, con su incertidumbre y validadas (exacto frente a Monte Carlo,
cobertura del 95 %, mejor calibración). En cambio, **no hay evidencia estadística de que
decidir por valor esperado con este modelo de rival gane más partidas** que el bot
profesional ajustado empíricamente. La causa medida es la especificación del modelo de
decisiones del rival. Por eso el nivel `matematico` queda como nivel experimental (en el
registro y la arena) y los niveles de la web no cambian. Trabajo futuro con más
fundamento: un modelo de decisiones condicionado al contexto (marcador, quién envidó y cuánto)
y el cálculo de estrategias de equilibrio del subjuego de envites (p. ej. CFR) en lugar de
respuestas a un modelo fijo del rival.

## 11. Supuestos y límites

* El modelo de decisiones de los rivales (umbrales, farol) es una hipótesis; el PlayerModel lo
  ajusta con la experiencia, pero sus parámetros a priori no están calibrados contra jugadores
  reales.
* D(x, y) se ha medido con bots de nivel medio; con otros rivales el ritmo de la partida cambia.
* Las acciones se suponen condicionalmente independientes dada la mano.
* Sin resubidas en el árbol de decisión; los demás lances de la jugada no se modelan uno a uno.
* La aproximación analítica (B) ignora que los asientos compiten por las mismas cartas.
