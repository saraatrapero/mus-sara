"""Backend que se ejecuta **dentro del navegador** (Pyodide, en un Web Worker).

Sustituye al servidor FastAPI en GitHub Pages: el frontend hace las mismas peticiones
(``/api/...``) y el worker las pasa a :func:`handle`, que las resuelve con
:class:`musst.server.service.MusService`. Motor, bots, agentes y aprendizaje son exactamente
los mismos que en el servidor.

Diferencias con el servidor (y por qué):

* **Perfil local** en lugar de cuentas: no hay servidor que guarde contraseñas. Los datos
  (partidas, estadísticas, lo que el bot aprende de ti) se guardan en SQLite dentro del
  navegador (IndexedDB) y no salen de él.
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
from musst.server.service import ApiError, MusService

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
        if not USERNAME.match(username or ""):
            raise ApiError(422, "Nombre: de 3 a 32 letras, números, punto, guion o guion bajo")
        user = self.repo.get_or_create_local_user(username)
        self._set_profile(user)
        return {"id": user.id, "username": user.username}

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
        seat = session.seats[0]
        if seat.kind == "human" and seat.token is None:
            seat.token = token

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
            if path in ("/api/auth/login", "/api/auth/register"):
                return 200, self._local_login(str(body.get("username", "")))
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
                if sub == "action" and method == "POST":
                    return 200, svc.action(game_id, token, body.get("action") or {})
                if sub == "help":
                    return 200, svc.help(game_id, token)
                if sub == "analysis":
                    return 200, svc.analysis(game_id, token)
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
