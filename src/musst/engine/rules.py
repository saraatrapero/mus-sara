"""RulesEngine y GameEngine: fachada funcional sobre :class:`MusGame`.

``GameEngine.apply`` es puro: no modifica el estado recibido y devuelve uno nuevo.
"""

from __future__ import annotations

from musst.engine.actions import Action, ActionSpec
from musst.engine.config import RulesConfig
from musst.engine.events import GameEvent
from musst.engine.game import IllegalAction, MusGame


class RulesEngine:
    """Única autoridad sobre la legalidad de una acción."""

    @staticmethod
    def legal_actions(state: MusGame, seat: int) -> list[ActionSpec]:
        return state.legal_specs(seat)

    @staticmethod
    def validate(state: MusGame, seat: int, action: Action) -> str | None:
        return state.validate(seat, action)

    @staticmethod
    def is_legal(state: MusGame, seat: int, action: Action) -> bool:
        return state.validate(seat, action) is None


class GameEngine:
    """Transiciones puras: ``(estado, acción) -> (estado', eventos)``."""

    def __init__(self, config: RulesConfig | None = None) -> None:
        self.config = config or RulesConfig()

    def new_game(self, seed: int) -> tuple[MusGame, list[GameEvent]]:
        game = MusGame(seed=seed, config=self.config)
        return game, list(game.events)

    @staticmethod
    def apply(state: MusGame, seat: int, action: Action) -> tuple[MusGame, list[GameEvent]]:
        reason = state.validate(seat, action)
        if reason is not None:
            raise IllegalAction(reason)
        new_state = state.clone()
        events = new_state.apply(seat, action)
        return new_state, events
