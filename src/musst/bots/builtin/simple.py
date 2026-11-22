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
from musst.bots.toolkit import early_game, hand_strength, keep_heuristic_discard
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
        self.last_reason: dict[str, object] = {}

    def signal(self, observation: Observation) -> str | None:
        """Descuidado: hace una seña en cuanto alguien le mira, sea su compañero o un rival."""
        obs = observation
        if not obs.available_signals or obs.signals_seen.get(obs.seat):
            return None
        if any(g == obs.seat for g in obs.gazes) and self.rng.random() < 0.5:
            return self.rng.choice(list(obs.available_signals))
        return None

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
            self.last_reason = {"regla": "ya no se puede pedir mus"}
            return CutMusAction()
        hand = obs.hand
        good = (
            ev.total_points(hand) == 31
            or ev.pairs(hand).kind >= ev.PairsKind.MEDIAS
            or (hand_strength(hand, "grande") >= 0.65 and ev.pairs(hand).has_pairs)
        )
        self.last_reason = {
            "regla": "corta el mus: tiene 31, medias/duples o grande alta con pares"
            if good
            else "pide mus: su mano no es buena y prefiere cambiar cartas"
        }
        return CutMusAction() if good else MusAction()

    def _open(self, obs: Observation, s: float) -> Action:
        self.last_reason = {"fuerza": s}
        if s >= 0.97 and self.rng.random() < 0.3 and not early_game(obs):
            self.last_reason["regla"] = "con 97/100 o más se arriesga a la partida entera"
            return OrdagoAction()
        if s >= 0.75:
            self.last_reason["regla"] = (
                "con 75/100 o más envida 2" if s < 0.9 else "con 90/100 o más envida 4"
            )
            return BetAction(2 if s < 0.9 else 4)
        if self.rng.random() < self.bluff:
            self.last_reason["regla"] = "va de farol: envida con mano floja a ver si cuela"
            return BetAction(2)
        self.last_reason["regla"] = "por debajo de 75/100 no envida y pasa"
        return PassAction()

    def _respond(self, obs: Observation, s: float) -> Action:
        bet = obs.current_bet
        assert bet is not None
        types = obs.legal_types()
        accept: Action = AcceptAction() if "accept" in types else AcceptNoLoseAction()
        self.last_reason = {"fuerza": s}
        if bet.is_ordago:
            need = 0.95 if early_game(obs) else 0.85
            if s >= need and accept.type in types:
                self.last_reason["regla"] = f"ve el órdago porque supera {round(need * 100)}/100"
                return accept
            self.last_reason["regla"] = (
                f"no se juega la partida sin al menos {round(need * 100)}/100"
                + (" (y es pronto en la partida)" if early_game(obs) else "")
            )
            return RejectAction()
        if s >= 0.9 and "raise" in types:
            self.last_reason["regla"] = "con 90/100 o más sube el envite"
            return RaiseAction(2)
        if s >= 0.55 and accept.type in types:
            self.last_reason["regla"] = "con 55/100 o más quiere el envite"
            return accept
        self.last_reason["regla"] = "por debajo de 55/100 no quiere el envite"
        return RejectAction()
