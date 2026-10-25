# 04 — Eventos y observaciones

## 1. Event sourcing

Cada `GameEngine.apply` devuelve una lista de **eventos inmutables**. Una partida es su
`seed` + la secuencia de acciones; los eventos son su historia legible. Con ellos se obtiene:

- **Replay**: reproducir los eventos visibles para un espectador.
- **Reconstrucción**: `replay(seed, actions)` debe dar exactamente el mismo log (se comprueba en un test).
- **Estadísticas y aprendizaje**: se calculan a partir de eventos, nunca del estado interno.
- **Recuperación**: una partida interrumpida se reconstruye a partir de su log (RF-U13).

### 1.1 Estructura

```python
@dataclass(frozen=True)
class GameEvent:
    game_id: UUID
    seq: int  # orden total dentro de la partida
    timestamp: datetime
    round_no: int
    phase: Phase  # lance / fase en la que ocurre
    actor: Seat | None  # None para eventos del sistema
    kind: EventKind
    payload: Mapping[str, Any]
    visibility: Visibility  # PUBLIC | PRIVATE(seats) | SYSTEM
```

| Visibilidad | Quién lo ve | Ejemplos |
|---|---|---|
| `PUBLIC` | Todos, también espectadores | `MusRequested`, `BetPlaced`, `PointsAwarded`, `HandsRevealed` |
| `PRIVATE(seats)` | Solo los asientos indicados | `CardsDealt` (al receptor), `CardsDiscarded` con cartas (al jugador), `SignalSent` (al compañero) |
| `SYSTEM` | Solo motor y modo dev | `DeckShuffled` (orden del mazo), `RngSeeded` |

Un mismo hecho puede generar **dos eventos**: `CardsDiscarded{seat, count: 3}` (público) y
`CardsDiscarded{seat, cards: [...]}` (privado).

### 1.2 Catálogo

| Evento | Visibilidad | Payload |
|---|---|---|
| `GameStarted` | PUBLIC | config pública, asientos, parejas, objetivo |
| `DealerAssigned` | PUBLIC | dealer, mano |
| `DeckShuffled` | SYSTEM | orden del mazo |
| `CardsDealt` | PRIVATE(seat) | cartas |
| `CardsDealtPublic` | PUBLIC | seat, número de cartas |
| `MusRequested` | PUBLIC | seat |
| `MusCut` | PUBLIC | seat |
| `CardsDiscarded` | PUBLIC (cantidad) + PRIVATE (cartas) | |
| `DeckReshuffled` | PUBLIC | (descarte rebarajado, FEM III.15) |
| `LanceStarted` | PUBLIC | lance, mano del lance, participantes |
| `PairsDeclared` / `GameDeclared` | PUBLIC | seat, sí/no |
| `Passed` | PUBLIC | seat |
| `BetPlaced` / `BetRaised` | PUBLIC | seat, cantidad, total |
| `OrdagoDeclared` | PUBLIC | seat, lance |
| `BetAccepted` / `BetRejected` | PUBLIC | seat, ¿definitivo? |
| `OrdagoAccepted` | PUBLIC | |
| `LanceResolved` | PUBLIC (al final de la jugada) | ganador, motivo |
| `HandsRevealed` | PUBLIC | las 4 manos (FEM VII.9) |
| `PointsAwarded` | PUBLIC | pareja, tantos, concepto (negada, deje, envite, paso, pares, juego, punto) |
| `TeamIsIn` | PUBLIC | pareja ("estamos dentro") |
| `RoundFinished` | PUBLIC | marcador |
| `GameFinished` | PUBLIC | ganador, marcador, motivo (tantos, órdago, abandono, error) |
| `IllegalActionAttempted` | SYSTEM + PRIVATE(actor) | acción, motivo |
| `PlayerTimedOut` / `PlayerDisconnected` | PUBLIC | seat |

## 2. ObservationBuilder — la frontera de la información

```
GameState (secreto) + EventLog
            │
            ▼
   ObservationBuilder.for_seat(seat)  ── único punto de proyección
            │
            ▼
   Observation (inmutable, serializable, sin referencias al estado)
            │
     ┌──────┴───────┐
     ▼              ▼
  Humano (JSON)   Bot (JSON por stdin al subproceso)
```

Nunca existe el camino `FRONTEND → GameState`. El servidor web no serializa jamás un `GameState`.

### 2.1 Contenido de `Observation`

```python
@dataclass(frozen=True)
class Observation:
    game_id: str
    me: Seat
    partner: Seat
    my_team: TeamId
    my_hand: tuple[Card, ...]  # SOLO mis cartas
    phase: Phase
    current_lance: Lance | None
    lance_hand: Seat | None  # mano del lance
    dealer: Seat
    turn: Seat | None
    score: dict[TeamId, int]
    target: int
    declarations: dict[Lance, dict[Seat, bool]]
    current_bet: BetView | None  # apuesta vigente y quién debe responder
    lance_history: tuple[PublicAction, ...]  # acciones públicas de esta jugada
    public_events: tuple[PublicEventView, ...]  # historial público de la partida
    revealed_hands: dict[Seat, tuple[Card, ...]] | None  # solo tras SHOWDOWN / órdago
    cards_in_deck: int  # número público (no las cartas)
    legal_actions: tuple[ActionTemplate, ...]
    time_limit_ms: int
```

**Nunca contiene**: manos ajenas antes del showdown, el mazo, el descarte ajeno, el estado del
RNG, eventos `SYSTEM`, modelos de jugador de otros, ni el estado de los agentes.

### 2.2 Garantías

1. **Lista blanca**: el builder copia campos concretos, no filtra un objeto completo. Un campo
   nuevo en `GameState` no se filtra por accidente.
2. **Copia profunda inmutable**: la observación no comparte referencias con el estado.
3. **Tests de fuga** (doc 10 §3): se juegan miles de partidas aleatorias y se comprueba que el
   JSON de cada observación no contiene ninguna carta ajena antes del showdown.
4. El modo espectador usa `for_spectator()`, que solo ve eventos `PUBLIC`.
5. El modo dev usa `for_developer()`, disponible solo con `MUSST_DEV_MODE=1` en local y sin
   ruta en el servidor de producción.

## 3. GameHistory

Cada entrada (`actions` en BD) guarda: timestamp, jugador, acción, lance, **contexto público**
del momento (marcador, posición, apuesta vigente, ronda) y resultado (se rellena al resolver).
Las cartas de un jugador se guardan **en la fila de su propia partida**, cifradas a nivel de
partida, y solo se usan en:

- el replay de partidas terminadas (las cartas son públicas tras el showdown, FEM VII.9), y
- el análisis contrafactual post-partida.

**Excepción importante.** Si se corta el mus, todas las cartas se acaban enseñando. Pero en un
**órdago rechazado** o cuando todo se queda en paso, ¿se enseñan? FEM VII.9 dice que los cuatro
enseñan siempre al terminar juego/punto, y un órdago rechazado no termina la jugada. Por tanto
en v1 todas las manos acaban siendo públicas al final de cada jugada. Las cartas descartadas en
el mus, en cambio, **nunca** se hacen públicas.
