"""car_lu: bot de Carmen Cuerva y Lucía Argüello.

Juega con simulación Monte Carlo sobre las cartas que no ve y decide pensando en ganar la
partida entera, no solo el lance:

* **Mus**: sitúa su mano en el percentil de una muestra de manos aleatorias y corta a partir
  de un umbral que se ajusta según la posición (mano o postre), quién ha pedido mus antes y el
  marcador.
* **Descarte**: prueba los 15 descartes posibles, simula qué cartas podrían entrar y se queda
  con el que deja mejor mano esperada.
* **Mundos simulados**: reparte manos a los otros tres compatibles con lo declarado (pares
  sí/no, juego sí/no) y pesa cada reparto según encaje con lo que ha hecho cada uno en esta
  mano: quien envida o quiere suele ir fuerte en ese lance (peso ``(0,05 + fuerza)^5``) y quien
  pasa, flojo (peso ``1,05 - fuerza``). Con esta lectura, la probabilidad estimada coincide con
  la frecuencia real con la que se gana el lance.
* **Valor de la partida**: en cada mundo calcula quién gana el lance y cuántos tantos de
  jugada cobraría cada pareja (pares, juego, punto). Con eso compara la probabilidad de ganar
  la partida si quiere y si no quiere; recuerda que, con un "no quiero" en pares, juego o
  punto, el rival cobra además sus jugadas.
* **Dejar hablar al compañero**: si el compañero todavía tiene que contestar al envite, solo
  quiere con lo que gana con su propia mano.
* **Envites**: envida desde una probabilidad de ganar el lance y más cuanto más clara es; a
  veces pasa con una mano muy buena para cazar el envite del rival y va de farol, sobre todo
  si habla el último y todos han pasado.
* **Órdago**: no lo echa por iniciativa propia (en las pruebas restaba); acepta el del rival
  solo si eso mejora su probabilidad de ganar la partida frente a no quererlo.
"""

from __future__ import annotations

import bisect
import math
import random
from collections.abc import Callable, Sequence

from musst.bots.api import (
    AcceptAction,
    AcceptNoLoseAction,
    Action,
    BetAction,
    Bot,
    Card,
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
    hand_strength,
    hand_value,
    keep_heuristic_discard,
    sample_world,
    speaking_order,
    unseen_cards,
)
from musst.engine import evaluation as ev
from musst.engine.cards import full_deck
from musst.engine.config import RulesConfig

LANCES = ("grande", "chica", "pares", "juego", "punto")
STRONG = {"BetPlaced", "BetRaised", "OrdagoDeclared", "BetAccepted", "OrdagoAccepted"}
WEAK = {"Passed", "BetRejected"}
RULES = RulesConfig()

World = dict[int, tuple[Card, ...]]


class _Table:
    """Lo que el bot sabe del lance en curso, calculado sobre mundos simulados."""

    def __init__(self, obs: Observation, worlds: list[tuple[World, float]]) -> None:
        self.obs = obs
        lance = obs.phase
        me, partner = obs.seat, obs.partner
        order = speaking_order(obs.mano)
        total = sum(w for _, w in worlds) or 1.0
        # Por mundo: (peso, gana mi pareja, gano yo solo, jugadas mías, jugadas del rival)
        self.rows: list[tuple[float, bool, bool, float, float]] = []
        for world, w in worlds:
            winner = ev.lance_winner(lance, world, order)
            alone = {s: h for s, h in world.items() if s != partner}
            winner_alone = ev.lance_winner(lance, alone, [s for s in order if s != partner])
            ours = _play_points(lance, world[me], world[partner])
            rivals = _play_points(lance, world[(me + 1) % 4], world[(me + 3) % 4])
            self.rows.append(
                (
                    w / total,
                    winner is not None and winner % 2 == obs.team,
                    winner_alone is not None and winner_alone % 2 == obs.team,
                    ours,
                    rivals,
                )
            )
        self.p = sum(w for w, win, _, _, _ in self.rows if win)
        self.p_alone = sum(w for w, _, win, _, _ in self.rows if win)
        self.rival_bonus = sum(w * r for w, _, _, _, r in self.rows)
        self.mine = obs.score[obs.team]
        self.theirs = obs.score[1 - obs.team]
        self.target = obs.target

    def vaca(self, plus_mine: float, plus_theirs: float) -> float:
        """Probabilidad aproximada de ganar la partida si cada pareja suma esos tantos."""
        mine, theirs = self.mine + plus_mine, self.theirs + plus_theirs
        if mine >= self.target:
            return 1.0
        if theirs >= self.target:
            return 0.0
        need_mine, need_theirs = self.target - mine, self.target - theirs
        x = (need_theirs - need_mine) / (9.0 * math.sqrt((need_mine + need_theirs) / 12 + 1))
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def accepted(self, stake: float, alone: bool) -> float:
        """Probabilidad de ganar la partida si se juega una apuesta de ``stake`` tantos."""
        value = 0.0
        for w, win, win_alone, ours, rivals in self.rows:
            won = win_alone if alone else win
            value += w * (self.vaca(stake + ours, 0) if won else self.vaca(0, stake + rivals))
        return value

    def rejected(self, deje: float) -> float:
        """Probabilidad de ganar la partida si no quiero: el rival cobra el deje y sus jugadas."""
        return self.vaca(0, deje + self.rival_bonus)


def _play_points(lance: str, a: Sequence[Card], b: Sequence[Card]) -> float:
    if lance in ("pares", "juego", "punto"):
        return float(ev.play_points(lance, (a, b), RULES))
    return 0.0


class CarLuBot(Bot):
    name = "car_lu"
    author = "Carmen Cuerva y Lucía Argüello"
    version = "2.0"

    SAMPLES = 300  # mundos simulados por decisión de lance
    DRAWS = 40  # robos simulados por cada descarte posible
    CUT = 0.62  # percentil de mano a partir del cual se corta el mus
    P_BET = 0.64  # probabilidad de ganar el lance para envidar
    P_RAISE = 0.82  # ... para reenvidar
    SLOWPLAY = 0.25  # con mano muy buena y un rival detrás, a veces se pasa para querer
    BLUFF = 0.07  # frecuencia base de farol
    # Echar órdagos por iniciativa propia restaba 3-4 puntos de porcentaje en las pruebas:
    # el bot no lanza órdagos, pero decide si acepta los del rival pensando en la partida.
    ORDAGO_OWN = False
    ORDAGO = 0.95  # (si ORDAGO_OWN) probabilidad para echar órdago con la partida igualada...
    ORDAGO_DESPERATE = 0.9  # ...y cuánto baja el umbral cuando la partida va mal
    READ_STRONG = 5.0  # cuánto pesa un envite ajeno como señal de fuerza (exponente)
    READ_WEAK = 1.0  # cuánto pesa un paso o un "no quiero" como señal de debilidad (exponente)
    LEAVE_TO_PARTNER = True

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(2026 if seed is None else seed)
        self._percentiles: list[float] | None = None

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
        table = _Table(obs, self._worlds(obs))
        if "pass" in legal:
            return self._lead(obs, table)
        return self._respond(obs, table)

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

    # ------------------------------------------------------------------ mundos simulados
    def _worlds(self, obs: Observation) -> list[tuple[World, float]]:
        weight = self._reader(obs)
        worlds = []
        for _ in range(self.SAMPLES):
            world = sample_world(obs, self.rng)
            worlds.append((world, 1.0 if weight is None else weight(world)))
        return worlds

    def _reader(self, obs: Observation) -> Callable[[World], float] | None:
        """Peso de cada mundo según lo que han hecho los demás en esta mano."""
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

        def weight(world: World) -> float:
            w = 1.0
            for seat, lance, strong in reads:
                x = hand_strength(world[seat], lance)
                w *= (0.05 + x) ** hi if strong else (1.05 - x) ** lo
            return max(w, 1e-6)

        return weight

    # ------------------------------------------------------------------ mus y descarte
    def _percentile(self, hand: Sequence[Card]) -> float:
        if self._percentiles is None:
            rng = random.Random(7)
            deck = full_deck()
            self._percentiles = sorted(hand_value(rng.sample(deck, 4)) for _ in range(3000))
        values = self._percentiles
        return bisect.bisect_left(values, hand_value(hand)) / len(values)

    def _mus(self, obs: Observation) -> Action:
        if "mus" not in obs.legal_types():
            return CutMusAction()
        if ev.total_points(obs.hand) == 31:
            return CutMusAction()
        threshold = self.CUT
        if obs.seat == obs.mano:
            threshold -= 0.03  # siendo mano gano los empates
        for event in obs.history:
            if event.get("round") != obs.round_no or event["kind"] != "MusRequested":
                continue
            if event.get("actor") == obs.partner:
                threshold += 0.03  # mi compañero no lleva gran cosa
            elif event.get("actor") in obs.opponents:
                threshold -= 0.02  # los rivales tampoco
        if obs.score[1 - obs.team] >= obs.target - 10:
            threshold -= 0.04  # que el rival no mejore su mano al final
        return CutMusAction() if self._percentile(obs.hand) >= threshold else MusAction()

    def _discard(self, obs: Observation) -> Action:
        spec = obs.spec("discard")
        lo = (spec.min_amount if spec else None) or 1
        hi = (spec.max_amount if spec else None) or 4
        pool = unseen_cards(obs)
        hand = list(obs.hand)
        best: tuple[float, int, tuple[Card, ...]] = (-1.0, 0, keep_heuristic_discard(obs.hand))
        for option in discard_options(hand, lo):
            if len(option) > hi or len(option) > len(pool):
                continue
            kept = [c for c in hand if c not in option]
            rng = random.Random(len(option) * 7919 + sum(c.rank for c in option))
            score = sum(hand_value(kept + rng.sample(pool, len(option))) for _ in range(self.DRAWS))
            candidate = (score / self.DRAWS, -len(option), tuple(option))
            if candidate[:2] > best[:2]:
                best = candidate
        return DiscardAction(best[2])

    # ------------------------------------------------------------------ lances
    def _ordago_threshold(self, table: _Table) -> float:
        if not self.ORDAGO_OWN:
            return 2.0  # nunca
        threshold = self.ORDAGO - self.ORDAGO_DESPERATE * (0.5 - table.vaca(0, 0))
        return min(0.99, max(0.5, threshold))

    def _still_to_speak(self, obs: Observation) -> list[int]:
        """Asientos que hablan después de mí en este lance (y no han hablado todavía)."""
        spoken = {
            e.get("actor")
            for e in obs.history
            if e.get("round") == obs.round_no
            and e.get("phase") == obs.phase
            and (e["kind"] in STRONG or e["kind"] in WEAK)
        }
        order = [s for s in speaking_order(obs.mano) if s in obs.lance_participants]
        after = order[order.index(obs.seat) + 1 :] if obs.seat in order else []
        return [s for s in after if s not in spoken]

    def _lead(self, obs: Observation, table: _Table) -> Action:
        legal = obs.legal_types()
        p = table.p
        if "ordago" in legal and p >= self._ordago_threshold(table):
            return OrdagoAction()
        after = self._still_to_speak(obs)
        rival_after = any(s % 2 != obs.team for s in after)
        if p >= 0.85 and rival_after and self.rng.random() < self.SLOWPLAY:
            return PassAction()
        spec = obs.spec("bet")
        if spec is None:
            return PassAction()
        lo = spec.min_amount or 2
        hi = spec.max_amount or lo
        if p >= self.P_BET:
            amount = 2
            if p >= self.P_BET + 0.1:
                amount = round(2 + (p - self.P_BET - 0.1) * 25) + self.rng.choice((-1, 0, 0, 1))
            return BetAction(max(lo, min(hi, amount, 10)))
        last = not after
        if self.rng.random() < self.BLUFF * (2.5 if last else 0.6):
            return BetAction(lo)
        return PassAction()

    def _respond(self, obs: Observation, table: _Table) -> Action | None:
        bet = obs.current_bet
        if bet is None:
            return None
        legal = obs.legal_types()
        accept: Action = AcceptAction() if "accept" in legal else AcceptNoLoseAction()
        can_accept = accept.type in legal
        alone = self.LEAVE_TO_PARTNER and obs.partner in bet.responders[1:]
        p = table.p_alone if alone else table.p
        reject = table.rejected(bet.previous)

        if bet.is_ordago:
            return accept if can_accept and p > reject else RejectAction()

        if "ordago" in legal and p >= self._ordago_threshold(table):
            return OrdagoAction()
        raise_spec = obs.spec("raise")
        if raise_spec is not None and p >= self.P_RAISE:
            lo = raise_spec.min_amount or 2
            hi = raise_spec.max_amount or lo
            return RaiseAction(max(lo, min(hi, max(2, bet.stake), 10)))
        if can_accept and table.accepted(bet.stake, alone) > reject:
            return accept
        return RejectAction()
