"""API pública para escribir bots de Mus.

Un bot externo **solo** necesita importar este módulo::

    from musst.bots.api import Bot, Observation, Action, PassAction

    class MiBot(Bot):
        name = "mi_bot"
        def decide(self, observation: Observation) -> Action:
            return observation.legal_actions[0].default()

El bot controla un asiento. Recibe una :class:`Observation` (nunca el estado del motor) y
devuelve una :class:`Action`. El motor vuelve a validar todas las acciones.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from musst.engine.actions import (
    AcceptAction,
    AcceptNoLoseAction,
    Action,
    ActionSpec,
    BetAction,
    CutMusAction,
    DiscardAction,
    MusAction,
    OrdagoAction,
    PassAction,
    RaiseAction,
    RejectAction,
)
from musst.engine.cards import Card, Suit
from musst.engine.observation import BetView, Observation

__all__ = [
    "AcceptAction",
    "AcceptNoLoseAction",
    "Action",
    "ActionSpec",
    "BetAction",
    "BetView",
    "Bot",
    "Card",
    "CutMusAction",
    "DiscardAction",
    "GameEndInfo",
    "GameStartInfo",
    "MusAction",
    "Observation",
    "OrdagoAction",
    "PassAction",
    "RaiseAction",
    "RejectAction",
    "Suit",
]


@dataclass(frozen=True)
class GameStartInfo:
    """Información pública al empezar una partida."""

    seat: int
    partner: int
    team: int
    target: int
    player_names: tuple[str, str, str, str]
    context: dict[str, Any] = field(default_factory=dict)
    """Datos opcionales del servidor, p. ej. perfiles históricos públicos de los rivales."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "partner": self.partner,
            "team": self.team,
            "target": self.target,
            "player_names": list(self.player_names),
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameStartInfo:
        names = data["player_names"]
        return cls(
            data["seat"],
            data["partner"],
            data["team"],
            data["target"],
            (names[0], names[1], names[2], names[3]),
            data.get("context", {}),
        )


@dataclass(frozen=True)
class GameEndInfo:
    """Resultado final. ``history`` incluye las manos reveladas de cada jugada."""

    winner: int
    score: tuple[int, int]
    reason: str
    history: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner": self.winner,
            "score": list(self.score),
            "reason": self.reason,
            "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameEndInfo:
        score = data["score"]
        return cls(data["winner"], (score[0], score[1]), data["reason"], tuple(data["history"]))


class Bot(ABC):
    """Jugador autónomo de Mus."""

    name: str = "unnamed"
    author: str = ""
    version: str = "0.1"

    def on_game_start(self, info: GameStartInfo) -> None:  # noqa: B027
        """Opcional: se llama una vez al empezar la partida."""

    @abstractmethod
    def decide(self, observation: Observation) -> Action:
        """Devuelve una acción de ``observation.legal_actions``."""

    def on_game_end(self, info: GameEndInfo) -> None:  # noqa: B027
        """Opcional: se llama al terminar. Útil para aprender."""
