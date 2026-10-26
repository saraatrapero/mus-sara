# Reglas del juego

La fuente de verdad es el **Reglamento de Juego de la Federación Española de Mus (FEM)**.
Cada regla del motor indica su artículo. Las que el Reglamento **no especifica** están marcadas
como **[CONVENCIÓN]**: siguen el Mus tradicional, son configurables en
`config/rules.default.toml` y se han trasladado al profesor
([preguntas](design/11-preguntas-profesor.md)).

## Resumen

| Regla | Fuente | Implementación |
|---|---|---|
| Baraja española de 40 naipes | FEM II.3 | `engine/cards.py` |
| Ocho reyes y ocho ases (3 = rey, 2 = as) | FEM II.3 | `normalized_rank` |
| Reparto de uno en uno, de derecha a izquierda; mano = a la derecha del que reparte | FEM III.2, VIII.8 | `MusGame._start_round` |
| Mus: habla el mano; mus de los cuatro → descarte | FEM IV | `_on_mus` |
| Descarte: empieza el que reparte y termina el mano | FEM III.11 | `_discard_order` |
| Se sirve en el orden del reparto | FEM III.2 | `_on_discard` |
| Mazo agotado → se baraja el descarte | FEM III.15 | `_reshuffle_discards` |
| Orden de lances: grande, chica, pares, juego o punto | FEM VII.2 | `_advance_lance` |
| Declaración pública de pares y juego; solo hablan quienes los tienen | FEM VI.5, VI.22 | `_open_lance` |
| Mano del lance = primero que tiene pares/juego | FEM VIII.8 | `LanceState.participants` |
| Envido = 2; envido N | FEM VIII.8 | `BetAction` |
| Si uno quiere y su compañero no, vale el quiero | FEM VI.4 | `_on_lance_action` (Reject) |
| Negada: 1 tanto por no aceptar la primera apuesta | FEM VIII.8 | `negada_points` |
| Envites contados al final de la jugada en orden de lances | FEM VI.6, VII.2 | `_finish_round` |
| Deje en pares, juego y punto | FEM VII.1 | `_score_lance` |
| Órdago aceptado: se enseñan las cartas y se resuelve el juego | FEM VI.6 | `_resolve_ordago` |
| El órdago anula envites aceptados anteriores | FEM VII.12 | la partida termina |
| Nunca órdago a dos lances a la vez | FEM IV.6 | un único `OrdagoAction` por lance |
| Postre con 33: solo "quiero y no pierdo" ante órdago a juego | FEM VI.9-10 | `_must_accept_no_lose` |
| Los cuatro enseñan las cartas al acabar juego/punto | FEM VII.9 | evento `HandsRevealed` |
| "Estamos dentro" a ≤ 4 tantos | FEM VII.7 | evento `TeamIsIn` |
| Juego a 40 tantos (40-60) | FEM Intro E | `target_points` |
| Señas oficiales, siempre verdaderas | FEM VIII.2-7 | `MusGame.signal`, `engine/signals.py` |

## Convenciones (no especificadas por la FEM)

| Concepto | Valor | Configuración |
|---|---|---|
| Orden en grande | R(12, 3) > C > S > 7 > 6 > 5 > 4 > A(1, 2) | — |
| Orden en chica | inverso | — |
| Valor para juego/punto | figuras 10, as 1, resto su número | — |
| Orden del juego | 31 > 32 > 40 > 37 > 36 > 35 > 34 > 33 | — |
| Empates | gana el más cercano al mano | — |
| Grande/chica en paso | 1 | `paso_points` |
| Par / medias / duples | 1 / 2 / 3 por jugador | `par_points`… |
| Juego 31 / otro juego | 3 / 2 por jugador | `juego_31_points`, `juego_points` |
| Punto | 1 | `punto_points` |
| Descarte mínimo | 1 carta | `min_discard` |
| Envite rechazado tras subidas | se cobra la apuesta anterior | — |
| Negada que alcanza el objetivo | termina el juego | `end_on_immediate_points` |

## Turnos secuenciales

En la mesa física se puede hablar "a la vez" (FEM VI.1, VI.4, IV.4). En digital, el motor da
la palabra de uno en uno, en sentido antihorario desde el mano del lance:

- Ante un envite responde primero el rival siguiente en el orden. Si dice *no quiero*, la
  palabra pasa a su compañero (FEM VI.4: vale el quiero).
- Mientras hay una apuesta pendiente solo puede hablar la pareja contraria (FEM VI.2).

## Artículos que no aplican en digital

Los artículos sobre naipes de más o de menos, mus visto, carta descubierta, contar el mazo,
enseñar cartas, gestos o declaraciones incorrectas (III.4-14, III.16, VI.10-25, VII.10-11,
IX) describen **errores físicos imposibles por construcción**: el motor reparte siempre cuatro
cartas, calcula las declaraciones y no existe la acción "enseñar". El tiempo de juego (cap. V)
se traduce en un límite de tiempo por decisión.

## Partida

El Reglamento habla de partidas "a cinco juegos". MUS.ST juega por defecto **un juego a 40
tantos** (configurable a 20-60). Pendiente de confirmar con el profesor (P4).

## Señas y miradas (FEM VIII)

Activadas con `signals_enabled` (la web las activa; el torneo y los tests de referencia no).

- **Solo señas oficiales y verdaderas**: el motor rechaza una seña que la mano no respalda
  (FEM VIII.4). Se pueden hacer **después de cortar el mus** y cada una una vez por jugada.
- **Miradas**: cada jugador mira a su compañero, a un rival o a la mesa durante unos pasos de
  tiempo, al azar (`gaze_weights`, `gaze_min_ticks`, `gaze_max_ticks`). Hacia dónde mira cada
  uno es público.
- **Quién ve la seña**: exactamente quienes miran en ese instante al que la hace. Si es el
  compañero, la ventaja es de la pareja; si es un rival, la información es para el rival; si
  no mira nadie, la seña se pierde. Quien la hace sabe quién le miraba.
- **Elegir a quién miras**: una persona puede fijar su mirada (`MusGame.look`, en la web
  pulsando la cara de un jugador) para vigilar a su compañero; dura `gaze_max_ticks` pasos.
- **Tiempo**: avanza con cada acción y con `MusGame.tick()` (en la web, cada ~2 s).
- **Privacidad**: cada asiento solo recibe las señas que ha visto (eventos privados
  `SignalSeen`/`SignalMade`). Los bots usan las señas vistas para restringir las manos que
  simulan (`toolkit.sample_world`).
- **Reproducible**: las miradas usan un generador aparte derivado de la semilla, así que
  activar las señas no cambia el reparto; el registro de la partida guarda señas y pasos del
  reloj para reconstruirla.
