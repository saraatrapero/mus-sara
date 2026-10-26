# 02 — Arquitectura

> **Nota de implementación.** Tres elecciones de esta tabla cambiaron al implementar: frontend
> en JavaScript sin compilación (ADR-005), `sqlite3` en lugar de SQLAlchemy (ADR-006) y
> `scrypt` en lugar de argon2 (ADR-007). Ver [docs/adr](../adr/index.md).

## 1. Vista general

La arquitectura es **hexagonal**: un núcleo puro (motor de Mus) sin dependencias, rodeado de
adaptadores (bots, servidor web, persistencia, torneo). Las dependencias apuntan siempre
**hacia dentro**: el motor no conoce bots, web ni base de datos.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  FRONTEND (navegador)  — TypeScript, solo recibe Observations           │
│  Mesa · Tutorial · Replay · Estadísticas · Perfil · Bot Arena           │
└───────────────▲─────────────────────────────────┬───────────────────────┘
                │ Observation (JSON)              │ ActionRequest (JSON)
                │ WebSocket / HTTP                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  musst.server — FastAPI                                                 │
│  Auth · Validación Pydantic · GameController · SessionManager           │
└───────────────▲─────────────────────────────────┬───────────────────────┘
                │                                 │
┌───────────────┴─────────────────────────────────▼───────────────────────┐
│  musst.runtime — GameRunner (orquesta asientos humanos/bots, timeouts)  │
│                                                                         │
│   ┌──────────────────────── musst.engine (NÚCLEO PURO) ───────────────┐ │
│   │  GameEngine ──► RulesEngine (legalidad)                           │ │
│   │      │      ──► Scoring (tanteo)                                  │ │
│   │      │      ──► HandEvaluator (grande/chica/pares/juego/punto)    │ │
│   │      ▼                                                            │ │
│   │  GameState (secreto) ──► EventLog ──► ObservationBuilder          │ │
│   └────────────────────────────────────────────────┬──────────────────┘ │
│                                                    │ Observation        │
│   ┌──────────────── musst.bots ────────────────────▼──────────────────┐ │
│   │  Bot API · SandboxRunner (subproceso) · Bots internos             │ │
│   │  musst.agents: Orquestador → Agentes → Juez → Decision            │ │
│   └───────────────────────────────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────────────────────────────────┘
                       │ eventos + resúmenes
┌──────────────────────▼──────────────────────────────────────────────────┐
│ musst.persistence (SQLAlchemy: SQLite → PostgreSQL)                     │
│ musst.learning (PlayerModel, actualización post-partida)                │
│ musst.analytics (estadísticas, momentos clave, simulación contrafactual)│
│ musst.arena (torneo, scoreboard)                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### Flujo de una decisión de bot (ninguna flecha salta el motor)

```
GameEngine ──state──► ObservationBuilder ──Observation(asiento)──► SandboxRunner
                                                                       │
                                     ┌─────────────────────────────────┘
                                     ▼
                              BOT ORCHESTRATOR
                     ┌──────┬──────┼────────┬─────────┐
                     ▼      ▼      ▼        ▼         ▼
                  CARTAS  PROB.  COMPORT. MARCADOR  PAREJA …
                     └──────┴──────┼────────┴─────────┘
                                   ▼
                          ESTRATEGIA (candidatas ⊆ legal_actions)
                                   ▼
                              JUEZ → Decision
                                   │ Action
                                   ▼
                     RulesEngine.validate(state, seat, action)
                         ├─ legal   → GameEngine.apply → eventos
                         └─ ilegal  → rechazo (en torneo: derrota)
```

## 2. Componentes

| Componente | Paquete | Responsabilidad | No hace |
|---|---|---|---|
| Cartas y baraja | `engine.cards` | `Card`, `Suit`, `Rank`, `Deck` con RNG inyectado | — |
| HandEvaluator | `engine.evaluation` | Comparar manos en grande/chica; calcular pares, juego y punto | Decidir |
| RulesEngine | `engine.rules` | `legal_actions(state, seat)`, `validate(...)` | Mutar estado |
| GameEngine | `engine.game` | `apply(state, seat, action) -> (state', events)`; transiciones de la FSM | Elegir acciones |
| Scoring | `engine.scoring` | Tanteo de cada lance y al final de la jugada; fin de juego | — |
| ObservationBuilder | `engine.observation` | Proyecta el estado y los eventos a la vista de un asiento | — |
| EventLog | `engine.events` | Eventos inmutables, públicos o privados | — |
| SignalSystem | `engine.signals` | Señas FEM (desactivado en v1) | — |
| GameRunner | `runtime` | Bucle de partida, asientos, timeouts, abandono, pausa | Reglas |
| Bot API | `bots.api` | Contrato público `Bot`, `Observation`, `Action` | — |
| SandboxRunner | `bots.sandbox` | Ejecuta bots en subproceso con timeout | — |
| Agentes | `agents.*` | IA interna (doc 06) | Validar ni ejecutar |
| PlayerModel | `learning` | Modelo estadístico de los jugadores | — |
| Arena | `arena` | Torneo, clasificación, exportación del scoreboard | — |
| Servidor | `server` | HTTP/WS, auth, sesiones, permisos | Lógica de juego |
| Persistencia | `persistence` | Repositorios, migraciones | — |
| Frontend | `web/` | Renderizar observaciones y enviar intenciones | Validar reglas (solo oculta botones) |

## 3. Decisiones tecnológicas

Cada decisión se documenta como un ADR breve en `docs/adr/`. Resumen:

| Decisión | Elección | Alternativas | Por qué | Limitaciones |
|---|---|---|---|---|
| Lenguaje del núcleo | Python 3.12, solo stdlib | — | Lo exige la práctica; sin dependencias el motor es instalable en cualquier sitio | Rendimiento de Monte Carlo (mitigable) |
| Modelado de estado | `dataclass(frozen=True)` + transiciones puras | Objetos mutables | Replay, tests y simulación triviales; ningún agente puede mutar el estado | Copias (aceptable: estado pequeño) |
| Servidor | **FastAPI** + Uvicorn | Streamlit, Flask, Django | WebSockets, validación Pydantic, OpenAPI automático; el servidor **guarda el secreto** | Requiere hosting con proceso (no Pages) |
| Frontend | **TypeScript + Vite**, sin framework pesado (Preact si crece) | Streamlit, React, Svelte | Control total de la mesa y las animaciones; estático, se sirve en Pages | Más trabajo que Streamlit |
| BD | **SQLAlchemy 2 + Alembic**, SQLite → PostgreSQL | ORM propio, SQL crudo | Migración sin reescribir | — |
| Hash de contraseñas | **argon2id** (`argon2-cffi`) | bcrypt | Recomendado por OWASP | — |
| Configuración | TOML (`tomllib`) + dataclasses validadas | YAML, env | stdlib, tipado | — |
| Docs | **MkDocs Material + mkdocstrings → ReadTheDocs** | Sphinx | Lo recomienda la práctica; referencia del API desde docstrings | — |
| Calidad | pytest, hypothesis, ruff, mypy | — | Estándar | — |

### Por qué NO hacer todo en el navegador (Pyodide / GitHub Pages solo)

Una web estática que ejecuta el motor en el navegador tendría **las cartas de los bots en la
memoria del cliente**: cualquiera las vería con las DevTools. Eso incumple RNF-02 y el
apartado 5.1.1 de la práctica. Por eso **el estado secreto vive en el servidor** y el
navegador solo recibe observaciones.

## 4. Estructura de carpetas

```
mus-sara/
├── README.md  LICENSE  .gitignore  pyproject.toml  CONTRIBUTING.md
├── config/
│   ├── rules.default.toml        # objetivo de tantos, convenciones de tanteo
│   ├── agents.toml               # pesos y umbrales de agentes por nivel
│   └── ui.toml
├── src/musst/
│   ├── __init__.py               # API de alto nivel: play_game(...)
│   ├── engine/
│   │   ├── cards.py  deck.py  evaluation.py
│   │   ├── actions.py            # acciones tipadas
│   │   ├── state.py              # GameState, RoundState, LanceState, BetState
│   │   ├── fsm.py                # fases y transiciones permitidas
│   │   ├── rules.py              # RulesEngine
│   │   ├── game.py               # GameEngine.apply
│   │   ├── scoring.py
│   │   ├── events.py
│   │   ├── observation.py        # ObservationBuilder
│   │   ├── signals.py            # SignalSystem (desactivado)
│   │   └── config.py
│   ├── runtime/  runner.py  seats.py  timeouts.py
│   ├── bots/
│   │   ├── api.py                # ← CONTRATO PÚBLICO
│   │   ├── sandbox.py  registry.py
│   │   └── builtin/  random_bot.py  simple.py  medium.py  pro.py
│   ├── agents/
│   │   ├── base.py  orchestrator.py  judge.py  explanation.py
│   │   ├── cards.py  probability.py  behaviour.py  bluff.py
│   │   ├── score.py  history.py  partner.py  strategy.py  rules_agent.py
│   ├── learning/  player_model.py  memory.py  updater.py  drift.py
│   ├── analytics/  stats.py  key_moments.py  counterfactual.py  calibration.py
│   ├── arena/  tournament.py  scoreboard.py  cli.py
│   ├── persistence/  models.py  repositories.py  migrations/
│   └── server/  app.py  auth.py  routes/  ws.py  schemas.py  dev_mode.py
├── bots/                         # bots externos (uno por carpeta, vía PR)
│   └── example_bot/  bot.py  README.md
├── web/                          # frontend (TypeScript + Vite)
├── experiments/                  # experimentos reproducibles (notebooks + scripts)
├── tests/
│   ├── unit/  integration/  privacy/  property/  bot_conformance/  scenarios/
├── docs/                         # MkDocs
│   ├── index.md  architecture.md  game-rules.md  bot-api.md  agents.md
│   ├── player-model.md  testing.md  deployment.md  adr/  design/
└── .github/
    ├── workflows/  ci.yml  bot-pr.yml  tournament.yml  docs.yml  deploy.yml
    └── PULL_REQUEST_TEMPLATE.md
```

## 5. Flujo Git

- `main`: protegida; solo recibe merges desde `develop` en hitos (punto de control, entrega).
- `develop`: integración; protegida, PR con CI verde y 1 revisión.
- `feature/fase-NN-descripcion`: una por fase o subtarea.
- Bots externos: PR a `develop` desde un fork, solo con cambios en `bots/<nombre>/`.

## 6. Despliegue (gratuito)

| Pieza | Plataforma | Notas |
|---|---|---|
| Frontend estático | GitHub Pages | Recomendado por la práctica |
| API + estado secreto | Render (free web service) **o** Hugging Face Spaces (Docker) | Arranque en frío ~30-60 s en Render; aceptable para la práctica |
| BD | SQLite en disco del servicio → Neon/Supabase PostgreSQL gratuito cuando haga falta persistencia real | En planes gratuitos el disco de Render es efímero |
| Documentación | ReadTheDocs | Req 2.3 |
| Scoreboard | GitHub Pages (JSON + HTML generados por Actions) | Req 4.2 |

**Plan B para Req 1.3 si el backend se retrasa:** una app Streamlit (Streamlit Cloud, también
recomendado por la práctica). Mantiene el estado en el servidor y no rompe la privacidad, con
menos control visual. Al ser solo un adaptador, el motor no cambia.
