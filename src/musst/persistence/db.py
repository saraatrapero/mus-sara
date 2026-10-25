"""Persistencia con SQLite (biblioteca estándar) detrás de un repositorio.

El dominio no conoce SQL: todo pasa por :class:`Repository`. Migrar a PostgreSQL consiste en
implementar la misma interfaz con otro driver (ver docs/deployment.md).

Contraseñas: ``hashlib.scrypt`` (función de derivación resistente a fuerza bruta, de la
biblioteca estándar) con sal aleatoria por usuario. Nunca se guarda la contraseña.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    avatar TEXT,
    settings_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    seed INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    seats_json TEXT NOT NULL,
    actions_json TEXT NOT NULL DEFAULT '[]',
    history_json TEXT,
    winner_team INTEGER,
    score_json TEXT,
    created_by INTEGER REFERENCES users(id),
    started_at REAL NOT NULL,
    finished_at REAL
);
CREATE TABLE IF NOT EXISTS game_players (
    game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    seat INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    PRIMARY KEY (game_id, seat)
);
CREATE TABLE IF NOT EXISTS player_models (
    player_id TEXT PRIMARY KEY,
    model_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS statistics (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    won INTEGER NOT NULL,
    stats_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (user_id, game_id)
);
CREATE TABLE IF NOT EXISTS achievements (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    earned_at REAL NOT NULL,
    PRIMARY KEY (user_id, code)
);
"""

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SESSION_TTL_S = 7 * 24 * 3600


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    digest = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=SCRYPT_R, p=SCRYPT_P
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class User:
    id: int
    username: str
    avatar: str | None
    settings: dict[str, Any]


class Repository:
    """Acceso a datos. Una conexión por hilo; seguro para el servidor de desarrollo."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._local = threading.local()
        self._lock = threading.Lock()
        self._shared: sqlite3.Connection | None = None
        if self.path == ":memory:":
            self._shared = sqlite3.connect(":memory:", check_same_thread=False)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        if self._shared is not None:
            with self._lock:
                yield self._shared
                self._shared.commit()
            return
        connection = getattr(self._local, "conn", None)
        if connection is None:
            connection = sqlite3.connect(self.path)
            connection.execute("PRAGMA foreign_keys = ON")
            self._local.conn = connection
        yield connection
        connection.commit()

    # ------------------------------------------------------------------ usuarios
    def create_user(self, username: str, password: str, avatar: str | None = None) -> User:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO users (username, password_hash, avatar, created_at) VALUES (?, ?, ?, ?)",
                (username, hash_password(password), avatar, time.time()),
            )
            assert cur.lastrowid is not None
            return User(cur.lastrowid, username, avatar, {})

    def get_or_create_local_user(self, username: str) -> User:
        """Perfil sin contraseña para la versión que se ejecuta en el navegador.

        El hash ``!local`` no corresponde a ninguna contraseña, así que este usuario nunca
        puede iniciar sesión en un servidor.
        """
        with self.conn() as c:
            row = c.execute(
                "SELECT id, username, avatar, settings_json FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if row is not None:
                return User(row[0], row[1], row[2], json.loads(row[3]))
            cur = c.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, '!local', ?)",
                (username, time.time()),
            )
            assert cur.lastrowid is not None
            return User(cur.lastrowid, username, None, {})

    def authenticate(self, username: str, password: str) -> User | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT id, username, password_hash, avatar, settings_json FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            hash_password(password)  # tiempo constante aproximado ante usuarios inexistentes
            return None
        if not verify_password(password, row[2]):
            return None
        return User(row[0], row[1], row[3], json.loads(row[4]))

    def get_user(self, user_id: int) -> User | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT id, username, avatar, settings_json FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return User(row[0], row[1], row[2], json.loads(row[3])) if row else None

    def update_user(self, user_id: int, avatar: str | None, settings: dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                "UPDATE users SET avatar = ?, settings_json = ? WHERE id = ?",
                (avatar, json.dumps(settings), user_id),
            )

    # ------------------------------------------------------------------ sesiones
    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        with self.conn() as c:
            c.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (_token_hash(token), user_id, time.time() + SESSION_TTL_S),
            )
        return token

    def session_user(self, token: str | None) -> User | None:
        if not token:
            return None
        with self.conn() as c:
            row = c.execute(
                "SELECT user_id, expires_at FROM sessions WHERE token_hash = ?",
                (_token_hash(token),),
            ).fetchone()
        if row is None or row[1] < time.time():
            return None
        return self.get_user(row[0])

    def delete_session(self, token: str) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))

    # ------------------------------------------------------------------ partidas
    def save_game(
        self,
        game_id: str,
        mode: str,
        status: str,
        seed: int,
        config: dict[str, Any],
        seats: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        created_by: int | None,
        history: list[dict[str, Any]] | None = None,
        winner: int | None = None,
        score: tuple[int, int] | None = None,
    ) -> None:
        now = time.time()
        with self.conn() as c:
            c.execute(
                """INSERT INTO games (id, mode, status, seed, config_json, seats_json, actions_json,
                       history_json, winner_team, score_json, created_by, started_at, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                       actions_json=excluded.actions_json, history_json=excluded.history_json,
                       winner_team=excluded.winner_team, score_json=excluded.score_json,
                       finished_at=excluded.finished_at""",
                (
                    game_id,
                    mode,
                    status,
                    seed,
                    json.dumps(config),
                    json.dumps(seats),
                    json.dumps(actions),
                    json.dumps(history) if history is not None else None,
                    winner,
                    json.dumps(score) if score else None,
                    created_by,
                    now,
                    now if status == "FINISHED" else None,
                ),
            )
            for seat in seats:
                c.execute(
                    "INSERT OR IGNORE INTO game_players (game_id, seat, player_id, user_id) VALUES (?, ?, ?, ?)",
                    (game_id, seat["seat"], seat["player_id"], seat.get("user_id")),
                )

    def load_game(self, game_id: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute(
                """SELECT id, mode, status, seed, config_json, seats_json, actions_json, history_json,
                          winner_team, score_json, created_by, started_at, finished_at
                   FROM games WHERE id = ?""",
                (game_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "mode": row[1],
            "status": row[2],
            "seed": row[3],
            "config": json.loads(row[4]),
            "seats": json.loads(row[5]),
            "actions": json.loads(row[6]),
            "history": json.loads(row[7]) if row[7] else None,
            "winner": row[8],
            "score": json.loads(row[9]) if row[9] else None,
            "created_by": row[10],
            "started_at": row[11],
            "finished_at": row[12],
        }

    def unfinished_games(self) -> list[str]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT id FROM games WHERE status IN ('PLAYING', 'PAUSED')"
            ).fetchall()
        return [r[0] for r in rows]

    def user_games(self, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        with self.conn() as c:
            rows = c.execute(
                """SELECT g.id, g.mode, g.status, g.winner_team, g.score_json, g.started_at, gp.seat
                   FROM games g JOIN game_players gp ON gp.game_id = g.id
                   WHERE gp.user_id = ? ORDER BY g.started_at DESC LIMIT ?""",
                (user_id, limit),
            ).fetchall()
        return [
            {
                "id": r[0],
                "mode": r[1],
                "status": r[2],
                "won": None if r[3] is None else r[3] == r[6] % 2,
                "score": json.loads(r[4]) if r[4] else None,
                "started_at": r[5],
                "seat": r[6],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------ modelos
    def load_model(self, player_id: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT model_json FROM player_models WHERE player_id = ?", (player_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_model(self, player_id: str, model: dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                """INSERT INTO player_models (player_id, model_json, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(player_id) DO UPDATE SET model_json=excluded.model_json,
                   updated_at=excluded.updated_at""",
                (player_id, json.dumps(model), time.time()),
            )

    # ------------------------------------------------------------------ estadísticas
    def add_statistics(self, user_id: int, game_id: str, won: bool, stats: dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO statistics (user_id, game_id, won, stats_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, game_id, int(won), json.dumps(stats), time.time()),
            )

    def user_statistics(self, user_id: int) -> list[dict[str, Any]]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT game_id, won, stats_json, created_at FROM statistics WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
        return [
            {"game_id": r[0], "won": bool(r[1]), "stats": json.loads(r[2]), "at": r[3]}
            for r in rows
        ]

    def grant_achievement(self, user_id: int, code: str) -> bool:
        with self.conn() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO achievements (user_id, code, earned_at) VALUES (?, ?, ?)",
                (user_id, code, time.time()),
            )
            return cur.rowcount > 0

    def achievements(self, user_id: int) -> list[str]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT code FROM achievements WHERE user_id = ? ORDER BY earned_at", (user_id,)
            ).fetchall()
        return [r[0] for r in rows]


class RepositoryModelStore:
    """Adaptador ``ModelStore`` (learning) sobre el repositorio."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def load(self, player_id: str):  # type: ignore[no-untyped-def]
        from musst.learning.player_model import PlayerModel

        data = self.repo.load_model(player_id)
        return PlayerModel.from_dict(data) if data else None

    def save(self, model) -> None:  # type: ignore[no-untyped-def]
        self.repo.save_model(model.player_id, model.to_dict())
