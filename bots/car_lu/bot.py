"""car_lu: bot de Carmen Cuerva y Lucía Argüello.

Juega con simulación Monte Carlo sobre las cartas que no ve:

* **Mus**: corta con 31, duples, medias o una mano global fuerte.
* **Descarte**: prueba los 15 descartes posibles, simula qué cartas podrían entrar y se queda
  con el que deja mejor mano esperada.
* **Lances**: estima P(mi pareja gana el lance) repartiendo manos compatibles con lo que se
  ha declarado (pares sí/no, juego sí/no). Envida según esa probabilidad y solo acepta un
  envite cuando el valor esperado de querer supera lo que cuesta el "no quiero".
* **Lectura de la jugada**: cada mundo simulado pesa más si encaja con lo que han hecho los
  demás en esta mano (quien envida o quiere suele ir fuerte en ese lance; quien pasa, flojo).
* **Órdago**: solo con el lance prácticamente ganado, o al final de la partida cuando el rival
  está a punto de ganar y ya no hay nada que perder.
"""

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
from musst.bots.toolkit import (
    discard_options,
    estimate_lance_win,
    hand_strength,
    hand_value,
    keep_heuristic_discard,
    unseen_cards,
)
from musst.engine import evaluation as ev

SAMPLES = 400  # mundos simulados por decisión de lance (< 0,3 s)
DRAWS = 40  # robos simulados por cada descarte posible
LANCES = ("grande", "chica", "pares", "juego", "punto")
STRONG = {"BetPlaced", "BetRaised", "OrdagoDeclared", "BetAccepted", "OrdagoAccepted"}
WEAK = {"Passed", "BetRejected"}


class CarLuBot(Bot):
    name = "car_lu"
    author = "Carmen Cuerva y Lucía Argüello"
    version = "1.0"

    # Umbrales sobre P(ganar el lance), ajustados con partidas contra los bots del repositorio.
    MUS_CUT = 0.5  # valor global de mano a partir del cual se corta el mus
    P_BET = 0.62  # envido de 2
    P_BET_BIG = 0.82  # envido de 4
    BLUFF_P = 0.45  # farol posible a partir de esta probabilidad...
    BLUFF = 0.08  # ...con esta frecuencia
    P_RAISE = 0.85  # reenvite
    ACCEPT_MARGIN = 0.08  # margen sobre el umbral de valor esperado para querer
    ORDAGO_OPEN = 0.97
    ORDAGO_RAISE = 0.95
    ORDAGO_ACCEPT = 0.6
    SAMPLES = SAMPLES
    DISCARD_SIM = True  # descarte simulado (False = descarte clásico)
    READ_STRONG = 1.0  # cuánto pesa un envite ajeno como señal de fuerza
    READ_WEAK = 0.4  # cuánto pesa un paso o un "no quiero" como señal de debilidad

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(2026 if seed is None else seed)

    # ------------------------------------------------------------------ entrada
    def decide(self, observation: Observation) -> Action:
        obs = observation
        try:
            action = self._decide(obs)
        except Exception:  # nunca perder una partida por un fallo propio
            action = None
        if action is None or action.type not in obs.legal_types():
            return self._safe(obs)
        return action

    def _decide(self, obs: Observation) -> Action | None:
        legal = obs.legal_types()
        if "cut" in legal or "mus" in legal:
            return self._mus(obs)
        if "discard" in legal:
            return self._discard(obs)
        if obs.phase not in LANCES:
            return None
        weight = self._reader(obs)
        p = estimate_lance_win(obs, obs.phase, self.rng, samples=self.SAMPLES, weight=weight).p_win
        if "pass" in legal:
            return self._lead(obs, p)
        return self._respond(obs, p)

    def _reader(self, obs: Observation):
        """Peso de cada mundo simulado según lo que han hecho los demás en esta jugada.

        Quien envida, sube o quiere en un lance suele ir fuerte en él; quien pasa o no quiere,
        flojo. Los mundos en los que las manos encajan con esas acciones cuentan más.
        """
        reads: list[tuple[int, str, bool]] = []
        for event in obs.history:
            if event.get("round") != obs.round_no or event.get("phase") not in LANCES:
                continue
            actor = event.get("actor")
            if actor is None or actor == obs.seat:
                continue
            if event["kind"] in STRONG:
                reads.append((actor, event["phase"], True))
            elif event["kind"] in WEAK:
                reads.append((actor, event["phase"], False))
        if not reads:
            return None
        hi, lo = self.READ_STRONG, self.READ_WEAK

        def weight(world) -> float:
            w = 1.0
            for seat, lance, strong in reads:
                x = hand_strength(world[seat], lance)
                w *= (1.0 - hi / 2) + hi * x if strong else 1.0 + lo / 2 - lo * x
            return max(w, 1e-6)

        return weight

    def _safe(self, obs: Observation) -> Action:
        legal = obs.legal_types()
        for kind, action in (
            ("pass", PassAction()),
            ("reject", RejectAction()),
            ("cut", CutMusAction()),
        ):
            if kind in legal:
                return action
        if "discard" in legal:
            return DiscardAction(keep_heuristic_discard(obs.hand))
        return obs.legal_actions[0].default()

    # ------------------------------------------------------------------ mus y descarte
    def _mus(self, obs: Observation) -> Action:
        if "mus" not in obs.legal_types():
            return CutMusAction()
        hand = obs.hand
        pairs = ev.pairs(hand).kind
        strong = (
            ev.total_points(hand) == 31
            or pairs >= ev.PairsKind.MEDIAS
            or hand_value(hand) >= self.MUS_CUT
            or (ev.has_juego(hand) and pairs >= ev.PairsKind.PAR)
        )
        return CutMusAction() if strong else MusAction()

    def _discard(self, obs: Observation) -> Action:
        spec = obs.spec("discard")
        if not self.DISCARD_SIM:
            return DiscardAction(keep_heuristic_discard(obs.hand))
        lo = (spec.min_amount if spec else None) or 1
        hi = (spec.max_amount if spec else None) or 4
        pool = unseen_cards(obs)
        hand = list(obs.hand)
        best: tuple[float, tuple] = (-1.0, keep_heuristic_discard(obs.hand))
        for option in discard_options(hand, lo):
            if len(option) > hi or len(option) > len(pool):
                continue
            kept = [c for c in hand if c not in option]
            rng = random.Random(len(option) * 7919 + sum(c.rank for c in option))
            total = 0.0
            for _ in range(DRAWS):
                total += hand_value(kept + rng.sample(pool, len(option)))
            score = total / DRAWS
            if score > best[0]:
                best = (score, option)
        return DiscardAction(tuple(best[1]))

    # ------------------------------------------------------------------ lances
    def _pressure(self, obs: Observation) -> tuple[int, int]:
        """Tantos que nos faltan a nosotras y al rival para ganar."""
        mine = obs.score[obs.team]
        theirs = obs.score[1 - obs.team]
        return obs.target - mine, obs.target - theirs

    def _lead(self, obs: Observation, p: float) -> Action:
        legal = obs.legal_types()
        _, they_need = self._pressure(obs)
        if "ordago" in legal and (p >= self.ORDAGO_OPEN or (they_need <= 5 and p >= 0.7)):
            return OrdagoAction()
        spec = obs.spec("bet")
        if spec is not None:
            lo = spec.min_amount or 2
            hi = spec.max_amount or lo
            if p >= self.P_BET_BIG:
                return BetAction(max(lo, min(hi, 4)))
            if p >= self.P_BET:
                return BetAction(lo)
            if p >= self.BLUFF_P and self.rng.random() < self.BLUFF:  # algún farol suelto
                return BetAction(lo)
        return PassAction()

    def _respond(self, obs: Observation, p: float) -> Action:
        bet = obs.current_bet
        legal = obs.legal_types()
        if bet is None:
            return None  # type: ignore[return-value]
        accept: Action = AcceptAction() if "accept" in legal else AcceptNoLoseAction()
        can_accept = accept.type in legal
        _, they_need = self._pressure(obs)

        if bet.is_ordago:
            # Si el rival gana igual en esta mano, aceptar no cuesta nada.
            threshold = 0.42 if they_need <= 6 else self.ORDAGO_ACCEPT
            return accept if can_accept and p >= threshold else RejectAction()

        if "ordago" in legal and p >= self.ORDAGO_RAISE:
            return OrdagoAction()
        raise_spec = obs.spec("raise")
        if raise_spec is not None and p >= self.P_RAISE:
            lo = raise_spec.min_amount or 2
            hi = raise_spec.max_amount or lo
            return RaiseAction(max(lo, min(hi, 2)))
        # Querer: ganamos stake con prob. p o lo perdemos; no querer: el rival se lleva previous.
        stake = max(bet.stake, 1)
        needed = (stake - bet.previous) / (2 * stake) + self.ACCEPT_MARGIN
        if can_accept and p >= needed:
            return accept
        return RejectAction()
