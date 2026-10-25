"""Jugadores sintéticos con parámetros conocidos, para validar el aprendizaje.

Permiten comprobar de forma controlada que el PlayerModel detecta, por ejemplo, un
``bluff_frequency`` alto o una ``risk_tolerance`` baja, y los cambios de estrategia.
"""

from __future__ import annotations

import random

from musst.bots.api import (
    AcceptAction,
    Action,
    BetAction,
    Bot,
    DiscardAction,
    Observation,
    PassAction,
    RejectAction,
)
from musst.bots.builtin.simple import SimpleBot
from musst.bots.toolkit import hand_strength, keep_heuristic_discard


class SyntheticPlayer(Bot):
    """Jugador paramétrico.

    * ``bluff``: probabilidad de envidar con mano débil (fuerza < 0.4).
    * ``value_threshold``: fuerza a partir de la cual envida "de verdad".
    * ``risk_tolerance``: probabilidad de aceptar un envite con mano débil.
    * ``shift_after``: tras N decisiones de envite, pasa a ``shifted_bluff`` (cambio de estrategia).
    """

    name = "sintetico"

    def __init__(
        self,
        bluff: float = 0.1,
        value_threshold: float = 0.7,
        risk_tolerance: float = 0.3,
        seed: int | None = None,
        shift_after: int | None = None,
        shifted_bluff: float = 0.9,
    ) -> None:
        self.bluff = bluff
        self.value_threshold = value_threshold
        self.risk_tolerance = risk_tolerance
        self.rng = random.Random(seed)
        self.shift_after = shift_after
        self.shifted_bluff = shifted_bluff
        self.decisions = 0
        self._mus = SimpleBot(seed, noise=0)

    def decide(self, observation: Observation) -> Action:
        types = observation.legal_types()
        if "mus" in types or "cut" in types:
            return self._mus._mus(observation)
        if "discard" in types:
            return DiscardAction(keep_heuristic_discard(observation.hand))
        strength = hand_strength(observation.hand, observation.phase)
        bluff = self.bluff
        if self.shift_after is not None and self.decisions >= self.shift_after:
            bluff = self.shifted_bluff
        if "pass" in types:
            self.decisions += 1
            if strength >= self.value_threshold:
                return BetAction(2)
            if strength < 0.4 and self.rng.random() < bluff:
                return BetAction(2)
            return PassAction()
        if "accept" in types:
            if strength >= 0.6:
                return AcceptAction()
            if strength < 0.5 and self.rng.random() < self.risk_tolerance:
                return AcceptAction()
        return RejectAction()
