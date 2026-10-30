"""API web de MUS.ST (FastAPI) y servidor del frontend estático.

Ejecutar en local::

    uvicorn musst.server.app:app --reload

Principio de seguridad: el cliente **nunca** recibe el estado del motor, solo la observación de
su asiento. El asiento se deduce del token de asiento, no de lo que diga el cliente.
"""

import os
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from musst.persistence.db import Repository, User
from musst.server.service import ApiError, MusService, file_scoreboard

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
    mode: Literal["rapida", "personalizada", "entrenamiento", "contra_bot", "campeonato"] = "rapida"
    name: str = Field(default="Tú", min_length=1, max_length=24)
    partner: Literal["sencillo", "medio", "profesional", "human"] = "sencillo"
    rivals: Literal["sencillo", "medio", "profesional"] = "medio"
    target: int = Field(default=40, ge=10, le=60)
    seed: int | None = Field(default=None, ge=0, le=2**31)
    names: dict[str, str] = Field(default_factory=dict)
    avatar: str | None = Field(default=None, max_length=64)
    signals: bool = True
    players: Literal["bot", "pareja", "cuatro"] = "bot"
    human_seats: list[int] | None = Field(default=None, max_length=3)


class JoinGame(BaseModel):
    invite: str = Field(min_length=4, max_length=64)
    name: str = Field(default="Compañero", min_length=1, max_length=24)


class ActionRequest(BaseModel):
    action: dict[str, Any]


class AdminUser(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    role: Literal["player", "admin"] = "player"


class AdminUserUpdate(BaseModel):
    username: str | None = Field(
        default=None, min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Literal["player", "admin"] | None = None


class LookRequest(BaseModel):
    target: int | None = Field(default=None, ge=0, le=3)


class SignalRequest(BaseModel):
    signal: str = Field(min_length=2, max_length=32)


class WatchRequest(BaseModel):
    team_a: str
    team_b: str
    seed: int | None = Field(default=None, ge=0, le=2**31)


def create_app(repo: Repository | None = None, dev_mode: bool = DEV_MODE) -> FastAPI:
    repository = repo or Repository(DB_PATH)
    service = MusService(repository, scoreboard=file_scoreboard(SCOREBOARD_PATH))
    manager = service.manager
    login_limiter = RateLimiter(10, 60)
    action_limiter = RateLimiter(240, 60)

    app = FastAPI(
        title="MUS.ST", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.state.manager = manager
    app.state.repo = repository

    @app.exception_handler(ApiError)
    async def api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)

    # ------------------------------------------------------------------ dependencias
    def current_user(musst_session: Annotated[str | None, Cookie()] = None) -> User | None:
        return repository.session_user(musst_session)

    def require_user(user: Annotated[User | None, Depends(current_user)]) -> User:
        if user is None:
            raise HTTPException(401, "Inicia sesión")
        return user

    def client_ip(request: Request) -> str:
        return request.client.host if request.client else "?"

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
        login_limiter.check(client_ip(request))
        try:
            user = repository.create_user(body.username, body.password)
        except Exception as exc:
            raise HTTPException(409, "Ese nombre de usuario ya existe") from exc
        _set_session(response, repository.create_session(user.id))
        return {"id": user.id, "username": user.username}

    @app.post("/api/auth/login")
    def login(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
        login_limiter.check(client_ip(request))
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
        return service.me(user)

    @app.put("/api/me")
    def update_me(
        body: ProfileUpdate, user: Annotated[User, Depends(require_user)]
    ) -> dict[str, bool]:
        return service.update_me(user, body.avatar, body.settings)

    # ------------------------------------------------------------------ administración
    @app.get("/api/admin/overview")
    def admin_overview(user: Annotated[User | None, Depends(current_user)]) -> dict[str, Any]:
        return service.admin_overview(user)

    @app.post("/api/admin/users")
    def admin_create(
        body: AdminUser, user: Annotated[User | None, Depends(current_user)]
    ) -> dict[str, Any]:
        return service.admin_create_user(user, body.model_dump())

    @app.put("/api/admin/users/{user_id}")
    def admin_update(
        user_id: int, body: AdminUserUpdate, user: Annotated[User | None, Depends(current_user)]
    ) -> dict[str, bool]:
        return service.admin_update_user(user, user_id, body.model_dump())

    @app.delete("/api/admin/users/{user_id}")
    def admin_delete(
        user_id: int, user: Annotated[User | None, Depends(current_user)]
    ) -> dict[str, bool]:
        return service.admin_delete_user(user, user_id)

    # ------------------------------------------------------------------ partidas
    @app.post("/api/games")
    def new_game(
        body: NewGame, request: Request, user: Annotated[User | None, Depends(current_user)]
    ) -> dict[str, Any]:
        action_limiter.check(client_ip(request))
        return service.new_game(user, body.model_dump())

    @app.post("/api/games/{game_id}/join")
    def join_game(
        game_id: str, body: JoinGame, user: Annotated[User | None, Depends(current_user)]
    ) -> dict[str, Any]:
        return service.join(user, game_id, body.invite, body.name)

    @app.post("/api/games/{game_id}/reclaim")
    def reclaim(game_id: str, user: Annotated[User, Depends(require_user)]) -> dict[str, Any]:
        return service.reclaim(user, game_id)

    @app.get("/api/games/{game_id}")
    def get_game(
        game_id: str, x_seat_token: Annotated[str | None, Header()] = None
    ) -> dict[str, Any]:
        return service.get_game(game_id, x_seat_token)

    @app.post("/api/games/{game_id}/action")
    def post_action(
        game_id: str,
        body: ActionRequest,
        request: Request,
        x_seat_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        action_limiter.check(client_ip(request))
        return service.action(game_id, x_seat_token, body.action)

    @app.post("/api/games/{game_id}/deal")
    def deal(game_id: str, x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        return service.deal(game_id, x_seat_token)

    @app.post("/api/games/{game_id}/tick")
    def tick(game_id: str, x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        return service.tick(game_id, x_seat_token)

    @app.post("/api/games/{game_id}/look")
    def look(
        game_id: str, body: LookRequest, x_seat_token: Annotated[str | None, Header()] = None
    ) -> dict[str, Any]:
        return service.look(game_id, x_seat_token, body.target)

    @app.post("/api/games/{game_id}/signal")
    def signal(
        game_id: str, body: SignalRequest, x_seat_token: Annotated[str | None, Header()] = None
    ) -> dict[str, Any]:
        return service.signal(game_id, x_seat_token, body.signal)

    @app.get("/api/games/{game_id}/help")
    def help_now(
        game_id: str, x_seat_token: Annotated[str | None, Header()] = None
    ) -> dict[str, Any]:
        return service.help(game_id, x_seat_token)

    @app.get("/api/games/{game_id}/analysis")
    def analysis(
        game_id: str, x_seat_token: Annotated[str | None, Header()] = None
    ) -> dict[str, Any]:
        return service.analysis(game_id, x_seat_token)

    @app.get("/api/games/{game_id}/replay")
    def replay(
        game_id: str,
        user: Annotated[User | None, Depends(current_user)],
        x_seat_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        return service.replay(game_id, user, x_seat_token)

    @app.get("/api/history")
    def history(user: Annotated[User, Depends(require_user)]) -> list[dict[str, Any]]:
        return service.history(user)

    # ------------------------------------------------------------------ estadísticas
    @app.get("/api/players/me/statistics")
    def my_statistics(user: Annotated[User, Depends(require_user)]) -> dict[str, Any]:
        return service.statistics(user)

    # ------------------------------------------------------------------ bots, arena y entrenamiento
    @app.get("/api/bots")
    def bots() -> list[dict[str, Any]]:
        return service.bots()

    @app.get("/api/scoreboard")
    def scoreboard() -> Any:
        return service.scoreboard()

    @app.post("/api/arena/watch")
    def watch(body: WatchRequest, request: Request) -> dict[str, Any]:
        action_limiter.check(client_ip(request))
        return service.watch(body.team_a, body.team_b, body.seed)

    @app.get("/api/training/scenarios")
    def scenarios() -> list[dict[str, Any]]:
        return service.scenarios()

    @app.post("/api/training/scenarios/{scenario_id}")
    def answer_scenario(scenario_id: str, body: ActionRequest) -> dict[str, Any]:
        return service.answer_scenario(scenario_id, body.action)

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


app: FastAPI | None = create_app() if os.environ.get("MUSST_NO_APP") != "1" else None
