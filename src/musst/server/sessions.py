"""Gestión de partidas en el servidor: asientos humanos y bots, recuperación y aprendizaje.

El servidor guarda el estado secreto; a los clientes solo se les entregan observaciones.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from musst.agents.base import Decision
from musst.analytics.analysis import key_moments, seat_statistics
from musst.bots.api import Bot, GameEndInfo, GameStartInfo
from musst.bots.registry import get_entry
from musst.engine.actions import Action, action_from_dict, action_to_dict
from musst.engine.config import RulesConfig
from musst.engine.game import IllegalAction, MusGame, partner_of, team_of
from musst.engine.observation import build_observation, build_spectator_view
from musst.learning.updater import Learner
from musst.persistence.db import Repository, RepositoryModelStore
from musst.runtime.runner import FallbackBot

log = logging.getLogger("musst.public.server")

BOT_LEVELS = ("sencillo", "medio", "profesional")


@dataclass
class Seat:
    index: int
    kind: str  # "human" | "bot"
    name: str
    player_id: str
    user_id: int | None = None
    token: str | None = None
    bot: Bot | None = None
    level: str | None = None
    avatar: str | None = None
    connected: bool = True


@dataclass
class GameSession:
    id: str
    mode: str
    game: MusGame
    seats: list[Seat]
    created_by: int | None
    status: str = "PLAYING"
    actions: list[dict[str, Any]] = field(default_factory=list)
    invite_token: str | None = None
    learning: list[str] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)  # solo modo desarrollo
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_activity: float = field(default_factory=time.time)

    def seat_for_token(self, token: str | None) -> Seat | None:
        if not token:
            return None
        for seat in self.seats:
            if seat.token and secrets.compare_digest(seat.token, token):
                return seat
        return None

    def public_seats(self) -> list[dict[str, Any]]:
        return [
            {
                "seat": s.index,
                "kind": s.kind,
                "name": s.name,
                "team": team_of(s.index),
                "level": s.level,
                "avatar": s.avatar,
                "connected": s.connected,
                "waiting": s.kind == "human" and s.token is None,
            }
            for s in self.seats
        ]


class SessionManager:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo
        self.sessions: dict[str, GameSession] = {}
        self.learner = Learner(RepositoryModelStore(repo))
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ creación
    def create(
        self,
        mode: str,
        human_name: str,
        user_id: int | None,
        partner: str,
        rivals: str,
        target: int = 40,
        seed: int | None = None,
        names: dict[str, str] | None = None,
        avatar: str | None = None,
    ) -> tuple[GameSession, str]:
        """Crea una partida. El humano ocupa el asiento 0; su pareja, el 2."""
        config = RulesConfig(target_points=target)
        game = MusGame(seed=seed, config=config)
        game_id = uuid.uuid4().hex[:12]
        token = secrets.token_urlsafe(24)
        names = names or {}
        seats = [
            Seat(
                0,
                "human",
                human_name,
                f"user:{user_id}" if user_id else f"guest:{token[:8]}",
                user_id,
                token,
                avatar=avatar,
            ),
        ]
        rival_level = rivals if rivals in BOT_LEVELS else "medio"
        invite = None
        for idx in (1, 2, 3):
            if idx == 2 and partner == "human":
                invite = secrets.token_urlsafe(12)
                seats.append(
                    Seat(2, "human", names.get("partner", "Compañero"), f"invite:{invite[:8]}")
                )
                continue
            level = (partner if partner in BOT_LEVELS else "sencillo") if idx == 2 else rival_level
            default_name = f"Bot {'compañero' if idx == 2 else ('1' if idx == 1 else '2')}"
            seats.append(
                Seat(
                    idx, "bot", names.get(str(idx), default_name), f"bot:{level}:{idx}", level=level
                )
            )
        session = GameSession(game_id, mode, game, seats, user_id, invite_token=invite)
        for seat in session.seats:
            if seat.kind == "bot":
                seat.bot = self._make_bot(seat.level or "medio", game.seed + seat.index)
                self._start_bot(session, seat)
        with self._lock:
            self.sessions[game_id] = session
        self._persist(session)
        self.advance_bots(session)
        return session, token

    def _make_bot(self, level: str, seed: int) -> Bot:
        if level == "profesional":
            from musst.agents.orchestrator import ProBot

            return ProBot(seed=seed, learner=self.learner)
        entry = get_entry(level)
        bot = entry.factory()
        if hasattr(bot, "rng"):
            import random

            bot.rng = random.Random(seed)
        return bot

    def _start_bot(self, session: GameSession, seat: Seat) -> None:
        assert seat.bot is not None
        info = GameStartInfo(
            seat=seat.index,
            partner=partner_of(seat.index),
            team=team_of(seat.index),
            target=session.game.config.target_points,
            player_names=tuple(s.name for s in session.seats),  # type: ignore[arg-type]
            context={"player_ids": [s.player_id for s in session.seats]},
        )
        try:
            seat.bot.on_game_start(info)
        except Exception:
            seat.bot = FallbackBot()

    def join(
        self, game_id: str, invite: str, name: str, user_id: int | None
    ) -> tuple[GameSession, str]:
        session = self.get(game_id)
        if (
            session is None
            or not session.invite_token
            or not secrets.compare_digest(session.invite_token, invite)
        ):
            raise PermissionError("Invitación no válida")
        seat = session.seats[2]
        if seat.token is not None:
            raise PermissionError("La plaza ya está ocupada")
        seat.token = secrets.token_urlsafe(24)
        seat.name = name or seat.name
        seat.user_id = user_id
        seat.player_id = f"user:{user_id}" if user_id else f"guest:{seat.token[:8]}"
        self._persist(session)
        return session, seat.token

    def get(self, game_id: str) -> GameSession | None:
        session = self.sessions.get(game_id)
        if session is None:
            session = self._recover(game_id)
        return session

    # ------------------------------------------------------------------ juego
    def apply_human(self, session: GameSession, seat: Seat, data: dict[str, Any]) -> None:
        """Valida y aplica la acción de un humano y deja jugar a los bots hasta el próximo humano."""
        with session.lock:
            if session.status not in ("PLAYING", "PAUSED"):
                raise IllegalAction("La partida no está en juego")
            action = action_from_dict(data)  # ValueError si la forma es inválida
            session.game.apply(seat.index, action)  # IllegalAction si no es legal
            session.status = "PLAYING"
            session.actions.append({"seat": seat.index, "action": action_to_dict(action)})
            session.last_activity = time.time()
            self.advance_bots(session)

    def advance_bots(self, session: GameSession) -> None:
        game = session.game
        guard = 0
        while not game.finished and guard < 500:
            guard += 1
            turn = game.turn
            assert turn is not None
            seat = session.seats[turn]
            if seat.kind == "human":
                break
            assert seat.bot is not None
            obs = build_observation(game, turn)
            try:
                action: Action = seat.bot.decide(obs)
                game.apply(turn, action)
            except Exception as exc:  # un bot nunca rompe la partida del humano
                log.warning("Bot %s falló: %r; se usa FallbackBot", seat.name, exc)
                seat.bot = FallbackBot()
                action = seat.bot.decide(obs)
                game.apply(turn, action)
            session.actions.append({"seat": turn, "action": action_to_dict(action)})
            last = getattr(seat.bot, "last_decision", None)
            if isinstance(last, Decision):
                session.decisions.append(
                    {"seat": turn, "round": game.round_no, **last.explanation()}
                )
        if game.finished and session.status != "FINISHED":
            self._finish(session)
        else:
            self._persist(session)

    def _finish(self, session: GameSession) -> None:
        session.status = "FINISHED"
        game = session.game
        assert game.result is not None
        history = [e.to_dict() for e in game.events if e.visible_to(None)]
        end = GameEndInfo(game.result.winner, game.result.score, game.result.reason, tuple(history))
        for seat in session.seats:
            if seat.bot is not None:
                try:
                    seat.bot.on_game_end(end)
                except Exception:
                    log.warning("on_game_end falló para %s", seat.name)
        humans = {s.index: s.player_id for s in session.seats if s.kind == "human" and s.token}
        try:
            updates = self.learner.learn_game(history, humans, game.config.target_points)
            session.learning = [line for u in updates for line in u.summary]
            if updates:
                session.learning.insert(
                    0, "El bot ha actualizado su modelo sobre tu forma de jugar."
                )
        except Exception:
            log.exception("Fallo al aprender de la partida %s", session.id)
        self._persist(session, history)
        for seat in session.seats:
            if seat.kind == "human" and seat.user_id:
                won = game.result.winner == team_of(seat.index)
                stats = seat_statistics(history, seat.index, game.config.target_points)
                stats.update(score=list(game.result.score), reason=game.result.reason)
                self.repo.add_statistics(seat.user_id, session.id, won, stats)
                self._achievements(seat, session, won, stats)

    def _achievements(
        self, seat: Seat, session: GameSession, won: bool, stats: dict[str, Any]
    ) -> None:
        assert seat.user_id is not None
        uid = seat.user_id
        games = self.repo.user_statistics(uid)
        grant = self.repo.grant_achievement
        grant(uid, "primera_partida")
        if won:
            grant(uid, "primera_victoria")
            if any(
                s.level == "profesional"
                for s in session.seats
                if s.kind == "bot" and team_of(s.index) != team_of(seat.index)
            ):
                grant(uid, "victoria_contra_profesional")
            score = session.game.result.score if session.game.result else (0, 0)
            if score[team_of(seat.index)] >= session.game.config.target_points:
                grant(uid, "cuarenta_tantos")
            if self._comeback(session, team_of(seat.index)):
                grant(uid, "remontada")
        if stats.get("ordagos"):
            grant(uid, "primer_ordago")
        if len(games) >= 100:
            grant(uid, "cien_partidas")

    @staticmethod
    def _comeback(session: GameSession, team: int) -> bool:
        worst = 0
        for e in session.game.events:
            if e.kind.value == "PointsAwarded":
                score = e.payload["score"]
                worst = min(worst, score[team] - score[1 - team])
        return worst <= -15

    # ------------------------------------------------------------------ vistas
    def observation(self, session: GameSession, seat: Seat) -> dict[str, Any]:
        obs = build_observation(session.game, seat.index).to_dict()
        obs.update(
            game_id=session.id,
            mode=session.mode,
            status=session.status,
            seats=session.public_seats(),
            invite=session.invite_token
            if seat.index == 0 and session.seats[2].token is None
            else None,
        )
        if session.status == "FINISHED":
            obs["learning"] = session.learning
        return obs

    def spectator(self, session: GameSession) -> dict[str, Any]:
        view = build_spectator_view(session.game)
        view.update(game_id=session.id, seats=session.public_seats(), status=session.status)
        return view

    def analysis(self, session: GameSession, seat: Seat) -> dict[str, Any]:
        if session.status != "FINISHED":
            raise PermissionError("El análisis solo está disponible al terminar la partida")
        history = [e.to_dict() for e in session.game.events if e.visible_to(None)]
        moments = key_moments(history)
        return {
            "result": {
                "winner": session.game.result.winner if session.game.result else None,
                "score": list(session.game.score),
                "my_team": team_of(seat.index),
            },
            "stats": seat_statistics(history, seat.index, session.game.config.target_points),
            "key_moments": [m.__dict__ for m in moments],
            "learning": session.learning,
            "history": history,
        }

    # ------------------------------------------------------------------ persistencia
    def _persist(self, session: GameSession, history: list[dict[str, Any]] | None = None) -> None:
        game = session.game
        seats = [
            {
                "seat": s.index,
                "kind": s.kind,
                "name": s.name,
                "player_id": s.player_id,
                "user_id": s.user_id,
                "level": s.level,
                "token_hash": None,
            }
            for s in session.seats
        ]
        result = game.result
        self.repo.save_game(
            session.id,
            session.mode,
            session.status,
            game.seed,
            game.config.to_dict(),
            seats,
            session.actions,
            session.created_by,
            history,
            result.winner if result else None,
            result.score if result else None,
        )

    def _recover(self, game_id: str) -> GameSession | None:
        """Reconstruye una partida interrumpida a partir de su seed y sus acciones."""
        data = self.repo.load_game(game_id)
        if data is None or data["status"] not in ("PLAYING", "PAUSED"):
            return None
        game = MusGame(seed=data["seed"], config=RulesConfig.from_dict(data["config"]))
        for item in data["actions"]:
            game.apply(item["seat"], action_from_dict(item["action"]))
        seats = []
        for s in data["seats"]:
            seat = Seat(
                s["seat"],
                s["kind"],
                s["name"],
                s["player_id"],
                s.get("user_id"),
                level=s.get("level"),
            )
            seats.append(seat)
        session = GameSession(
            game_id, data["mode"], game, seats, data["created_by"], "PAUSED", data["actions"]
        )
        for seat in seats:
            if seat.kind == "bot":
                seat.bot = self._make_bot(seat.level or "medio", game.seed + seat.index)
                self._start_bot(session, seat)
        self.sessions[game_id] = session
        return session

    def reclaim(self, session: GameSession, user_id: int) -> str | None:
        """Un usuario registrado recupera su asiento tras cerrar la app (nuevo token)."""
        for seat in session.seats:
            if seat.kind == "human" and seat.user_id == user_id:
                seat.token = secrets.token_urlsafe(24)
                return seat.token
        return None
