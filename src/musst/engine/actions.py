"""Acciones tipadas que un jugador puede proponer al motor.

Una acción es una *intención*. Solo el :class:`~musst.engine.rules.RulesEngine` decide si es legal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from musst.engine.cards import Card


@dataclass(frozen=True)
class MusAction:
    """Dar mus (pedir descarte)."""

    type = "mus"


@dataclass(frozen=True)
class CutMusAction:
    """Cortar el mus ("no hay mus")."""

    type = "cut"


@dataclass(frozen=True)
class DiscardAction:
    """Descartar las cartas indicadas (de ``min_discard`` a 4)."""

    cards: tuple[Card, ...]
    type = "discard"


@dataclass(frozen=True)
class PassAction:
    """Paso: no envidar en el turno."""

    type = "pass"


@dataclass(frozen=True)
class BetAction:
    """Envido de ``amount`` tantos (envido = 2)."""

    amount: int
    type = "bet"


@dataclass(frozen=True)
class RaiseAction:
    """Reenvite: subir ``amount`` tantos sobre la apuesta pendiente."""

    amount: int
    type = "raise"


@dataclass(frozen=True)
class AcceptAction:
    """Quiero."""

    type = "accept"


@dataclass(frozen=True)
class AcceptNoLoseAction:
    """ "Quiero y no pierdo" (FEM VI.9-10): postre con 33 acepta un órdago a juego."""

    type = "accept_no_lose"


@dataclass(frozen=True)
class RejectAction:
    """No quiero."""

    type = "reject"


@dataclass(frozen=True)
class OrdagoAction:
    """Órdago: apostar el juego completo."""

    type = "ordago"


Action = (
    MusAction
    | CutMusAction
    | DiscardAction
    | PassAction
    | BetAction
    | RaiseAction
    | AcceptAction
    | AcceptNoLoseAction
    | RejectAction
    | OrdagoAction
)

_SIMPLE: dict[str, Action] = {
    "mus": MusAction(),
    "cut": CutMusAction(),
    "pass": PassAction(),
    "accept": AcceptAction(),
    "accept_no_lose": AcceptNoLoseAction(),
    "reject": RejectAction(),
    "ordago": OrdagoAction(),
}


def action_to_dict(action: Action) -> dict[str, Any]:
    """Serializa una acción a JSON con discriminador ``type``."""
    data: dict[str, Any] = {"type": action.type}
    if isinstance(action, DiscardAction):
        data["cards"] = [c.code for c in action.cards]
    elif isinstance(action, BetAction | RaiseAction):
        data["amount"] = action.amount
    return data


def action_from_dict(data: dict[str, Any]) -> Action:
    """Deserializa y valida la *forma* (no la legalidad) de una acción."""
    if not isinstance(data, dict) or "type" not in data:
        raise ValueError("La acción debe ser un objeto con campo 'type'")
    kind = data["type"]
    if kind in _SIMPLE:
        return _SIMPLE[kind]
    if kind == "discard":
        cards = data.get("cards")
        if not isinstance(cards, list) or not all(isinstance(c, str) for c in cards):
            raise ValueError("'cards' debe ser una lista de códigos de naipe")
        return DiscardAction(tuple(Card.parse(c) for c in cards))
    if kind in ("bet", "raise"):
        amount = data.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise ValueError("'amount' debe ser un entero")
        return BetAction(amount) if kind == "bet" else RaiseAction(amount)
    raise ValueError(f"Tipo de acción desconocido: {kind!r}")


@dataclass(frozen=True)
class ActionSpec:
    """Descripción de una familia de acciones legales.

    Para ``bet``/``raise`` indica el rango de cantidades; para ``discard`` el número de cartas.
    """

    type: str
    min_amount: int | None = None
    max_amount: int | None = None

    def default(self) -> Action:
        """Una acción concreta válida de esta familia (para bots sencillos).

        ``discard`` no tiene acción por defecto porque depende de la mano.
        """
        if self.type in _SIMPLE:
            return _SIMPLE[self.type]
        if self.type == "bet":
            return BetAction(self.min_amount or 2)
        if self.type == "raise":
            return RaiseAction(self.min_amount or 2)
        raise ValueError("discard requiere elegir cartas")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": self.type}
        if self.min_amount is not None:
            data["min"] = self.min_amount
            data["max"] = self.max_amount
        return data
