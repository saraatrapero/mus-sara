"""Eventos de partida (event sourcing).

Cada evento tiene una visibilidad: ``public`` (todos), ``private`` (solo ``recipients``)
o ``system`` (solo motor y modo desarrollo).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Visibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    SYSTEM = "system"


class EventKind(str, Enum):
    GAME_STARTED = "GameStarted"
    DEALER_ASSIGNED = "DealerAssigned"
    DECK_SHUFFLED = "DeckShuffled"
    CARDS_DEALT = "CardsDealt"
    MUS_REQUESTED = "MusRequested"
    MUS_CUT = "MusCut"
    CARDS_DISCARDED = "CardsDiscarded"
    CARDS_RECEIVED = "CardsReceived"
    DECK_RESHUFFLED = "DeckReshuffled"
    LANCE_STARTED = "LanceStarted"
    PAIRS_DECLARED = "PairsDeclared"
    GAME_DECLARED = "GameDeclared"
    PASSED = "Passed"
    BET_PLACED = "BetPlaced"
    BET_RAISED = "BetRaised"
    ORDAGO_DECLARED = "OrdagoDeclared"
    BET_ACCEPTED = "BetAccepted"
    BET_REJECTED = "BetRejected"
    ORDAGO_ACCEPTED = "OrdagoAccepted"
    LANCE_RESOLVED = "LanceResolved"
    HANDS_REVEALED = "HandsRevealed"
    POINTS_AWARDED = "PointsAwarded"
    TEAM_IS_IN = "TeamIsIn"
    ROUND_FINISHED = "RoundFinished"
    GAME_FINISHED = "GameFinished"
    GAZE_CHANGED = "GazeChanged"
    SIGNAL_MADE = "SignalMade"
    SIGNAL_SEEN = "SignalSeen"


@dataclass(frozen=True)
class GameEvent:
    """Hecho inmutable ocurrido en la partida."""

    seq: int
    kind: EventKind
    round_no: int
    phase: str
    actor: int | None
    payload: dict[str, Any] = field(default_factory=dict)
    visibility: Visibility = Visibility.PUBLIC
    recipients: tuple[int, ...] = ()

    def visible_to(self, seat: int | None) -> bool:
        """¿Puede ``seat`` ver este evento? ``None`` = espectador."""
        if self.visibility is Visibility.PUBLIC:
            return True
        if self.visibility is Visibility.PRIVATE:
            return seat is not None and seat in self.recipients
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "kind": self.kind.value,
            "round": self.round_no,
            "phase": self.phase,
            "actor": self.actor,
            "payload": self.payload,
        }
