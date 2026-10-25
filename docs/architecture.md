# Arquitectura

El diseño completo está en [design/02-arquitectura.md](design/02-arquitectura.md). Esta página
describe lo **implementado** y dónde está cada pieza.

## Capas

```
            NAVEGADOR (src/musst/server/static: HTML + CSS + JS sin dependencias)
                 │  Observation (JSON)          ▲  Action (JSON) + X-Seat-Token
                 ▼                              │
            SERVIDOR (src/musst/server: FastAPI)    o    NAVEGADOR (src/musst/web: Pyodide en un Web Worker)
            auth · Pydantic · modo dev (solo local)      perfil local · SQLite sobre IndexedDB
                 └──────────────── MusService (server/service.py): casos de uso comunes ──┘
                                   SessionManager · coach
                 │
                 ▼
            RUNTIME (src/musst/runtime/runner.py)  ── torneo (src/musst/arena)
                 │
   ┌─────────────┴──────────────── MOTOR (src/musst/engine, solo stdlib) ─────────────┐
   │ cards · evaluation · actions · config · game (FSM + reglas + tanteo) · events     │
   │ observation (ÚNICA puerta al exterior) · rules (fachada pura) · signals           │
   └─────────────────────────────────────┬─────────────────────────────────────────────┘
                                         │ Observation
            BOTS (src/musst/bots): api · toolkit · sandbox (subproceso) · registry
                                         │
            AGENTES (src/musst/agents): Orquestador → especialistas → Estrategia → Juez
                                         │
            APRENDIZAJE (src/musst/learning): PlayerModel · extracción · Learner · deriva
            ANÁLISIS (src/musst/analytics) · PERSISTENCIA (src/musst/persistence)
```

Las dependencias apuntan hacia dentro: el motor no importa nada de bots, agentes, servidor ni
base de datos.

## Flujo de una decisión

```
MusGame ──► build_observation(seat) ──► Bot.decide(obs)
                                             │ (AgentBot)
                         Orquestador: ¿qué agentes?, ¿análisis profundo?
                    cartas · comportamiento · probabilidad · farol · marcador · pareja
                                             ▼
                         Estrategia: candidatas legales con su valor esperado
                                             ▼
                         Juez: argmax EV − λ·riesgo·(1 − confianza) → Decision
                                             │ Action
MusGame.validate(seat, action) ◄─────────────┘
   ├── legal   → apply → eventos
   └── ilegal  → IllegalAction (torneo: derrota; partida con humanos: FallbackBot)
```

## Máquina de estados

`musst/engine/game.py` define `ALLOWED_TRANSITIONS`. Cualquier transición que no esté en la
tabla lanza `IllegalTransition`.

```
MUS ⇄ DISCARD
MUS → GRANDE → CHICA → PARES → (JUEGO | PUNTO) → [tanteo] → MUS (siguiente jugada)
cualquier lance → GAME_OVER (órdago aceptado o se alcanza el objetivo)
```

Estados de la partida en el servidor: `PLAYING`, `PAUSED` (recuperada tras un reinicio, a la
espera del jugador), `FINISHED`. Los errores de un bot nunca cambian el estado: se sustituye por
`FallbackBot`.

## Event sourcing

Toda partida es `seed` + acciones. Los eventos (`engine/events.py`) tienen visibilidad
`public`, `private` (solo sus destinatarios) o `system` (orden del mazo; solo motor y modo dev).
El servidor guarda las acciones de cada partida en curso y la **reconstruye** tras un reinicio
(`SessionManager._recover`).

## Seguridad

| Amenaza | Medida (código) |
|---|---|
| Fuga de cartas | `build_observation` por lista blanca; `tests/privacy` |
| Cliente tramposo | El asiento sale del token de asiento; `MusGame.validate` revalida todo |
| Contraseñas | `hashlib.scrypt` con sal (`persistence/db.py`); nunca en claro |
| Sesiones | token aleatorio en cookie `HttpOnly` + `SameSite=Lax` (+ `Secure` en producción); en BD solo su hash SHA-256 |
| Fuerza bruta | `RateLimiter` en login y acciones |
| Entradas | Pydantic + `action_from_dict` |
| Datos de otros usuarios | estadísticas y replay solo del propio usuario |
| Bots externos | subproceso, entorno vacío, límites de recursos, timeout, revisión de PR, análisis estático |
| Modo desarrollo | la ruta `/api/dev/*` solo existe con `MUSST_DEV_MODE=1` |
| Logs | los logs del runner y del servidor no incluyen cartas |

## Decisiones

Ver [ADR](adr/index.md).
