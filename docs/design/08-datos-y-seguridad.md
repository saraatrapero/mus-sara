# 08 — Modelo de datos, persistencia, seguridad y logging

## 1. Entidades del dominio

```
User 1───0..1 Player ───* PlayerModel (uno por Player; versiones)
               │
Bot  1───────0..1 Player          (Player = quien ocupa un asiento: humano o bot)
               │
Team *──2 Player   (por partida)
               │
Game 1──2 Team, 1──4 Seat(Player)
Game 1──* Round(jugada) 1──4 Lance 1──* Action
Game 1──* GameEvent
Game *──0..1 Tournament
Player 1──* Statistics(snapshot por periodo)
Agent: configuración dentro de un Bot (no es una tabla de dominio)
Card: objeto de valor (no es una tabla)
```

| Entidad | Descripción |
|---|---|
| `User` | Cuenta humana (login). Datos mínimos. |
| `Player` | Identidad de juego: humano (`user_id`) o bot (`bot_id`). |
| `Bot` | Bot registrado: nombre, versión, autor, nivel, entrypoint. |
| `Team` | Pareja en una partida concreta. |
| `Game` | Partida: config, seed, estado, resultado. |
| `Round` | Jugada: mano, dealer, número. |
| `Lance` | Lance dentro de una jugada: resultado, tantos. |
| `Action` | Decisión de un jugador con su contexto público. |
| `GameEvent` | Evento del log (doc 04). |
| `PlayerModel` | Modelo estadístico serializado (JSON) y versionado. |
| `Statistics` | Agregados por jugador y periodo. |
| `Tournament` | Ejecución del torneo: seed, participantes, clasificación. |

## 2. Esquema relacional (SQLite → PostgreSQL)

```sql
users(id PK, username UNIQUE, password_hash, avatar_path NULL, created_at, settings_json)
bots(id PK, name, version, author, level, entrypoint, active, UNIQUE(name, version))
players(id PK, kind CHECK(kind IN ('human','bot')), user_id FK NULL, bot_id FK NULL, display_name)
games(id PK, mode, status, seed, config_json, target, winner_team NULL,
      created_by FK users NULL, started_at, finished_at, tournament_id FK NULL)
game_seats(game_id FK, seat 0..3, team 0..1, player_id FK, PRIMARY KEY(game_id, seat))
rounds(id PK, game_id FK, round_no, dealer_seat, mano_seat, score_a_after, score_b_after)
actions(id PK, game_id FK, round_id FK, seq, seat, lance, action_json, context_json, outcome_json NULL, ts)
game_events(game_id FK, seq, kind, visibility, recipients, payload_json, ts, PRIMARY KEY(game_id, seq))
player_models(player_id FK, version, model_json, sample_size, updated_at, PRIMARY KEY(player_id, version))
statistics(player_id FK, period, stats_json, PRIMARY KEY(player_id, period))
tournaments(id PK, seed, started_at, finished_at, config_json)
tournament_results(tournament_id FK, bot_id FK, games, wins, losses, points_for, points_against, errors, elo)
achievements(user_id FK, code, earned_at, PRIMARY KEY(user_id, code))
```

- Acceso a través de repositorios (`persistence.repositories`); el dominio no conoce SQLAlchemy.
- Migraciones con Alembic desde el primer día, para que el paso a PostgreSQL sea cambiar la URL.
- `game_events` con visibilidad `PRIVATE` o `SYSTEM` solo se sirven al dueño, al acabar la
  partida, o en modo dev local.

## 3. Seguridad

| Amenaza | Medida |
|---|---|
| Robo de contraseñas | argon2id; nunca texto plano ni en logs; política de longitud mínima |
| Robo de sesión | Cookie `HttpOnly`, `Secure`, `SameSite=Lax`; token de sesión aleatorio (`secrets`) guardado como hash; expiración |
| CSRF | SameSite + token CSRF en formularios que cambian estado |
| Inyección / entrada malformada | Pydantic en todas las entradas; acciones como unión discriminada; ORM con parámetros |
| Acción fuera de turno o ajena | El servidor deriva el asiento de la **sesión**, no del cliente; el `RulesEngine` vuelve a validar |
| Fuga de información | Solo `Observation`; tests de fuga; el modo dev no está en el build de producción |
| Acceso a datos ajenos | Autorización por recurso: `/players/{id}/statistics` solo para el dueño (o perfil público opcional) |
| Abuso | Rate limiting por IP/usuario en login y acciones |
| Bots maliciosos | doc 05 §3 |
| Fotografías | Se procesan para generar el avatar; por defecto **no se guarda el original** (minimización); tamaño y tipo validados |
| Secretos | Variables de entorno; nunca en el repositorio; `.env` en `.gitignore` |

### Endpoints (conceptuales)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| POST | `/auth/register`, `/auth/login`, `/auth/logout` | — | |
| POST | `/games` | opcional | Crear partida (modo, bots, config) |
| GET | `/games/{id}` | asiento o espectador | **Observation** del que llama |
| POST | `/games/{id}/action` | asiento | Enviar una acción (también por WS) |
| WS | `/games/{id}/ws` | asiento | Observaciones en tiempo real |
| GET | `/games/{id}/replay` | participante, partida terminada | Eventos visibles tras el final |
| GET | `/bots`, `/bots/{id}` | — | Catálogo |
| GET | `/players/{id}/statistics` | dueño | Estadísticas |
| GET | `/scoreboard` | — | Clasificación del torneo |

## 4. Logging

- `logging` estándar con logs estructurados (JSON) y niveles DEBUG / INFO / WARNING / ERROR.
- Dos canales: `musst.public` (eventos públicos, operativa) y `musst.secret` (estado completo,
  **desactivado salvo en modo dev local**, nunca en producción ni en artefactos del CI público).
- Un filtro `RedactSecretsFilter` elimina campos `hand`, `deck`, `cards` de cualquier registro
  fuera de `musst.secret`. Un test lo comprueba.
- Logs del torneo: solo resultados y tipo de error del bot, no sus cartas.

## 5. Robustez

| Fallo | Respuesta |
|---|---|
| Bot lanza una excepción / acción ilegal / timeout | `BotFailure` → Fallback (partida con humanos) o derrota (torneo) |
| Acción ilegal de un humano | 422 con el motivo; el estado no cambia |
| Desconexión de un humano | `PAUSED`; el estado se reconstruye desde el log; reconexión con su sesión; tras X min, abandono configurable |
| Error interno | `ERROR`, se guarda la partida y se registra el traceback (sin secretos) |
| Reinicio del servidor | Las partidas en curso se reconstruyen con `seed + acciones` desde la BD |
