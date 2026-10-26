# API de bots — tutorial de principio a fin

Esta guía explica cómo crear un bot de Mus para MUS.ST, probarlo y añadirlo al torneo **sin
tocar el código del juego** (Req 2.1).

## 1. Qué es un bot

Un bot controla **un asiento**. En cada turno recibe una `Observation` con todo lo que ese
asiento puede saber legítimamente, y devuelve una `Action`. El motor vuelve a validar todas las
acciones: si devuelves algo ilegal, en el torneo pierdes la partida.

```python
from musst.bots.api import Bot, Observation, Action


class MiBot(Bot):
    name = "mi_bot"
    author = "Tu nombre"
    version = "1.0"

    def decide(self, observation: Observation) -> Action: ...
```

Métodos opcionales:

| Método | Cuándo | Para qué |
|---|---|---|
| `on_game_start(info: GameStartInfo)` | Al empezar | Asiento, compañero, objetivo, nombres de los jugadores |
| `decide(observation) -> Action` | En cada turno tuyo | **Obligatorio** |
| `on_game_end(info: GameEndInfo)` | Al terminar | Historial público con las manos reveladas: para aprender |

## 2. Qué información recibes

| Campo | Significado |
|---|---|
| `seat`, `partner`, `team` | Tu asiento (0-3), el de tu compañero y tu pareja (0 = {0, 2}, 1 = {1, 3}) |
| `hand` | **Solo tus** 4 cartas (`Card(rank, suit)`; el 3 vale como rey y el 2 como as) |
| `phase` | `mus`, `discard`, `grande`, `chica`, `pares`, `juego`, `punto`, `game_over` |
| `turn`, `mano`, `dealer` | Quién habla, quién es mano y quién reparte |
| `score`, `target` | Marcador `(pareja 0, pareja 1)` y tantos para ganar |
| `declarations` | Pares sí/no y juego sí/no ya declarados: `{"pares": {asiento: bool}}` |
| `current_bet` | Apuesta pendiente: lance, pareja que envida, cantidad, si es órdago, quién responde |
| `legal_actions` | Lista de `ActionSpec` con las familias de acciones legales y sus rangos |
| `history` | Eventos **públicos** de la partida, más los privados dirigidos a ti |
| `revealed_hands` | Manos de todos, solo cuando ya se han enseñado (fin de jugada u órdago) |

Nunca recibirás las cartas de otros jugadores antes de tiempo, ni el mazo, ni el estado interno
de otros bots.

## 3. Qué acciones puedes devolver

| Acción | Cuándo es legal |
|---|---|
| `MusAction()` / `CutMusAction()` | Fase de mus |
| `DiscardAction((carta, ...))` | Descarte: de 1 a 4 cartas **de tu mano** |
| `PassAction()` | Lance abierto |
| `BetAction(n)` | Lance abierto, `n` entre `min` y `max` del `ActionSpec` |
| `RaiseAction(n)` | Responder a un envite subiendo `n` |
| `AcceptAction()` / `RejectAction()` | Responder a un envite u órdago |
| `AcceptNoLoseAction()` | "Quiero y no pierdo" (postre con 33 ante un órdago a juego, FEM VI.9) |
| `OrdagoAction()` | Lance abierto o como respuesta a un envite |

Truco: `observation.legal_types()` devuelve el conjunto de tipos legales, y
`spec.default()` construye una acción válida de esa familia.

## 4. Tu primer bot

```python
# bots/mi_bot/bot.py
from musst.bots.api import (
    AcceptAction,
    Action,
    BetAction,
    Bot,
    CutMusAction,
    DiscardAction,
    MusAction,
    Observation,
    PassAction,
    RejectAction,
)
from musst.bots.toolkit import hand_strength


class MiBot(Bot):
    name = "mi_bot"
    author = "Tu nombre"

    def decide(self, observation: Observation) -> Action:
        legal = observation.legal_types()
        if "cut" in legal:
            return (
                CutMusAction()
                if "mus" not in legal or hand_strength(observation.hand, "grande") > 0.6
                else MusAction()
            )
        if "discard" in legal:
            return DiscardAction((min(observation.hand, key=lambda c: c.rank),))
        strength = hand_strength(observation.hand, observation.phase)
        if "pass" in legal:
            return BetAction(2) if strength > 0.75 else PassAction()
        if "accept" in legal and strength > 0.6:
            return AcceptAction()
        return RejectAction()
```

```toml
# bots/mi_bot/bot.toml
name = "mi_bot"
author = "Tu nombre"
version = "1.0"
entrypoint = "bot:MiBot"
description = "Envida con mano fuerte."
```

Añade también `bots/mi_bot/README.md` con la estrategia en 5-10 líneas.

### Herramientas disponibles (`musst.bots.toolkit`)

| Función | Qué hace |
|---|---|
| `hand_strength(hand, lance)` | Fuerza heurística en [0, 1] |
| `unseen_cards(obs)` | Cartas que pueden estar en otras manos |
| `sample_world(obs, rng)` | Reparte las cartas no vistas de forma compatible con las declaraciones |
| `estimate_lance_win(obs, lance, rng, samples)` | P(tu pareja gana el lance) por Monte Carlo |
| `keep_heuristic_discard(hand)` | Descarte clásico (guardar reyes y parejas) |

## 5. Cómo ejecutarlo y probarlo

```bash
pip install -e ".[dev]"

# Una partida contra el bot sencillo
python -c "
from musst import play_game
from musst.bots.registry import external_entries
from musst.bots.builtin import SimpleBot
mine = next(e for e in external_entries() if e.name == 'mi_bot')
print(play_game([mine.factory(), SimpleBot(1), mine.factory(), SimpleBot(2)], seed=1).result)
"

# Tests de conformidad (los mismos que se ejecutan en tu PR)
pytest tests/bot_conformance -k mi_bot

# Mini-torneo
musst-arena --games 5 --only mi_bot sencillo medio
```

Los tests de conformidad comprueban que el bot:

1. se instancia y tiene metadatos válidos;
2. juega partidas completas contra `RandomBot` y `SimpleBot` sin acciones ilegales;
3. responde en menos de 2 s en el percentil 99.

## 6. Cómo añadirlo al torneo

1. Haz un fork del repositorio y crea la rama `bot/mi_bot`.
2. Añade **solo** la carpeta `bots/mi_bot/`.
3. Abre un Pull Request a `develop`. El workflow `bot-pr.yml` hace un análisis estático,
   ejecuta los tests de conformidad y un mini-torneo, y publica el resultado en el PR.
4. Tras la revisión y el merge, tu bot entra en el torneo automático y en el
   [scoreboard](https://saraatrapero.github.io/mus-sara/scoreboard/).

## 7. Sandbox: cómo se ejecuta tu bot

En el torneo, tu bot se ejecuta en **otro proceso** (`musst.bots.sandbox`): recibe la
observación en JSON por la entrada estándar y responde con la acción por la salida estándar.

| Regla | Consecuencia si se incumple |
|---|---|
| Responder en ≤ 2 s por decisión | Timeout → pierdes la partida |
| Devolver una acción legal | Acción ilegal → pierdes la partida |
| No lanzar excepciones | Excepción → pierdes la partida |
| No usar `os`, `subprocess`, `socket`, `eval`, `exec`, `open` | El PR no pasa la validación |

Tus `print()` no rompen el protocolo (se descartan). El proceso arranca en un directorio
temporal vacío, sin variables de entorno del servidor y con límites de CPU, memoria y ficheros.

> **Límite honesto:** Python no permite un sandbox perfecto dentro del lenguaje. La protección
> combina proceso separado, límites del sistema, revisión del PR y un CI sin secretos. Ver
> [docs/architecture.md](architecture.md#seguridad).
