# 03 — Reglas, máquina de estados, GameEngine y puntuación

## 1. Reglas: qué dice el Reglamento FEM y qué no

El Reglamento FEM regula sobre todo **procedimiento** (sorteo, reparto, mus, envites, tanteo,
señas, errores y penalizaciones), pero **no define el valor de las cartas ni de las jugadas**:
los da por sabidos. Por eso las reglas se dividen en dos tipos:

- **[FEM]**: implementada según el artículo citado.
- **[CONVENCIÓN]**: regla tradicional del Mus (ocho reyes) que la FEM no escribe. Se implementa
  en `config/rules.default.toml`, se documenta y se lista en las preguntas al profesor (P5).

### 1.1 Baraja y valores

| Regla | Tipo | Detalle |
|---|---|---|
| Baraja española de 40 naipes (1-7, sota, caballo, rey; oros, copas, espadas, bastos) | FEM II.3 | Sin 8 ni 9 |
| Ocho reyes y ocho ases: el 3 cuenta como rey y el 2 como as | FEM II.3 | Configurable (`modalidad = "8R8A"`); otra modalidad solo por configuración |
| Orden en grande: R(12,3) > C(11) > S(10) > 7 > 6 > 5 > 4 > A(1,2) | CONVENCIÓN | Chica: el orden inverso |
| Valor para juego/punto: R, C, S = 10 (el 3, al ser rey, vale 10); A (1 y 2) = 1; resto, su número | CONVENCIÓN | |
| Pares: par (2 iguales), medias (3), duples (2 pares o 4 iguales) | FEM VIII.2 (los nombra) / CONVENCIÓN (valor) | |
| Juego: suma ≥ 31. Orden: 31 > 32 > 40 > 37 > 36 > 35 > 34 > 33 | FEM nombra 31 como máximo y 33 como mínimo (VI.7-8) / CONVENCIÓN (orden completo) | |
| Punto: si nadie tiene juego, gana la suma más alta (máximo 30) | FEM VI.7, VIII.8 | |
| Empate en cualquier lance: gana el más cercano al mano | CONVENCIÓN | |

### 1.2 Desarrollo de una jugada

| Paso | Regla | Fuente |
|---|---|---|
| Asientos | 4 asientos fijos; pareja A = {0, 2}, pareja B = {1, 3}. No cambian durante la partida | FEM II.1-2 |
| Primer reparto | Por sorteo de palo (se simula con la seed) | FEM III.1 |
| Reparto | 4 cartas, de una en una, de derecha a izquierda (antihorario) | FEM III.2 |
| Mano | El jugador a la derecha del que reparte; la mano rota cada jugada | FEM VIII.8 |
| Visibilidad | Nadie ve las cartas hasta terminar el reparto | FEM III.6 (garantizado por diseño) |
| Mus | Habla primero el mano. El postre de la pareja contraria solo puede cortar después de que el mano dé mus; el compañero del mano puede cortar siempre; el cuarto, cuando la pareja mano lo haya dado | FEM IV.4 |
| Descartes | Si los cuatro dan mus, cada uno descarta de 1 a 4 cartas y se repone; si se acaba el mazo, se rebaraja el descarte | FEM III.11, III.15 · CONVENCIÓN (mínimo 1) |
| A falta de tanto | El mus puede cortarse en cualquier momento | FEM IV.7 (ver P6) |
| Lances | Grande → Chica → Pares → Juego o Punto | FEM VII.2 |
| Declaración | En pares y juego se declara públicamente sí/no; solo hablan quienes los tienen | FEM VI.5, VI.22, IX.1 |
| Mano del lance | En pares/juego, el primero que los tiene | FEM VIII.8 |
| Órdago | Solo a un lance cada vez | FEM IV.6 |
| Mostrar cartas | Los cuatro, al acabar el lance de juego o punto, o cuando se acepta un órdago | FEM VII.9, VI.6 |

**Decisión de diseño — turnos secuenciales.** En la mesa física los jugadores pueden hablar
"a la vez" (FEM VI.1, VI.4, IV.4). En digital, el motor da la palabra **de uno en uno** en
orden antihorario empezando por el mano del lance. Las reglas de prioridad de la FEM se
traducen así:

- **VI.4** ("si uno quiere y su compañero no quiere, vale el quiero"): si el primer rival
  responde *no quiero*, la palabra pasa a su compañero. Solo es *no quiero* si lo dicen los dos.
- **VI.2** (no se sube hasta que los contrarios respondan): sale solo, porque mientras hay una
  apuesta pendiente el turno es de la pareja contraria.
- **VI.1** (envites distintos simultáneos): no puede ocurrir.
- **IV.4**: el orden secuencial cumple siempre las condiciones del artículo.

### 1.3 Envites

| Acción | Significado | Fuente |
|---|---|---|
| `Pass` (paso) | No envidar | FEM VIII.8 |
| `Bet(n)` | Envido: n = 2 por defecto; "envido N" con N ≥ 2 | FEM VIII.8 |
| `Raise(n)` | Reenvite: subir la apuesta (ver P7: FEM define "reenvido" como *doblar*) | FEM VIII.8 |
| `Accept` (quiero) | | FEM VI.3-4 |
| `Reject` (no quiero) | | FEM VI.3-4 |
| `Ordago` | Apostar el juego completo | FEM VIII.8 |
| `AcceptNoLose` ("quiero y no pierdo") | La única forma legal de que el postre con 33 acepte un órdago a juego | FEM VI.9-10 |

Restricciones que el `RulesEngine` comprueba:

- Solo puede envidar o responder en pares/juego quien los tiene (FEM VI.5, VI.22-23).
- El postre con 33 no puede aceptar un órdago a juego salvo con `AcceptNoLose` (FEM VI.9).
- Cualquier envite puede aceptarse, aunque la cantidad supere los tantos que faltan (FEM VI.6, VI.8).

### 1.4 Artículos FEM que no aplican en digital (y por qué)

| Artículos | Situación física | Tratamiento digital |
|---|---|---|
| III.4-5, III.7-10, III.12-14, III.16 | Naipes de más/menos, mus visto, carta descubierta, contar el mazo | **Imposibles por construcción.** El motor reparte siempre 4 cartas y la UI no expone el mazo. Se documentan para justificarlo en la defensa. |
| VI.10-11, VI.13, VI.24-25, VII.10-11 | Enseñar naipes, separar amarracos, mirar cartas del contrario | Imposible: no existe acción "enseñar". |
| VI.15-20, VIII.4-6 | Declarar jugadas, señas parciales | La declaración sí/no la hace el motor (siempre veraz) y las señas van por `SignalSystem`. |
| IX.1 | Errores al declarar pares/juego | Imposible: el motor calcula la declaración. |
| V | Tiempo de juego | Se traduce en un timeout por acción (configurable) en el `GameRunner`. |
| I, X, XI, XII | Torneos presenciales, árbitros, actas | Inspiran el diseño de la Arena; no son reglas del motor. |

### 1.5 SignalSystem (preparado, desactivado en v1)

Modela las señas oficiales de FEM VIII.2 (dos reyes, dos ases, pares, medias de reyes, medias
de ases, medias, duples, juego, treinta y una, treinta, veintinueve, ciego, cortar el mus,
envidar más) con sus restricciones (VIII.3-6: no antes de cortar el mus, medias no-reyes tras
la grande, sin señas parciales, solo para transmitir la jugada propia).

Una seña es una `SignalAction` que el `RulesEngine` valida **contra las cartas reales** del
emisor (no se puede mentir con una seña, VIII.4). Genera un evento **privado para el
compañero**, con probabilidad configurable de que lo vea también cada rival (`interception_p`),
para simular que en la mesa física los rivales pueden ver las señas. Queda desactivado en v1
(`signals.enabled = false`): con señas, el modelado de información se complica mucho y eso
debe validarse antes.

## 2. Máquina de estados

### 2.1 Estado de la partida (runtime)

```
WAITING ──start──► PLAYING ◄──resume── PAUSED
                     │  └──pause/desconexión──►┘
                     ├──fin de juego──► FINISHED
                     └──error irrecuperable──► ERROR   (la partida se guarda; el torneo continúa)
```

### 2.2 Fases de una jugada (engine)

```
            ┌──────────────────────────────────────────────────────────┐
            ▼                                                          │
        DEALING                                                        │
            ▼                                                          │
     MUS_DECISION ──todos "mus"──► DISCARD ──reposición──┐             │
            │ alguien corta                              │             │
            ▼                     ◄──────────────────────┘ (vuelve a MUS_DECISION)
         GRANDE ──órdago aceptado──────────────────────┐               │
            ▼                                          │               │
          CHICA ──órdago aceptado─────────────────────►│               │
            ▼                                          │               │
   PARES_DECLARATION                                   │               │
            ├─ ambas parejas tienen ─► PARES ─órdago──►│               │
            ├─ solo una / ninguna (sin envites) ───┐   │               │
            ▼                                      ▼   │               │
   JUEGO_DECLARATION ◄─────────────────────────────┘   │               │
            ├─ ambas tienen juego ─► JUEGO ─órdago────►│               │
            ├─ una sola tiene juego (sin envites) ─┐   │               │
            ├─ nadie tiene juego ─► PUNTO ─órdago─►│   │               │
            ▼                                      ▼   ▼               │
         SHOWDOWN (los 4 enseñan, FEM VII.9) ◄──────── ORDAGO_SHOWDOWN │
            ▼                                          │               │
         SCORING (tanteo en orden de lances)           │               │
            ▼                                          ▼               │
     CHECK_GAME_END ──no──► rotar mano ────────────────────────────────┘
            │ sí
            ▼
        GAME_OVER
```

Cada lance de envites tiene su propia sub-máquina:

```
OPEN(turno = mano del lance) ──Pass──► siguiente jugador / si todos pasan ► CLOSED_PASSED
     │ Bet / Ordago
     ▼
PENDING(apuesta, pareja que responde)
     ├─ Accept / AcceptNoLose ─────────────► CLOSED_ACCEPTED (o ORDAGO_SHOWDOWN)
     ├─ Reject (primer rival) ─────────────► PENDING (responde su compañero)
     ├─ Reject (los dos) ──────────────────► CLOSED_REJECTED (negada o deje en el acto)
     └─ Raise / Ordago ────────────────────► PENDING (responde la otra pareja)
```

Las transiciones están en una **tabla explícita** (`fsm.py`: `ALLOWED: dict[Phase, set[Phase]]`).
Cualquier transición que no esté en la tabla lanza `IllegalTransition`, y un test recorre la
tabla completa.

## 3. Diseño del GameEngine

### 3.1 Acciones tipadas

```python
@dataclass(frozen=True)
class MusAction:            # dar mus
@dataclass(frozen=True)
class CutMusAction:         # cortar ("no hay mus")
@dataclass(frozen=True)
class DiscardAction:        cards: tuple[Card, ...]          # 1..4
@dataclass(frozen=True)
class PassAction:
@dataclass(frozen=True)
class BetAction:            amount: int                      # ≥ min_bet (2)
@dataclass(frozen=True)
class RaiseAction:          amount: int                      # incremento sobre la apuesta vigente
@dataclass(frozen=True)
class AcceptAction:
@dataclass(frozen=True)
class AcceptNoLoseAction:   # "quiero y no pierdo" (FEM VI.9-10)
@dataclass(frozen=True)
class RejectAction:
@dataclass(frozen=True)
class OrdagoAction:
@dataclass(frozen=True)
class SignalAction:         signal: Signal                   # desactivado en v1

Action = MusAction | CutMusAction | DiscardAction | ...      # unión cerrada
```

Las acciones se serializan a JSON con un discriminador `"type"` para el API web y el sandbox.

### 3.2 Estado (secreto, solo en el motor)

```python
@dataclass(frozen=True)
class GameState:
    config: RulesConfig
    seats: tuple[SeatInfo, SeatInfo, SeatInfo, SeatInfo]
    score: dict[TeamId, int]
    dealer: Seat
    phase: Phase
    round: RoundState | None  # jugada en curso
    rng_state: RngState  # para reproducibilidad
    status: GameStatus


@dataclass(frozen=True)
class RoundState:
    hands: tuple[Hand, Hand, Hand, Hand]  # ← SECRETO
    deck: tuple[Card, ...]  # ← SECRETO
    discard_pile: tuple[Card, ...]  # ← SECRETO
    mus_rounds: int
    turn: Seat | None
    lances: dict[Lance, LanceState]  # apuestas, resultado pendiente
    declarations: dict[Lance, dict[Seat, bool]]  # pares sí/no, juego sí/no (público)
    pending_points: list[PendingPoints]  # se tantea al final (FEM VI.6)
```

### 3.3 Interfaz pública del motor

```python
class GameEngine:
    def new_game(self, config: RulesConfig, seed: int) -> tuple[GameState, list[GameEvent]]: ...
    def apply(
        self, state: GameState, seat: Seat, action: Action
    ) -> tuple[GameState, list[GameEvent]]:
        """Valida con RulesEngine; si es ilegal, lanza IllegalAction y no cambia nada."""


class RulesEngine:
    def legal_actions(self, state: GameState, seat: Seat) -> list[ActionTemplate]: ...
    def validate(self, state: GameState, seat: Seat, action: Action) -> Validation: ...
```

- **Funciones puras**: el mismo estado y la misma acción dan siempre el mismo resultado. El
  azar sale de un `random.Random(seed)` cuyo estado forma parte del `GameState`.
- **Nadie fuera del motor construye un `GameState`**: los bots reciben `Observation`.
- `ActionTemplate` describe acciones parametrizadas (por ejemplo `Bet(min=2, max=None)`,
  `Discard(min=1, max=4)`), para que el frontend y los bots sepan qué pueden hacer.
- API de alto nivel para el Req 1.1:

```python
from musst import play_game
from musst.bots.builtin import SimpleBot

result = play_game(bots=[SimpleBot(), SimpleBot(), SimpleBot(), SimpleBot()], seed=12345)
print(result.winner, result.final_score, len(result.events))
```

## 4. Sistema de puntuación

### 4.1 Cuándo se apunta (FEM VII.2, VI.6)

| Momento | Qué se apunta |
|---|---|
| **En el acto**, durante el lance | Negada (1 tanto por no aceptar la primera apuesta de un lance) o el valor de los envites revocados y no aceptados; el deje en pares/juego/punto |
| **Al final de la jugada**, en orden grande → chica → pares → juego/punto | Envites aceptados; grande y chica en paso (1); valor de los pares; valor del juego; punto (1) |
| **Órdago aceptado** | Se enseñan las cartas; quien gana el lance gana el juego. Se anulan los envites aceptados en lances anteriores (FEM VII.12) |

### 4.2 Valores [CONVENCIÓN, configurables]

| Concepto | Valor por defecto |
|---|---|
| Negada | 1 |
| Grande o chica en paso | 1 |
| Par / medias / duples | 1 / 2 / 3 **por cada jugador** de la pareja ganadora que los tenga |
| Juego 31 / otro juego | 3 / 2 por cada jugador de la pareja ganadora con juego |
| Punto | 1 |
| Envite rechazado tras subidas | La pareja que subió gana el valor de la apuesta vigente antes de su subida |

### 4.3 Fin del juego

- Objetivo por defecto: **40 tantos** (FEM Intro E: entre 40 y 60).
- Como el tanteo final va en orden de lances (FEM VII.2), **gana la primera pareja que llegue
  al objetivo al contar**, aunque la otra fuese a sumar más en un lance posterior.
- Si una negada en el acto lleva a una pareja al objetivo, ¿termina el juego inmediatamente?
  → configurable, por defecto sí (pregunta P8).
- Al faltar ≤ 4 tantos: evento `TeamIsIn` ("estamos dentro", FEM VII.7) y se activa el modo
  "a falta de tanto" (FEM IV.7).
- Partida = N juegos (FEM: "a cinco juegos"); v1 usa `games_to_win = 1` (pregunta P4).

### 4.4 Amarracos

Representación visual: 1 amarraco = 5 tantos; los tantos sueltos se muestran como piedras
(FEM VII.3, VII.7). Es solo presentación (`score // 5`, `score % 5`); el motor trabaja en tantos.
