"""GameRunner: juega partidas completas entre bots sin interfaz (Req 1.1).

Un fallo de bot (excepción, acción ilegal o timeout) nunca rompe el proceso:

* ``mode="tournament"``: la pareja del bot que falla pierde la partida (Req 4.1).
* ``mode="casual"``: se registra el fallo y el asiento juega con ``FallbackBot``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from musst.bots.api import Bot, GameEndInfo, GameStartInfo
from musst.engine.actions import (
    Action,
    CutMusAction,
    DiscardAction,
    PassAction,
    RejectAction,
)
from musst.engine.config import RulesConfig
from musst.engine.events import GameEvent
from musst.engine.game import GameResult, IllegalAction, MusGame, partner_of, team_of
from musst.engine.observation import Observation, build_observation

log = logging.getLogger("musst.public.runner")


class BotFailure(Exception):
    """Fallo de un bot: ``kind`` ∈ {"exception", "illegal", "timeout", "crash"}."""

    def __init__(self, kind: str, detail: str = "") -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


@dataclass
class SeatError:
    seat: int
    kind: str
    detail: str
    round_no: int


@dataclass
class MatchResult:
    result: GameResult
    seed: int
    events: list[GameEvent]
    errors: list[SeatError] = field(default_factory=list)
    decision_times: dict[int, list[float]] = field(default_factory=dict)
    actions: list[tuple[int, Action]] = field(default_factory=list)


class FallbackBot(Bot):
    """Jugada legal más conservadora. Sustituye a un bot que falla fuera del torneo."""

    name = "fallback"

    def decide(self, observation: Observation) -> Action:
        types = observation.legal_types()
        if "cut" in types:
            return CutMusAction()
        if "discard" in types:
            return DiscardAction((observation.hand[0],))
        if "pass" in types:
            return PassAction()
        if "reject" in types:
            return RejectAction()
        return observation.legal_actions[0].default()


def play_game(
    bots: Sequence[Bot],
    seed: int | None = None,
    config: RulesConfig | None = None,
    mode: Literal["casual", "tournament"] = "casual",
    time_limit_s: float = 5.0,
    names: Sequence[str] | None = None,
    contexts: Sequence[dict[str, object]] | None = None,
    on_event: Callable[[GameEvent], None] | None = None,
    max_actions: int = 20000,
) -> MatchResult:
    """Juega una partida completa. ``bots[i]`` ocupa el asiento ``i``.

    Pareja 0 = asientos 0 y 2; pareja 1 = asientos 1 y 3.
    """
    if len(bots) != 4:
        raise ValueError("Se necesitan exactamente 4 bots (uno por asiento)")
    game = MusGame(seed=seed, config=config)
    player_names = (
        tuple(names) if names else tuple(getattr(b, "name", f"bot{i}") for i, b in enumerate(bots))
    )
    seats: list[Bot] = list(bots)
    match = MatchResult(game.result or GameResult(0, (0, 0), "", 0), game.seed, game.events)
    match.decision_times = {i: [] for i in range(4)}

    for i, bot in enumerate(seats):
        info = GameStartInfo(
            seat=i,
            partner=partner_of(i),
            team=team_of(i),
            target=game.config.target_points,
            player_names=(player_names[0], player_names[1], player_names[2], player_names[3]),
            context=dict(contexts[i]) if contexts else {},
        )
        try:
            bot.on_game_start(info)
        except Exception as exc:
            if _handle_failure(game, match, seats, i, BotFailure("exception", repr(exc)), mode):
                break

    seen = len(game.events)
    steps = 0
    while not game.finished:
        steps += 1
        if steps > max_actions:
            game.forfeit(0, "action_limit")  # salvaguarda: nunca debería ocurrir
            break
        seat = game.turn
        assert seat is not None
        obs = build_observation(game, seat)
        start = time.perf_counter()
        try:
            action = seats[seat].decide(obs)
            elapsed = time.perf_counter() - start
            match.decision_times[seat].append(elapsed)
            if elapsed > time_limit_s:
                raise BotFailure("timeout", f"{elapsed:.2f}s > {time_limit_s}s")
            try:
                game.apply(seat, action)
            except IllegalAction as exc:
                raise BotFailure("illegal", f"{action!r}: {exc}") from exc
            except Exception as exc:  # acción malformada (tipo incorrecto, etc.)
                raise BotFailure("illegal", f"{action!r}: {exc!r}") from exc
            match.actions.append((seat, action))
        except BotFailure as failure:
            if _handle_failure(game, match, seats, seat, failure, mode):
                break
        except Exception as exc:
            if _handle_failure(game, match, seats, seat, BotFailure("exception", repr(exc)), mode):
                break
        if on_event is not None:
            for event in game.events[seen:]:
                on_event(event)
        seen = len(game.events)

    assert game.result is not None
    match.result = game.result
    history = tuple(e.to_dict() for e in game.events if e.visible_to(None))
    end = GameEndInfo(game.result.winner, game.result.score, game.result.reason, history)
    for bot in seats:
        try:
            bot.on_game_end(end)
        except Exception as exc:  # el aprendizaje de un bot no puede romper la partida
            log.warning("on_game_end falló en %s: %r", getattr(bot, "name", "?"), exc)
    return match


def _handle_failure(
    game: MusGame,
    match: MatchResult,
    seats: list[Bot],
    seat: int,
    failure: BotFailure,
    mode: str,
) -> bool:
    """Registra el fallo. Devuelve ``True`` si la partida termina."""
    match.errors.append(SeatError(seat, failure.kind, failure.detail[:500], game.round_no))
    log.warning("Bot del asiento %s falló (%s)", seat, failure.kind)
    if mode == "tournament":
        game.forfeit(team_of(seat), f"bot_failure:{failure.kind}")
        return True
    seats[seat] = FallbackBot()
    return False
