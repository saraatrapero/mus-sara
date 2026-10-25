"""API web de MUS.ST (FastAPI) y servidor del frontend estático.

Ejecutar en local::

    uvicorn musst.server.app:app --reload

Principio de seguridad: el cliente **nunca** recibe el estado del motor, solo la observación de
su asiento. El asiento se deduce del token de asiento, no de lo que diga el cliente.
"""

import json
import os
import random
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from musst.bots.registry import all_entries
from musst.engine.game import IllegalAction
from musst.persistence.db import Repository, User
from musst.runtime.runner import play_game
from musst.server import coach
from musst.server.sessions import GameSession, Seat, SessionManager

STATIC_DIR = Path(__file__).parent / "static"
DEV_MODE = os.environ.get("MUSST_DEV_MODE") == "1"
DB_PATH = os.environ.get("MUSST_DB", "musst.sqlite3")
SCOREBOARD_PATH = Path(os.environ.get("MUSST_SCOREBOARD", "scoreboard_out/scoreboard.json"))
SESSION_COOKIE = "musst_session"


class RateLimiter:
    """Límite simple por clave (IP) en una ventana deslizante."""

    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = limit
        self.window = window_s
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.time()
        q = self.hits[key]
        while q and q[0] < now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "Demasiadas peticiones, espera un momento")
        q.append(now)


# ---------------------------------------------------------------------------- esquemas
class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class ProfileUpdate(BaseModel):
    avatar: str | None = Field(default=None, max_length=64)
    settings: dict[str, Any] = Field(default_factory=dict)


class NewGame(BaseModel):
    mode: Literal["rapida", "personalizada", "entrenamiento", "contra_bot"] = "rapida"
    name: str = Field(default="Tú", min_length=1, max_length=24)
    partner: Literal["sencillo", "medio", "profesional", "human"] = "sencillo"
    rivals: Literal["sencillo", "medio", "profesional"] = "medio"
    target: int = Field(default=40, ge=10, le=60)
    seed: int | None = Field(default=None, ge=0, le=2**31)
    names: dict[str, str] = Field(default_factory=dict)
    avatar: str | None = Field(default=None, max_length=64)


class JoinGame(BaseModel):
    invite: str = Field(min_length=4, max_length=64)
    name: str = Field(default="Compañero", min_length=1, max_length=24)


class ActionRequest(BaseModel):
    action: dict[str, Any]


class WatchRequest(BaseModel):
    team_a: str
    team_b: str
    seed: int | None = Field(default=None, ge=0, le=2**31)


def create_app(repo: Repository | None = None, dev_mode: bool = DEV_MODE) -> FastAPI:
    repository = repo or Repository(DB_PATH)
    manager = SessionManager(repository)
    login_limiter = RateLimiter(10, 60)
    action_limiter = RateLimiter(240, 60)

    app = FastAPI(
        title="MUS.ST", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.state.manager = manager
    app.state.repo = repository

    # ------------------------------------------------------------------ dependencias
    def current_user(musst_session: Annotated[str | None, Cookie()] = None) -> User | None:
        return repository.session_user(musst_session)

    def require_user(user: Annotated[User | None, Depends(current_user)]) -> User:
        if user is None:
            raise HTTPException(401, "Inicia sesión")
        return user

    def seat_of(game_id: str, x_seat_token: str | None) -> tuple[GameSession, Seat]:
        session = manager.get(game_id)
        if session is None:
            raise HTTPException(404, "Partida no encontrada")
        seat = session.seat_for_token(x_seat_token)
        if seat is None:
            raise HTTPException(403, "No ocupas un asiento en esta partida")
        return session, seat

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    # ------------------------------------------------------------------ auth
    @app.post("/api/auth/register")
    def register(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
        login_limiter.check(request.client.host if request.client else "?")
        try:
            user = repository.create_user(body.username, body.password)
        except Exception as exc:
            raise HTTPException(409, "Ese nombre de usuario ya existe") from exc
        _set_session(response, repository.create_session(user.id))
        return {"id": user.id, "username": user.username}

    @app.post("/api/auth/login")
    def login(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
        login_limiter.check(request.client.host if request.client else "?")
        user = repository.authenticate(body.username, body.password)
        if user is None:
            raise HTTPException(401, "Usuario o contraseña incorrectos")
        _set_session(response, repository.create_session(user.id))
        return {"id": user.id, "username": user.username}

    @app.post("/api/auth/logout")
    def logout(
        response: Response, musst_session: Annotated[str | None, Cookie()] = None
    ) -> dict[str, bool]:
        if musst_session:
            repository.delete_session(musst_session)
        response.delete_cookie(SESSION_COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(user: Annotated[User | None, Depends(current_user)]) -> dict[str, Any] | None:
        if user is None:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "avatar": user.avatar,
            "settings": user.settings,
        }

    @app.put("/api/me")
    def update_me(
        body: ProfileUpdate, user: Annotated[User, Depends(require_user)]
    ) -> dict[str, bool]:
        allowed = {"theme", "text_size", "reduce_motion", "sound", "speed", "table", "card_back"}
        settings = {k: v for k, v in body.settings.items() if k in allowed}
        repository.update_user(user.id, body.avatar, settings)
        return {"ok": True}

    # ------------------------------------------------------------------ partidas
    @app.post("/api/games")
    def new_game(
        body: NewGame, request: Request, user: Annotated[User | None, Depends(current_user)]
    ) -> dict[str, Any]:
        action_limiter.check(request.client.host if request.client else "?")
        name = user.username if user else body.name
        session, token = manager.create(
            body.mode,
            name,
            user.id if user else None,
            body.partner,
            body.rivals,
            body.target,
            body.seed,
            body.names,
            body.avatar or (user.avatar if user else None),
        )
        seat = session.seats[0]
        return {
            "game_id": session.id,
            "seat_token": token,
            "observation": manager.observation(session, seat),
        }

    @app.post("/api/games/{game_id}/join")
    def join_game(
        game_id: str, body: JoinGame, user: Annotated[User | None, Depends(current_user)]
    ) -> dict[str, Any]:
        try:
            session, token = manager.join(
                game_id, body.invite, body.name, user.id if user else None
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        return {
            "game_id": session.id,
            "seat_token": token,
            "observation": manager.observation(session, session.seats[2]),
        }

    @app.post("/api/games/{game_id}/reclaim")
    def reclaim(game_id: str, user: Annotated[User, Depends(require_user)]) -> dict[str, Any]:
        session = manager.get(game_id)
        if session is None:
            raise HTTPException(404, "Partida no encontrada")
        token = manager.reclaim(session, user.id)
        if token is None:
            raise HTTPException(403, "No jugabas en esta partida")
        return {"game_id": game_id, "seat_token": token}

    @app.get("/api/games/{game_id}")
    def get_game(
        game_id: str, x_seat_token: Annotated[str | None, Header()] = None
    ) -> dict[str, Any]:
        session, seat = seat_of(game_id, x_seat_token)
        return manager.observation(session, seat)

    @app.post("/api/games/{game_id}/action")
    def post_action(
        game_id: str,
        body: ActionRequest,
        request: Request,
        x_seat_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        action_limiter.check(request.client.host if request.client else "?")
        session, seat = seat_of(game_id, x_seat_token)
        try:
            manager.apply_human(session, seat, body.action)
        except (IllegalAction, ValueError) as exc:
            raise HTTPException(422, f"Acción no válida: {exc}") from exc
        return manager.observation(session, seat)

    @app.get("/api/games/{game_id}/help")
    def help_now(
        game_id: str, x_seat_token: Annotated[str | None, Header()] = None
    ) -> dict[str, Any]:
        from musst.engine.observation import build_observation

        session, seat = seat_of(game_id, x_seat_token)
        return coach.explain_legal_actions(build_observation(session.game, seat.index))

    @app.get("/api/games/{game_id}/analysis")
    def analysis(
        game_id: str, x_seat_token: Annotated[str | None, Header()] = None
    ) -> dict[str, Any]:
        session, seat = seat_of(game_id, x_seat_token)
        try:
            return manager.analysis(session, seat)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.get("/api/games/{game_id}/replay")
    def replay(
        game_id: str,
        user: Annotated[User | None, Depends(current_user)],
        x_seat_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        """Replay de una partida terminada (solo para quien la jugó)."""
        data = repository.load_game(game_id)
        if data is None:
            raise HTTPException(404, "Partida no encontrada")
        if data["status"] != "FINISHED" or data["history"] is None:
            raise HTTPException(403, "El replay solo está disponible al terminar la partida")
        allowed = user is not None and any(s.get("user_id") == user.id for s in data["seats"])
        session = manager.sessions.get(game_id)
        if session is not None and session.seat_for_token(x_seat_token) is not None:
            allowed = True
        if not allowed:
            raise HTTPException(403, "Solo puedes ver el replay de tus partidas")
        return {
            "game_id": game_id,
            "seats": [{k: s[k] for k in ("seat", "kind", "name", "level")} for s in data["seats"]],
            "history": data["history"],
            "score": data["score"],
            "winner": data["winner"],
        }

    @app.get("/api/history")
    def history(user: Annotated[User, Depends(require_user)]) -> list[dict[str, Any]]:
        return repository.user_games(user.id)

    # ------------------------------------------------------------------ estadísticas
    @app.get("/api/players/me/statistics")
    def my_statistics(user: Annotated[User, Depends(require_user)]) -> dict[str, Any]:
        rows = repository.user_statistics(user.id)
        model = manager.learner.long_model(f"user:{user.id}")
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
            "logros": repository.achievements(user.id),
        }

    # ------------------------------------------------------------------ bots, arena y entrenamiento
    @app.get("/api/bots")
    def bots() -> list[dict[str, Any]]:
        return [
            {
                "name": e.name,
                "author": e.author,
                "version": e.version,
                "level": e.level,
                "external": e.external,
                "description": e.description,
            }
            for e in all_entries(sandboxed=True)
        ]

    @app.get("/api/scoreboard")
    def scoreboard() -> Any:
        if not SCOREBOARD_PATH.exists():
            return JSONResponse({"ranking": [], "note": "Aún no se ha ejecutado el torneo"})
        return json.loads(SCOREBOARD_PATH.read_text())

    @app.post("/api/arena/watch")
    def watch(body: WatchRequest, request: Request) -> dict[str, Any]:
        """Bot vs Bot para observar: solo eventos públicos (las manos, al final de cada jugada)."""
        action_limiter.check(request.client.host if request.client else "?")
        internal = {e.name: e for e in all_entries(sandboxed=True) if not e.external}
        if body.team_a not in internal or body.team_b not in internal:
            raise HTTPException(422, "Bot desconocido")
        a, b = internal[body.team_a], internal[body.team_b]
        seed = body.seed if body.seed is not None else random.randrange(2**31)
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

    @app.get("/api/training/scenarios")
    def scenarios() -> list[dict[str, Any]]:
        return [coach.scenario_public(s) for s in coach.SCENARIOS]

    @app.post("/api/training/scenarios/{scenario_id}")
    def answer_scenario(scenario_id: str, body: ActionRequest) -> dict[str, Any]:
        sc = next((s for s in coach.SCENARIOS if s.id == scenario_id), None)
        if sc is None:
            raise HTTPException(404, "Situación no encontrada")
        try:
            return coach.analyse_answer(sc, body.action)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    # ------------------------------------------------------------------ modo desarrollo
    if dev_mode:

        @app.get("/api/dev/games/{game_id}")
        def dev_state(game_id: str) -> dict[str, Any]:
            """SOLO DESARROLLO: estado completo, incluidas las cartas y las decisiones de los agentes."""
            session = manager.get(game_id)
            if session is None:
                raise HTTPException(404, "Partida no encontrada")
            g = session.game
            return {
                "phase": g.phase.value,
                "turn": g.turn,
                "score": g.score,
                "hands": {s: [c.code for c in h] for s, h in enumerate(g.hands)},
                "deck": [c.code for c in g.deck],
                "events": [{**e.to_dict(), "visibility": e.visibility.value} for e in g.events],
                "agent_decisions": session.decisions[-50:],
            }

    # ------------------------------------------------------------------ frontend
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app


def _set_session(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("MUSST_SECURE_COOKIES", "1") == "1",
        max_age=7 * 24 * 3600,
    )


app = create_app() if os.environ.get("MUSST_NO_APP") != "1" else None  # type: ignore[assignment]
