# MUS.ST

> *El Mus que aprende cómo juegas.*

Plataforma de Mus según el **Reglamento de la Federación Española de Mus**: un motor de reglas
fiable, bots inteligentes y adaptativos, modelos de jugador, estadísticas, entrenamiento y un
torneo automático de bots.

Práctica de **Inteligencia Artificial — 3º MAT-A, CUNEF Universidad, 2026/2027**.

**Jugar online:** https://saraatrapero.github.io/mus-sara/ (Python ejecutándose en tu navegador con Pyodide)

[![CI](https://github.com/saraatrapero/mus-sara/actions/workflows/ci.yml/badge.svg)](https://github.com/saraatrapero/mus-sara/actions/workflows/ci.yml)

| Jugar | Aprender | Competir | Analizar |
|---|---|---|---|
| Partida rápida, personalizada, contra un bot concreto, con compañero humano por invitación | Tutorial interactivo, aprender jugando, situaciones de entrenamiento, asistente «¿qué puedo hacer?» | Bot Arena, torneo automático, scoreboard, observar Bot vs Bot | Historial, replay ⏮ ◀ ▶ ⏭, estadísticas, estilo de juego, momentos clave |

## Empezar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                                   # 156 tests
musst-play --bots sencillo profesional   # una partida sin interfaz
musst-arena --games 5                    # torneo entre todos los bots
MUSST_SECURE_COOKIES=0 uvicorn musst.server.app:app --reload   # web con servidor: http://localhost:8000
python scripts/build_web.py --out site && python -m http.server -d site 8001   # web sin servidor (Pyodide)
```

Partida completa desde código (Req 1.1):

```python
from musst import play_game
from musst.bots.builtin import SimpleBot, ProBot

match = play_game([ProBot(1), SimpleBot(2), ProBot(3), SimpleBot(4)], seed=12345)
print(match.result)
```

## Escribir un bot

```python
from musst.bots.api import Bot, Observation, Action

class MiBot(Bot):
    name = "mi_bot"
    def decide(self, observation: Observation) -> Action:
        return observation.legal_actions[0].default()
```

Tutorial completo, sandbox y cómo entrar en el torneo: **[docs/bot-api.md](docs/bot-api.md)**.

## Estructura

```
src/musst/
  engine/       motor de reglas FEM (solo stdlib): cartas, evaluación, FSM, tanteo, eventos, observaciones
  bots/         API pública de bots, utilidades, sandbox en subproceso, registro, bots internos
  agents/       IA multiagente: orquestador, especialistas, estrategia, juez
  learning/     PlayerModel contextual, memoria, detección de cambios, jugadores sintéticos
  analytics/    estadísticas, momentos clave, contrafactuales post-partida
  arena/        torneo (mus duplicado) y scoreboard
  persistence/  SQLite detrás de un repositorio; contraseñas con scrypt
  server/       casos de uso (service.py) + API FastAPI + frontend estático (HTML/CSS/JS)
  web/          backend que corre en el navegador (Pyodide) para GitHub Pages
bots/           bots externos (uno por carpeta, vía Pull Request)
experiments/    experimentos reproducibles (escalera de niveles, adaptación)
tests/          unit · property · privacy · integration · bot_conformance
docs/           MkDocs (ReadTheDocs) + diseño de la Fase 0 + ADR
config/         reglas y parámetros de agentes
```

## Documentación

| | |
|---|---|
| [Reglas del juego](docs/game-rules.md) | Artículo FEM de cada regla; convenciones marcadas |
| [Arquitectura](docs/architecture.md) | Capas, flujo de decisión, máquina de estados, seguridad |
| [API de bots](docs/bot-api.md) | Tutorial de principio a fin |
| [Agentes](docs/agents.md) | Niveles, agentes, selección adversa, DecisionExplanation |
| [PlayerModel](docs/player-model.md) | Qué aprende, cómo, memoria, cambios de estrategia |
| [Testing y experimentos](docs/testing.md) | Pirámide de tests, privacidad, resultados medidos |
| [Despliegue](docs/deployment.md) | GitHub Pages con Pyodide, local, ReadTheDocs |
| [Decisiones (ADR)](docs/adr/index.md) | Por qué cada decisión, alternativas y limitaciones |
| [Diseño de la Fase 0](docs/design/00-indice.md) | Requisitos, arquitectura y **preguntas para el profesor** |

## Validado por el profesor

- Se permite el **Mus FEM de 4 jugadores en 2 parejas**; no se ha modificado el juego.
- **Dificultad 5** (cada victoria de un bot en la Sección 3 vale 0.5 × 5 = 2.5).
- La web se publica en **GitHub Pages** con Python en el navegador (Pyodide).

El resto de preguntas abiertas están en [preguntas al profesor](docs/design/11-preguntas-profesor.md).

## Flujo de trabajo

`main` (protegida) ← `develop` (protegida) ← `feature/*`, siempre mediante Pull Request con
CI verde. Ver [CONTRIBUTING.md](CONTRIBUTING.md).

Licencia [MIT](LICENSE).
