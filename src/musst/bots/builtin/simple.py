"""Bots de referencia: ``RandomBot`` y ``SimpleBot`` (nivel Sencillo)."""

from __future__ import annotations

import random

from musst.bots.api import (
    AcceptAction,
    AcceptNoLoseAction,
    Action,
    BetAction,
    Bot,
    CutMusAction,
    DiscardAction,
    MusAction,
    Observation,
    OrdagoAction,
    PassAction,
    RaiseAction,
    RejectAction,
)
from musst.bots.toolkit import hand_strength, keep_heuristic_discard
from musst.engine import evaluation as ev


class RandomBot(Bot):
    """Elige una acción legal al azar. Sirve de línea base y para tests."""

    name = "random"
    author = "MUS.ST"

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    def decide(self, observation: Observation) -> Action:
        spec = self.rng.choice(observation.legal_actions)
        if spec.type == "discard":
            n = self.rng.randint(spec.min_amount or 1, spec.max_amount or 4)
            return DiscardAction(tuple(self.rng.sample(list(observation.hand), n)))
        if spec.type in ("bet", "raise"):
            amount = self.rng.randint(spec.min_amount or 2, min(spec.max_amount or 2, 8))
            return BetAction(amount) if spec.type == "bet" else RaiseAction(amount)
        return spec.default()


class SimpleBot(Bot):
    """Nivel SENCILLO: heurísticas de fuerza de mano, sin modelo del rival.

    Comete errores razonables: con probabilidad ``noise`` juega una alternativa cercana.
    """

    name = "sencillo"
    author = "MUS.ST"

    def __init__(self, seed: int | None = None, noise: float = 0.15, bluff: float = 0.05) -> None:
        self.rng = random.Random(seed)
        self.noise = noise
        self.bluff = bluff

    def decide(self, observation: Observation) -> Action:
        obs = observation
        types = obs.legal_types()
        if "mus" in types or "cut" in types:
            return self._mus(obs)
        if "discard" in types:
            return DiscardAction(keep_heuristic_discard(obs.hand))
        strength = hand_strength(obs.hand, obs.phase)
        if self.rng.random() < self.noise:
            strength = min(1.0, max(0.0, strength + self.rng.uniform(-0.25, 0.25)))
        if "pass" in types:
            return self._open(obs, strength)
        return self._respond(obs, strength)

    def _mus(self, obs: Observation) -> Action:
        if "mus" not in obs.legal_types():
            return CutMusAction()
        hand = obs.hand
        good = (
            ev.total_points(hand) == 31
            or ev.pairs(hand).kind >= ev.PairsKind.MEDIAS
            or (hand_strength(hand, "grande") >= 0.65 and ev.pairs(hand).has_pairs)
        )
        return CutMusAction() if good else MusAction()

    def _open(self, obs: Observation, s: float) -> Action:
        if s >= 0.97 and self.rng.random() < 0.3:
            return OrdagoAction()
        if s >= 0.75:
            return BetAction(2 if s < 0.9 else 4)
        if self.rng.random() < self.bluff:
            return BetAction(2)
        return PassAction()

    def _respond(self, obs: Observation, s: float) -> Action:
        bet = obs.current_bet
        assert bet is not None
        types = obs.legal_types()
        accept: Action = AcceptAction() if "accept" in types else AcceptNoLoseAction()
        if bet.is_ordago:
            return accept if s >= 0.85 and accept.type in types else RejectAction()
        if s >= 0.9 and "raise" in types:
            return RaiseAction(2)
        if s >= 0.55 and accept.type in types:
            return accept
        return RejectAction()
