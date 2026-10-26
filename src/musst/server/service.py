"""Casos de uso de la API, sin dependencia de ningún framework web.

Los usan dos adaptadores:

* ``musst.server.app``: FastAPI (servidor con usuarios, invitaciones y torneo).
* ``musst.web.backend``: el mismo Python ejecutándose en el navegador con Pyodide
  (GitHub Pages, sin servidor).

Así las reglas de acceso (quién ve qué) se escriben una sola vez.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from musst.bots.registry import BotEntry, all_entries, builtin_entries
from musst.engine.game import IllegalAction
from musst.engine.observation import build_observation
from musst.persistence.db import Repository, User
from musst.runtime.runner import play_game
from musst.server import coach
from musst.server.sessions import BOT_LEVELS, GameSession, Seat, SessionManager

MODES = ("rapida", "personalizada", "entrenamiento", "contra_bot")
PROFILE_SETTINGS = {"theme", "text_size", "reduce_motion", "sound", "speed", "table", "card_back"}


class ApiError(Exception):
    """Error con código HTTP; cada adaptador lo traduce a su formato."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class MusService:
    def __init__(
        self,
        repo: Repository,
        *,
        human_partner: bool = True,
        external_bots: bool = True,
        scoreboard: Callable[[], Any] | None = None,
    ) -> None:
        self.repo = repo
        self.manager = SessionManager(repo)
        self.human_partner = human_partner
        self.external_bots = external_bots
        self._scoreboard = scoreboard

    # ------------------------------------------------------------------ utilidades
    def seat_of(self, game_id: str, token: str | None) -> tuple[GameSession, Seat]:
        session = self.manager.get(game_id)
        if session is None:
            raise ApiError(404, "Partida no encontrada")
        seat = session.seat_for_token(token)
        if seat is None:
            raise ApiError(403, "No ocupas un asiento en esta partida")
        return session, seat

    def _entries(self) -> list[BotEntry]:
        return all_entries(sandboxed=True) if self.external_bots else builtin_entries()

    # ------------------------------------------------------------------ perfil
    @staticmethod
    def me(user: User | None) -> dict[str, Any] | None:
        if user is None:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "avatar": user.avatar,
            "settings": user.settings,
        }

    def update_me(
        self, user: User, avatar: str | None, settings: dict[str, Any]
    ) -> dict[str, bool]:
        clean = {k: v for k, v in settings.items() if k in PROFILE_SETTINGS}
        self.repo.update_user(user.id, avatar, clean)
        return {"ok": True}

    # ------------------------------------------------------------------ partidas
    def new_game(self, user: User | None, body: dict[str, Any]) -> dict[str, Any]:
        mode = body.get("mode", "rapida")
        partner = body.get("partner", "sencillo")
        rivals = body.get("rivals", "medio")
        target = int(body.get("target", 40))
        seed = body.get("seed")
        if mode not in MODES or rivals not in BOT_LEVELS:
            raise ApiError(422, "Parámetros de partida no válidos")
        if partner not in (*BOT_LEVELS, "human"):
            raise ApiError(422, "Compañero no válido")
        if partner == "human" and not self.human_partner:
            raise ApiError(422, "El compañero humano necesita el servidor; aquí juega con un bot")
        if not 10 <= target <= 60 or (seed is not None and not 0 <= int(seed) <= 2**31):
            raise ApiError(422, "Objetivo o semilla fuera de rango")
        name = user.username if user else str(body.get("name") or "Tú")[:24]
        names = {str(k): str(v)[:24] for k, v in (body.get("names") or {}).items()}
        session, token = self.manager.create(
            mode,
            name,
            user.id if user else None,
            partner,
            rivals,
            target,
            int(seed) if seed is not None else None,
            names,
            body.get("avatar") or (user.avatar if user else None),
        )
        return {
            "game_id": session.id,
            "seat_token": token,
            "observation": self.manager.observation(session, session.seats[0]),
        }

    def join(self, user: User | None, game_id: str, invite: str, name: str) -> dict[str, Any]:
        try:
            session, token = self.manager.join(game_id, invite, name, user.id if user else None)
        except PermissionError as exc:
            raise ApiError(403, str(exc)) from exc
        return {
            "game_id": session.id,
            "seat_token": token,
            "observation": self.manager.observation(session, session.seats[2]),
        }

    def reclaim(self, user: User, game_id: str) -> dict[str, Any]:
        session = self.manager.get(game_id)
        if session is None:
            raise ApiError(404, "Partida no encontrada")
        token = self.manager.reclaim(session, user.id)
        if token is None:
            raise ApiError(403, "No jugabas en esta partida")
        return {"game_id": game_id, "seat_token": token}

    def get_game(self, game_id: str, token: str | None) -> dict[str, Any]:
        session, seat = self.seat_of(game_id, token)
        return self.manager.observation(session, seat)

    def action(self, game_id: str, token: str | None, action: dict[str, Any]) -> dict[str, Any]:
        session, seat = self.seat_of(game_id, token)
        try:
            self.manager.apply_human(session, seat, action)
        except (IllegalAction, ValueError) as exc:
            raise ApiError(422, f"Acción no válida: {exc}") from exc
        return self.manager.observation(session, seat)

    def help(self, game_id: str, token: str | None) -> dict[str, Any]:
        session, seat = self.seat_of(game_id, token)
        return coach.explain_legal_actions(build_observation(session.game, seat.index))

    def analysis(self, game_id: str, token: str | None) -> dict[str, Any]:
        session, seat = self.seat_of(game_id, token)
        try:
            return self.manager.analysis(session, seat)
        except PermissionError as exc:
            raise ApiError(403, str(exc)) from exc

    def replay(self, game_id: str, user: User | None, token: str | None) -> dict[str, Any]:
        """Replay de una partida terminada (solo para quien la jugó)."""
        data = self.repo.load_game(game_id)
        if data is None:
            raise ApiError(404, "Partida no encontrada")
        if data["status"] != "FINISHED" or data["history"] is None:
            raise ApiError(403, "El replay solo está disponible al terminar la partida")
        allowed = user is not None and any(s.get("user_id") == user.id for s in data["seats"])
        session = self.manager.sessions.get(game_id)
        if session is not None and session.seat_for_token(token) is not None:
            allowed = True
        if not allowed:
            raise ApiError(403, "Solo puedes ver el replay de tus partidas")
        return {
            "game_id": game_id,
            "seats": [{k: s[k] for k in ("seat", "kind", "name", "level")} for s in data["seats"]],
            "history": data["history"],
            "score": data["score"],
            "winner": data["winner"],
        }

    def history(self, user: User) -> list[dict[str, Any]]:
        return self.repo.user_games(user.id)

    # ------------------------------------------------------------------ estadísticas
    def statistics(self, user: User) -> dict[str, Any]:
        rows = self.repo.user_statistics(user.id)
        model = self.manager.learner.long_model(f"user:{user.id}")
        totals: dict[str, float] = defaultdict(float)
        by_lance: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        timeline = []
        for r in rows:
            s = r["stats"]
            for key in (
                "envites",
                "ordagos",
                "aceptaciones",
                "rechazos",
                "mus",
                "cortes",
                "tantos_pareja",
            ):
                totals[key] += s.get(key, 0) or 0
            for lance, d in s.get("por_lance", {}).items():
                for k, v in d.items():
                    by_lance[lance][k] += v
            timeline.append({"at": r["at"], "won": r["won"], "tantos": s.get("tantos_pareja", 0)})
        games = len(rows)
        wins = sum(1 for r in rows if r["won"])
        return {
            "partidas": games,
            "victorias": wins,
            "derrotas": games - wins,
            "porcentaje_victorias": wins / games if games else None,
            "tantos_medios": totals["tantos_pareja"] / games if games else None,
            "totales": dict(totals),
            "por_lance": {k: dict(v) for k, v in by_lance.items()},
            "evolucion": timeline,
            "estilo": model.profile(),
            "logros": self.repo.achievements(user.id),
        }

    # ------------------------------------------------------------------ bots, arena y entrenamiento
    def bots(self) -> list[dict[str, Any]]:
        return [
            {
                "name": e.name,
                "author": e.author,
                "version": e.version,
                "level": e.level,
                "external": e.external,
                "description": e.description,
            }
            for e in self._entries()
        ]

    def scoreboard(self) -> Any:
        if self._scoreboard is None:
            return {"ranking": [], "note": "Aún no se ha ejecutado el torneo"}
        return self._scoreboard()

    def watch(self, team_a: str, team_b: str, seed: int | None = None) -> dict[str, Any]:
        """Bot vs Bot para observar: solo eventos públicos (las manos, al final de cada jugada)."""
        internal = {e.name: e for e in builtin_entries()}
        if team_a not in internal or team_b not in internal:
            raise ApiError(422, "Bot desconocido")
        a, b = internal[team_a], internal[team_b]
        seed = seed if seed is not None else random.randrange(2**31)
        match = play_game(
            [a.factory(), b.factory(), a.factory(), b.factory()],
            seed=seed,
            names=[a.name, b.name, a.name, b.name],
        )
        return {
            "seed": seed,
            "names": [a.name, b.name, a.name, b.name],
            "history": [e.to_dict() for e in match.events if e.visible_to(None)],
            "winner": match.result.winner,
            "score": list(match.result.score),
        }

    @staticmethod
    def scenarios() -> list[dict[str, Any]]:
        return [coach.scenario_public(s) for s in coach.SCENARIOS]

    @staticmethod
    def answer_scenario(scenario_id: str, action: dict[str, Any]) -> dict[str, Any]:
        sc = next((s for s in coach.SCENARIOS if s.id == scenario_id), None)
        if sc is None:
            raise ApiError(404, "Situación no encontrada")
        try:
            return coach.analyse_answer(sc, action)
        except ValueError as exc:
            raise ApiError(422, str(exc)) from exc


def file_scoreboard(path: Path) -> Callable[[], Any]:
    def load() -> Any:
        if not path.exists():
            return {"ranking": [], "note": "Aún no se ha ejecutado el torneo"}
        return json.loads(path.read_text())

    return load
