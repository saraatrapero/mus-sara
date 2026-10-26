"""Backend que se ejecuta **dentro del navegador** (Pyodide, en un Web Worker).

Sustituye al servidor FastAPI en GitHub Pages: el frontend hace las mismas peticiones
(``/api/...``) y el worker las pasa a :func:`handle`, que las resuelve con
:class:`musst.server.service.MusService`. Motor, bots, agentes y aprendizaje son exactamente
los mismos que en el servidor.

Diferencias con el servidor (y por qué):

* **Cuentas en el navegador**: usuario y contraseña (hash scrypt, el mismo que el servidor) y
  un administrador (la primera cuenta que se registra). Los datos (cuentas, partidas,
  estadísticas, lo que el bot aprende de cada jugador) se guardan en SQLite dentro del
  navegador (IndexedDB) y no salen de él: cada navegador tiene sus propias cuentas. Sirve para
  que varias personas usen el mismo equipo (p. ej. en clase) sin mezclar sus datos, **no** como
  seguridad frente a quien controla ese equipo (ver ADR-015).
* **Sin compañero humano por invitación**: necesita un servidor que comparta la partida.
* **Sin bots externos en subproceso**: el navegador no puede lanzar procesos. El torneo con
  todos los bots se ejecuta en GitHub Actions y aquí se muestra su scoreboard.

La separación de información se mantiene: el frontend sigue recibiendo solo la observación de
su asiento. Como todo se ejecuta en el equipo del jugador, esto evita mostrar las cartas por
error, pero no impide que alguien con conocimientos las lea en la memoria del navegador.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from musst.persistence.db import Repository, User
from musst.server.service import ApiError, MusService, check_credentials

DATA_DIR = Path("/data")  # montado sobre IndexedDB por el worker
USERNAME = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")


class LocalBackend:
    def __init__(self, data_dir: Path | None = DATA_DIR) -> None:
        if data_dir is not None and data_dir.is_dir():
            self.repo = Repository(data_dir / "musst.sqlite3")
            self.profile_file: Path | None = data_dir / "perfil.txt"
        else:
            self.repo = Repository(":memory:")
            self.profile_file = None
        self.service = MusService(self.repo, human_partner=False, external_bots=False)
        self.user: User | None = self._load_profile()

    # ------------------------------------------------------------------ perfil local
    def _load_profile(self) -> User | None:
        if self.profile_file is None or not self.profile_file.exists():
            return None
        raw = self.profile_file.read_text().strip()
        return self.repo.get_user(int(raw)) if raw.isdigit() else None

    def _set_profile(self, user: User | None) -> None:
        self.user = user
        if self.profile_file is not None:
            self.profile_file.write_text(str(user.id) if user else "")

    def _local_login(self, username: str) -> dict[str, Any]:
        """Perfil sin contraseña: solo lo usa la sincronización con Supabase (la contraseña la
        comprueba Supabase)."""
        if not USERNAME.match(username or ""):
            raise ApiError(422, "Nombre: de 3 a 32 letras, números, punto, guion o guion bajo")
        user = self.repo.get_or_create_local_user(username)
        self._set_profile(user)
        return {"id": user.id, "username": user.username}

    def _register(self, username: str, password: str) -> dict[str, Any]:
        check_credentials(username, password)
        existing = self.repo.user_by_name(username)
        if existing is not None and existing[1]:
            raise ApiError(409, "Ese nombre de usuario ya existe")
        if existing is not None:  # perfil local antiguo sin contraseña: se le pone una
            user = existing[0]
            self.repo.set_password(user.id, password)
        else:
            user = self.repo.create_user(username, password)
        if self.repo.count_admins() == 0:
            self.repo.set_role(user.id, "admin")  # la primera cuenta administra este navegador
        self.repo.touch(user.id)
        user = self.repo.get_user(user.id) or user
        self._set_profile(user)
        return {"id": user.id, "username": user.username, "role": user.role}

    def _login(self, username: str, password: str) -> dict[str, Any]:
        user = self.repo.authenticate(username, password)
        if user is None:
            raise ApiError(401, "Usuario o contraseña incorrectos")
        self._set_profile(user)
        return {"id": user.id, "username": user.username, "role": user.role}

    def _fresh_user(self) -> User | None:
        """El usuario actual leído de la base (por si un administrador le cambió el rol)."""
        if self.user is not None:
            self.user = self.repo.get_user(self.user.id)
        return self.user

    def _require_user(self) -> User:
        if self.user is None:
            raise ApiError(401, "Crea tu perfil para guardar partidas y estadísticas")
        return self.user

    def _adopt(self, game_id: str, token: str | None) -> None:
        """Tras recargar la página la partida se reconstruye sin tokens: este navegador es su
        único jugador, así que el asiento humano recupera el token que guardó el frontend."""
        session = self.service.manager.get(game_id)
        if session is None or not token or session.seat_for_token(token) is not None:
            return
        # Las personas del mismo dispositivo llevan el asiento en el token ("2.xxxx").
        index = int(token[0]) if len(token) > 2 and token[1] == "." and token[0] in "123" else 0
        seat = session.seats[index]
        if seat.kind == "human" and seat.token is None:
            seat.token = token

    # ------------------------------------------------------------------ nube (Supabase)
    def _cloud_import(self, body: dict[str, Any]) -> dict[str, Any]:
        """Al iniciar sesión: lo que la IA sabía del jugador y la autocrítica de los bots.

        Se queda con la versión que tenga más partidas (la nube o este navegador)."""
        user = self._require_user()
        imported = []
        cloud_model = body.get("model")
        if isinstance(cloud_model, dict):
            pid = f"user:{user.id}"
            local = self.repo.load_model(pid)
            if local is None or cloud_model.get("games", 0) >= local.get("games", 0):
                self.repo.save_model(pid, {**cloud_model, "player_id": pid})
                imported.append("modelo del jugador")
        for key, data in (body.get("bot_memory") or {}).items():
            if not (isinstance(data, dict) and re.fullmatch(r"self:[a-z]+", key)):
                continue
            local = self.repo.load_model(key) or {"player_id": key, "games": 0, "rates": {}}
            mine = (local.get("extra") or {}).get("self_review") or {}
            if data.get("games", 0) >= mine.get("games", 0):
                local.setdefault("extra", {})["self_review"] = data
                self.repo.save_model(key, local)
                imported.append(f"autocrítica {key}")
        return {"imported": imported}

    def _cloud_export(self, game_id: str) -> dict[str, Any]:
        """Al terminar una partida: resumen, modelo del jugador y autocrítica para la nube."""
        from musst.analytics.analysis import seat_statistics

        user = self._require_user()
        data = self.repo.load_game(game_id)
        if data is None or data["status"] != "FINISHED":
            raise ApiError(404, "Partida no terminada")
        seat = next((s for s in data["seats"] if s.get("user_id") == user.id), None)
        if seat is None:
            raise ApiError(403, "No jugabas en esta partida")
        team = seat["seat"] % 2
        levels = {s["seat"]: s.get("level") for s in data["seats"]}
        model = self.service.manager.learner.long_model(f"user:{user.id}")
        memory = {}
        for level in ("profesional",):
            raw = self.repo.load_model(f"self:{level}")
            if raw and (raw.get("extra") or {}).get("self_review"):
                memory[f"self:{level}"] = raw["extra"]["self_review"]
        return {
            "game": {
                "id": game_id,
                "mode": data["mode"],
                "rivals": levels.get((seat["seat"] + 1) % 4),
                "partner": levels.get((seat["seat"] + 2) % 4) or "humano",
                "won": data["winner"] == team,
                "score": [data["score"][team], data["score"][1 - team]],
                "reason": (data["history"] or [{}])[-1].get("payload", {}).get("reason"),
                "stats": seat_statistics(data["history"] or [], seat["seat"]),
                "history": data["history"],
            },
            "model": model.to_dict(),
            "style": model.style()["label"],
            "bot_memory": memory,
        }

    # ------------------------------------------------------------------ enrutado
    def handle(
        self, method: str, path: str, body: dict[str, Any] | None, token: str | None
    ) -> tuple[int, Any]:
        body = body or {}
        svc = self.service
        try:
            if path == "/api/me":
                if method == "PUT":
                    user = self._require_user()
                    result = svc.update_me(user, body.get("avatar"), body.get("settings") or {})
                    self.user = self.repo.get_user(user.id)
                    return 200, result
                return 200, svc.me(self.user)
            if path == "/api/auth/register":
                return 200, self._register(
                    str(body.get("username", "")), str(body.get("password", ""))
                )
            if path == "/api/auth/login":
                if body.get("cloud"):  # cuenta de Supabase ya autenticada
                    return 200, self._local_login(str(body.get("username", "")))
                return 200, self._login(
                    str(body.get("username", "")), str(body.get("password", ""))
                )
            if path == "/api/admin/overview":
                return 200, svc.admin_overview(self._fresh_user())
            if path == "/api/admin/users" and method == "POST":
                return 200, svc.admin_create_user(self._fresh_user(), body)
            m = re.fullmatch(r"/api/admin/users/(\d+)", path)
            if m and method == "PUT":
                return 200, svc.admin_update_user(self._fresh_user(), int(m.group(1)), body)
            if m and method == "DELETE":
                return 200, svc.admin_delete_user(self._fresh_user(), int(m.group(1)))
            if path == "/api/auth/logout":
                self._set_profile(None)
                return 200, {"ok": True}
            if path == "/api/games" and method == "POST":
                return 200, svc.new_game(self.user, body)
            m = re.fullmatch(r"/api/games/([\w-]+)(?:/(\w+))?", path)
            if m:
                game_id, sub = m.group(1), m.group(2)
                if sub == "reclaim":
                    return 200, svc.reclaim(self._require_user(), game_id)
                if sub == "join":
                    raise ApiError(422, "Las invitaciones necesitan el servidor")
                if sub == "replay":
                    return 200, svc.replay(game_id, self.user, token)
                self._adopt(game_id, token)
                if sub is None:
                    return 200, svc.get_game(game_id, token)
                if sub == "deal" and method == "POST":
                    return 200, svc.deal(game_id, token)
                if sub == "tick" and method == "POST":
                    return 200, svc.tick(game_id, token)
                if sub == "look" and method == "POST":
                    target = body.get("target")
                    return 200, svc.look(game_id, token, None if target is None else int(target))
                if sub == "signal" and method == "POST":
                    return 200, svc.signal(game_id, token, str(body.get("signal", "")))
                if sub == "action" and method == "POST":
                    return 200, svc.action(game_id, token, body.get("action") or {})
                if sub == "help":
                    return 200, svc.help(game_id, token)
                if sub == "analysis":
                    return 200, svc.analysis(game_id, token)
            if path == "/api/cloud/import" and method == "POST":
                return 200, self._cloud_import(body)
            m = re.fullmatch(r"/api/cloud/export/([\w-]+)", path)
            if m:
                return 200, self._cloud_export(m.group(1))
            if path == "/api/history":
                return 200, svc.history(self._require_user())
            if path == "/api/players/me/statistics":
                return 200, svc.statistics(self._require_user())
            if path == "/api/bots":
                return 200, svc.bots()
            if path == "/api/arena/watch":
                seed = body.get("seed")
                return 200, svc.watch(
                    str(body.get("team_a")), str(body.get("team_b")), int(seed) if seed else None
                )
            if path == "/api/training/scenarios":
                return 200, svc.scenarios()
            m = re.fullmatch(r"/api/training/scenarios/([\w-]+)", path)
            if m and method == "POST":
                return 200, svc.answer_scenario(m.group(1), body.get("action") or {})
            raise ApiError(404, "Ruta no disponible en la versión web")
        except ApiError as exc:
            return exc.status, {"detail": exc.detail}
        except (ValueError, TypeError) as exc:
            return 422, {"detail": f"Petición no válida: {exc}"}


_backend: LocalBackend | None = None


def handle_json(method: str, path: str, body: str | None, token: str | None) -> str:
    """Punto de entrada para el worker: recibe y devuelve JSON en texto."""
    global _backend
    if _backend is None:
        _backend = LocalBackend()
    status, data = _backend.handle(method, path, json.loads(body) if body else None, token)
    return json.dumps({"status": status, "data": data})
