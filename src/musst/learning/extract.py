"""Extrae decisiones con contexto a partir del historial **público** de una partida.

Solo usa eventos públicos y las manos reveladas al final de cada jugada (FEM VII.9).
Nunca necesita el estado secreto del motor.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from musst.bots.toolkit import hand_strength
from musst.engine.cards import Card
from musst.learning.player_model import score_context

WEAK = 0.4
"""Por debajo de esta fuerza heurística, envidar se considera farol."""


@dataclass(frozen=True)
class Decision:
    """Una decisión observada de un asiento."""

    round_no: int
    seat: int
    lance: str
    kind: str  # mus | cut | pass | bet | raise | ordago | accept | reject
    responding: bool
    score_ctx: str
    strength: float | None  # fuerza de la mano revelada en ese lance (si se conoce)
    stake: int


def extract_decisions(history: Iterable[dict[str, Any]], target: int = 40) -> list[Decision]:
    events = list(history)
    hands: dict[int, dict[int, tuple[Card, ...]]] = {}
    for e in events:
        if e["kind"] == "HandsRevealed":
            hands[e["round"]] = {
                int(s): tuple(Card.parse(c) for c in cs) for s, cs in e["payload"]["hands"].items()
            }
    decisions: list[Decision] = []
    score = [0, 0]
    pending = False
    stake = 0
    for e in events:
        kind = e["kind"]
        payload = e["payload"]
        if kind == "PointsAwarded":
            score = list(payload["score"])
            continue
        if kind == "LanceStarted":
            pending = False
            stake = 0
            continue
        actor = e["actor"]
        if actor is None:
            continue
        mapping = {
            "MusRequested": "mus",
            "MusCut": "cut",
            "Passed": "pass",
            "BetPlaced": "bet",
            "BetRaised": "raise",
            "OrdagoDeclared": "ordago",
            "BetAccepted": "accept",
            "OrdagoAccepted": "accept",
            "BetRejected": "reject",
        }
        if kind not in mapping:
            continue
        action = mapping[kind]
        lance = payload.get("lance", "mus")
        team = actor % 2
        ctx = score_context(score[team], score[1 - team], target)
        strength = None
        round_hands = hands.get(e["round"])
        if round_hands and lance != "mus":
            strength = hand_strength(round_hands[actor], lance)
        decisions.append(Decision(e["round"], actor, lance, action, pending, ctx, strength, stake))
        if action in ("bet", "raise", "ordago"):
            pending = True
            stake = payload.get("total", payload.get("amount", stake))
        elif action == "accept" or (action == "reject" and payload.get("final", True)):
            pending = False
    return decisions
