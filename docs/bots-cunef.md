# Bots de mus-cunef

MUS.ST incluye tres bots que vienen del otro repositorio del equipo,
[mus-cunef/mus](https://github.com/mus-cunef/mus) (paquete `musarena`, licencia MIT). Juegan
sobre el motor FEM de MUS.ST **sin haberlos reescrito**: un adaptador traduce entre las dos APIs.

| Bot | Qué hace | Necesita |
|---|---|---|
| `basico` | Reglas sencillas sobre la fuerza de la mano en cada lance | nada (biblioteca estándar) |
| `reglas` | Lee la mesa (qué manos puede tener cada uno según lo que han dicho y apostado), calcula la probabilidad de ganar cada lance y decide pensando en ganar la vaca | numpy |
| `reglas_agresivo`, `reglas_conservador` | El mismo bot con otros umbrales (corta, envida y echa órdagos antes o después) | numpy |
| `inteligente` | Red neuronal entrenada en mus-cunef: primero imitando al bot `reglas` y después con aprendizaje por refuerzo (PPO) | numpy |

```bash
pip install -e ".[cunef]"     # numpy; basico funciona sin él
mus-torneo -n 6 --participantes inteligente,reglas,basico,medio,profesional
```

Desde código:

```python
from musst import play_game
from musst.bots.cunef import inteligente, reglas

print(play_game([inteligente(), reglas(), inteligente(), reglas()], seed=1).result)
```

En la web de GitHub Pages (Python en el navegador con Pyodide) numpy no se carga para no
añadir unos 7 MB de descarga, así que allí solo está `basico`. `reglas` e `inteligente` juegan en
el torneo automático, cuya clasificación sí se ve en la web (**Campeonatos → Torneo de bots**).

## Cómo funciona el adaptador

Las dos APIs se parecen pero no son iguales:

| | mus-cunef (`musarena`) | MUS.ST (`musst`) |
|---|---|---|
| Método | `Player.choose_action(observation, legal_actions)` | `Bot.decide(observation)` |
| Acciones legales | lista de acciones concretas (`Envido(4)`, `Descarte({…})`) | `ActionSpec` con mínimo y máximo (`bet 2..99`) |
| Observación | `Observation` con `historial` de `Evento`, `resultados`, `manos_jugadas`… | `Observation` con `history` de eventos en diccionarios |

`PlayerComoBot` (en `src/musst/bots/adaptador.py`) envuelve un `Player` y, en cada turno:

1. **Traduce la observación** (`traducir_observacion`) usando **solo** la observación de MUS.ST:
   sus cartas, el marcador, la apuesta en curso, las declaraciones de pares y juego, el historial
   público de la jugada y las manos enseñadas en las jugadas ya terminadas. Nunca mira el estado
   del motor, así que no puede ver cartas ajenas.
2. **Construye la lista de acciones legales** (`acciones_legales`) a partir de las `ActionSpec`,
   con las cantidades que admiten los dos reglamentos.
3. **Pregunta al bot** y **traduce su respuesta** de vuelta (`a_musst`). Si el bot devuelve algo
   que no estaba en la lista, el adaptador lanza `AccionNoTraducible`: el runner lo cuenta como
   falta y su pareja pierde la partida, sin romper el torneo.

El código copiado está en `src/musst/compat/musarena/` con los mismos nombres de módulo que en el
original. Solo se han cambiado los imports (`musarena.*` → `musst.compat.musarena.*`) y una
función de `ia/codificacion.py`, marcada con `ADAPTADO para MUS.ST`. No se ha copiado su motor,
su web ni el entrenamiento (PyTorch).

## Diferencias de reglas y cómo se resuelven

mus-cunef implementa el mus "clásico" de su `docs/reglas.md`; MUS.ST, el Reglamento FEM.

| Diferencia | mus-cunef | MUS.ST (FEM) | Solución en el adaptador |
|---|---|---|---|
| Final de partida | Vacas de 40 tantos, al mejor de 3 o 5 | Una partida a `target_points` (40 por defecto) | Se le dice que se juega a **una** vaca y los tantos se **escalan a 40** si la partida es a otro número |
| Primera mano | Mano corrida | El reparto fija la mano | `corrida=False` siempre |
| Tope de las apuestas | El total no pasa de 40 | Tope técnico `max_bet` (99) | Solo se ofrecen envites de 2 a 40 y subidas que dejen el total en 40 o menos |
| "Quiero y no pierdo" (FEM VI.9) | No existe | El postre con 33 ante un órdago a juego | Si es la única forma de querer, `Quiero` se traduce a ella |
| Señas | No hay | Opcionales (FEM VIII) | Estos bots no hacen señas ni las ven |
| Lances sin apuesta | Se anotan como "sin apuesta" | El lance empieza con `betting: False` | Se traduce a `SIN_APUESTA` |

En lo demás coinciden: 8 reyes, orden de grande y chica, pares (par, medias, duples), juego
(31 > 32 > 40 > 37 … > 33), punto, tanteo del recuento (par 1, medias 2, duples 3, 31 vale 3 y
otro juego 2), quién habla en pares y juego y que los empates los gana el más cercano a la mano.

## Cómo se prueba

| Test | Qué comprueba |
|---|---|
| `tests/compat/test_adaptador.py` | En miles de estados de partidas al azar, **cada** acción de la lista traducida es legal en el motor; no falta ningún tipo de acción; la observación no lleva cartas ajenas; el bot aleatorio de musarena juega 30 partidas completas sin faltas; una acción fuera de la lista hace perder la partida; los tantos se escalan |
| `tests/compat/test_bots_cunef.py` | `basico`, los tres estilos de `reglas` e `inteligente` juegan partidas completas sin faltas y en menos de 2 s por decisión, `reglas` recibe las manos enseñadas e `inteligente` carga el modelo entrenado y gana a `sencillo` |
| `tests/unit/test_bradley_terry.py` | El Elo del torneo |

## Resultados medidos

40 partidas con repartos duplicados por cruce (20 contra `medio`), sin ninguna falta:

| | contra `sencillo` | contra `basico` | contra `reglas` | contra `medio` |
|---|---|---|---|---|
| `inteligente` | 80 % | 75 % | 80 % | 65 % |
| `reglas` | 68 % | 65 % | — | 35 % |
| `basico` | 45 % | — | — | — |

La clasificación completa, con todos los bots, está en [Clasificación de bots](clasificacion.md).
