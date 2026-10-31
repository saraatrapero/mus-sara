"""Valor esperado de cada acción legal en un lance: EV(a) = Σ_s P(s | E) · U(a, s).

* ``s`` — un reparto posible de las cartas desconocidas (mundo), con su probabilidad a
  posteriori P(s | E) (pesos de :mod:`musst.probability.bayes`).
* ``U(a, s)`` — **probabilidad de ganar la partida** después de resolver el lance con la
  acción ``a`` si el reparto es ``s`` (:mod:`musst.probability.equity`). Así la utilidad tiene
  en cuenta el marcador y lo que falta para ganar: 2 tantos valen mucho más a 38-35 que a 5-5,
  y un órdago vale exactamente P(ganar el lance).

Consecuencias que se modelan (reglas y tanteo del motor):

* **Pasar** en un lance abierto: los rivales que aún no han hablado pueden envidar con
  probabilidad b(s) (modelo de decisiones de cada uno, según su mano en ``s``). Si envidan, mi
  pareja responde con **una sola** respuesta (querer o no querer) elegida con la información
  que tendría entonces —el conjunto de información, no las cartas de ``s``—:
  r* = argmax_r Σ_s w_s·b(s)·U(r, s). Si nadie envida, el lance va en paso.
* **Envidar** k tantos: la pareja rival lo quiere con probabilidad a(s) = 1 − Π_i (1 − a_i(s))
  (basta con que uno quiera, FEM VI.4). Si no lo quieren, cobro la negada en el acto (y en
  pares/juego/punto, el deje: mis jugadas). Si lo quieren, gana el lance quien tenga mejor
  jugada en ``s``. La **selección adversa** sale sola: a(s) es mayor en los mundos donde ellos
  tienen buena mano.
* **Órdago**: si lo quieren, U = 1 si gano el lance en ``s`` y 0 si no.
* **Responder** a un envite: querer, no querer (si mi compañero aún puede querer, decide él
  según su mano en ``s``), subir o echar órdago (con la respuesta de quien envidó).

Simplificaciones (documentadas): no se modelan resubidas más allá de una respuesta; los tantos
de los demás lances de la jugada se tratan como parte del resto de la partida (D en equity).

Además de E[U] se dan Var[U] y la media y varianza de la diferencia de tantos: el riesgo se ve,
pero la decisión maximiza P(ganar la partida), que es el objetivo del juego.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from musst.bots.toolkit import hand_strength
from musst.engine import evaluation as ev
from musst.engine.actions import (
    AcceptAction,
    AcceptNoLoseAction,
    Action,
    BetAction,
    OrdagoAction,
    PassAction,
    RaiseAction,
    RejectAction,
    action_to_dict,
)
from musst.engine.config import RulesConfig
from musst.engine.observation import Observation
from musst.probability.bayes import BehaviourModel
from musst.probability.equity import equity_after
from musst.probability.lances import lance_outcome
from musst.probability.sampler import World

ACCEPT_SHARPNESS = 0.1
ORDAGO_ACCEPT_SHIFT = 0.2
"""Para querer un órdago se supone una mano algo mejor que para querer un envite."""
STAKE_ACCEPT_SHIFT = 0.01
"""Cada tanto más de envite exige un poco más de mano para quererlo."""
RESPONSE_FLOOR = 0.03
"""Nadie quiere ni rechaza con certeza absoluta."""
PLAY_LANCES = ("pares", "juego", "punto")


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def label(action: Action) -> str:
    data = action_to_dict(action)
    return str(data["type"]).upper() + (f"_{data['amount']}" if "amount" in data else "")


@dataclass(frozen=True)
class ActionValue:
    action: Action
    ev: float
    """E[U]: probabilidad esperada de ganar la partida tras la acción."""
    var: float
    """Var[U] entre mundos y respuestas."""
    points_mean: float | None
    """E[tantos míos − tantos suyos] en el lance (None en órdago: se juega la partida)."""
    points_var: float | None
    details: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "accion": label(self.action),
            "ev_partida": round(self.ev, 4),
            "var_partida": round(self.var, 5),
        }
        if self.points_mean is not None:
            out["ev_tantos"] = round(self.points_mean, 3)
            out["var_tantos"] = round(self.points_var or 0.0, 3)
        out.update({k: round(v, 4) for k, v in self.details.items()})
        return out


class _Moments:
    """Acumula E[X] y E[X²] de una mezcla ponderada."""

    def __init__(self) -> None:
        self.w = self.s = self.s2 = 0.0

    def add(self, weight: float, value: float) -> None:
        self.w += weight
        self.s += weight * value
        self.s2 += weight * value * value

    @property
    def mean(self) -> float:
        return self.s / self.w if self.w else 0.0

    @property
    def var(self) -> float:
        return max(0.0, self.s2 / self.w - self.mean**2) if self.w else 0.0


@dataclass
class DecisionModel:
    """Calcula el valor esperado de las acciones legales de ``obs`` en el lance actual."""

    obs: Observation
    worlds: Sequence[World]
    weights: Sequence[float]
    behaviour: BehaviourModel
    config: RulesConfig = field(default_factory=RulesConfig)

    def __post_init__(self) -> None:
        obs = self.obs
        self.lance = obs.phase
        self.team = obs.team
        self.mine = obs.score[obs.team]
        self.theirs = obs.score[1 - obs.team]
        self.target = obs.target
        k8 = self.config.eight_kings
        self.outcome = [
            lance_outcome(self.lance, w, obs.mano, obs.team, k8)[0] for w in self.worlds
        ]
        if self.lance in PLAY_LANCES:
            self.pv_mine = [
                ev.play_points(self.lance, (w[obs.team], w[obs.team + 2]), self.config)
                for w in self.worlds
            ]
            other = 1 - obs.team
            self.pv_theirs = [
                ev.play_points(self.lance, (w[other], w[other + 2]), self.config)
                for w in self.worlds
            ]
        else:
            self.pv_mine = [0] * len(self.worlds)
            self.pv_theirs = [0] * len(self.worlds)

    # ------------------------------------------------------------------ utilidades
    def utility(self, d_mine: int, d_theirs: int) -> float:
        return equity_after(self.mine, self.theirs, self.target, d_mine, d_theirs)

    def p_accept(self, seat: int, world: World, stake: int, ordago: bool = False) -> float:
        """P(el asiento quiere | su mano en el mundo): modelo de decisiones (no de cartas)."""
        p = self.behaviour.params(seat)
        shift = ORDAGO_ACCEPT_SHIFT if ordago else STAKE_ACCEPT_SHIFT * max(0, stake - 2)
        x = (hand_strength(world[seat], self.lance) - p.accept_threshold - shift) / ACCEPT_SHARPNESS
        return min(1 - RESPONSE_FLOOR, max(RESPONSE_FLOOR, sigmoid(x)))

    def p_team_accepts(
        self, seats: Sequence[int], world: World, stake: int, ordago: bool = False
    ) -> float:
        refuse = 1.0
        for seat in seats:
            refuse *= 1 - self.p_accept(seat, world, stake, ordago)
        return 1 - refuse

    def p_bets(self, seat: int, world: World) -> float:
        """P(el asiento envida en un lance abierto | su mano)."""
        p = self.behaviour.params(seat)
        strength = hand_strength(world[seat], self.lance)
        value = sigmoid((strength - p.bet_threshold) / 0.05)
        return min(1 - RESPONSE_FLOOR, max(RESPONSE_FLOOR, 0.5 * p.bluff + (1 - p.bluff) * value))

    def players_of_lance(self) -> list[int]:
        """Quién juega el lance (pares/juego: quien lo ha declarado)."""
        if self.obs.lance_participants:
            return list(self.obs.lance_participants)
        return [(self.obs.mano + i) % 4 for i in range(4)]

    # ------------------------------------------------------------------ resultados por mundo
    def accepted(self, i: int, stake: int) -> tuple[int, int]:
        """Tantos (míos, suyos) si se quiere un envite de ``stake`` en el mundo ``i``."""
        bonus = self.lance in PLAY_LANCES
        o = self.outcome[i]
        if o == "gana":
            return stake + (self.pv_mine[i] if bonus else 0), 0
        if o == "pierde":
            return 0, stake + (self.pv_theirs[i] if bonus else 0)
        return 0, 0

    def paso(self, i: int) -> tuple[int, int]:
        o = self.outcome[i]
        if self.lance in ("grande", "chica"):
            pts = self.config.paso_points
            return (pts, 0) if o == "gana" else (0, pts) if o == "pierde" else (0, 0)
        if o == "gana":
            return self.pv_mine[i], 0
        if o == "pierde":
            return 0, self.pv_theirs[i]
        return 0, 0

    def rejected(self, i: int, previous: int, bettor_is_me: bool) -> tuple[int, int]:
        """Envite no querido: la pareja que envidó cobra ``previous`` y, en pares/juego/punto,
        además sus jugadas (deje, FEM VII.1)."""
        deje = self.lance in PLAY_LANCES
        if bettor_is_me:
            return previous + (self.pv_mine[i] if deje else 0), 0
        return 0, previous + (self.pv_theirs[i] if deje else 0)

    # ------------------------------------------------------------------ acciones
    def evaluate(self) -> list[ActionValue]:
        obs = self.obs
        types = obs.legal_types()
        out: list[ActionValue] = []
        if obs.current_bet is None:
            if "pass" in types:
                out.append(self._pass())
            spec = obs.spec("bet")
            if spec is not None:
                amounts = sorted({spec.min_amount or 2, 4, 8})
                for amount in amounts:
                    if amount <= (spec.max_amount or amount):
                        out.append(self._bet(BetAction(amount), amount, ordago=False))
            if "ordago" in types:
                out.append(self._bet(OrdagoAction(), 0, ordago=True))
            return out
        bet = obs.current_bet
        accept = (
            "accept"
            if "accept" in types
            else "accept_no_lose"
            if "accept_no_lose" in types
            else None
        )
        if accept is not None:
            out.append(self._accept(AcceptAction() if accept == "accept" else AcceptNoLoseAction()))
        if "reject" in types:
            out.append(self._reject())
        spec = obs.spec("raise")
        if spec is not None and not bet.is_ordago:
            for extra in sorted({spec.min_amount or 2, 5}):
                if extra <= (spec.max_amount or extra):
                    out.append(self._raise(RaiseAction(extra), bet.stake, extra))
        if "ordago" in types and not bet.is_ordago:
            out.append(self._raise(OrdagoAction(), bet.stake, 0, ordago=True))
        return out

    def _value(
        self,
        action: Action,
        branches: Callable[[int], list[tuple[float, float, float | None]]],
        details: dict[str, float] | None = None,
    ) -> ActionValue:
        """``branches(i)`` → [(probabilidad, utilidad, diferencia de tantos o None)] en el mundo i."""
        u = _Moments()
        pts = _Moments()
        has_pts = True
        for i, w in enumerate(self.weights):
            if w <= 0:
                continue
            for p, util, diff in branches(i):
                if p <= 0:
                    continue
                u.add(w * p, util)
                if diff is None:
                    has_pts = False
                else:
                    pts.add(w * p, diff)
        return ActionValue(
            action,
            u.mean,
            u.var,
            pts.mean if has_pts else None,
            pts.var if has_pts else None,
            details or {},
        )

    def _u(self, d: tuple[int, int]) -> tuple[float, float]:
        return self.utility(*d), float(d[0] - d[1])

    def _pass(self) -> ActionValue:
        order = self.players_of_lance()
        me = order.index(self.obs.seat) if self.obs.seat in order else 0
        later_opp = [s for s in order[me + 1 :] if s % 2 != self.team]
        b = [
            1 - math.prod(1 - self.p_bets(s, w) for s in later_opp) if later_opp else 0.0
            for w in self.worlds
        ]
        stake = self.config.min_bet
        # Respuesta en el conjunto de información: una sola para todos los mundos.
        accept_v = sum(
            w * bi * self.utility(*self.accepted(i, stake))
            for i, (w, bi) in enumerate(zip(self.weights, b, strict=True))
        )
        reject_v = sum(
            w * bi * self.utility(*self.rejected(i, self.config.negada_points, False))
            for i, (w, bi) in enumerate(zip(self.weights, b, strict=True))
        )
        respond_accept = accept_v >= reject_v

        def branches(i: int) -> list[tuple[float, float, float | None]]:
            paso_u, paso_d = self._u(self.paso(i))
            if respond_accept:
                r_u, r_d = self._u(self.accepted(i, stake))
            else:
                r_u, r_d = self._u(self.rejected(i, self.config.negada_points, False))
            return [(1 - b[i], paso_u, paso_d), (b[i], r_u, r_d)]

        total = sum(self.weights) or 1.0
        p_bet = sum(w * bi for w, bi in zip(self.weights, b, strict=True)) / total
        return self._value(
            PassAction(),
            branches,
            {"p_envidan_ellos": p_bet, "responderia_queriendo": 1.0 if respond_accept else 0.0},
        )

    def _opponents_in_lance(self) -> list[int]:
        return [s for s in self.players_of_lance() if s % 2 != self.team]

    def _bet(self, action: Action, amount: int, ordago: bool) -> ActionValue:
        opps = self._opponents_in_lance()
        negada = self.config.negada_points
        acc = [self.p_team_accepts(opps, w, amount, ordago) for w in self.worlds]

        def branches(i: int) -> list[tuple[float, float, float | None]]:
            rej_u, rej_d = self._u(self.rejected(i, negada, True))
            if ordago:
                win = 1.0 if self.outcome[i] == "gana" else 0.0
                return [(1 - acc[i], rej_u, None), (acc[i], win, None)]
            acc_u, acc_d = self._u(self.accepted(i, amount))
            return [(1 - acc[i], rej_u, rej_d), (acc[i], acc_u, acc_d)]

        return self._value(action, branches, self._acceptance_details(acc))

    def _acceptance_details(self, acc: Sequence[float]) -> dict[str, float]:
        """P(lo quieren) y P(gano el lance | lo quieren): la selección adversa."""
        total = sum(self.weights) or 1.0
        wa = sum(w * a for w, a in zip(self.weights, acc, strict=True))
        win_a = sum(
            w * a for w, a, o in zip(self.weights, acc, self.outcome, strict=True) if o == "gana"
        )
        return {"p_quieren": wa / total, "p_gano_si_quieren": win_a / wa if wa else 0.0}

    def _accept(self, action: Action) -> ActionValue:
        bet = self.obs.current_bet
        assert bet is not None

        def branches(i: int) -> list[tuple[float, float, float | None]]:
            if bet.is_ordago:
                return [(1.0, 1.0 if self.outcome[i] == "gana" else 0.0, None)]
            return [(1.0, *self._u(self.accepted(i, bet.stake)))]

        return self._value(action, branches)

    def _reject(self) -> ActionValue:
        bet = self.obs.current_bet
        assert bet is not None
        partner = self.obs.partner
        partner_can = partner in bet.responders[1:]

        def branches(i: int) -> list[tuple[float, float, float | None]]:
            rej = self._u(self.rejected(i, bet.previous, False))
            if not partner_can:
                return [(1.0, *rej)]
            pa = self.p_accept(partner, self.worlds[i], bet.stake, bet.is_ordago)
            if bet.is_ordago:
                acc: tuple[float, float | None] = (1.0 if self.outcome[i] == "gana" else 0.0, None)
            else:
                acc = self._u(self.accepted(i, bet.stake))
            return [(1 - pa, *rej), (pa, *acc)]

        return self._value(RejectAction(), branches, {"companero_puede_querer": float(partner_can)})

    def _raise(self, action: Action, stake: int, extra: int, ordago: bool = False) -> ActionValue:
        bet = self.obs.current_bet
        assert bet is not None
        opps = self._opponents_in_lance()
        total_stake = stake + extra
        acc = [self.p_team_accepts(opps, w, total_stake, ordago) for w in self.worlds]

        def branches(i: int) -> list[tuple[float, float, float | None]]:
            rej_u, rej_d = self._u(self.rejected(i, stake, True))
            if ordago:
                win = 1.0 if self.outcome[i] == "gana" else 0.0
                return [(1 - acc[i], rej_u, None), (acc[i], win, None)]
            acc_u, acc_d = self._u(self.accepted(i, total_stake))
            return [(1 - acc[i], rej_u, rej_d), (acc[i], acc_u, acc_d)]

        return self._value(action, branches, self._acceptance_details(acc))


def best_action(values: Sequence[ActionValue]) -> ActionValue:
    """argmax E[U]; en empate, más tantos esperados."""
    return max(
        values,
        key=lambda v: (round(v.ev, 12), v.points_mean if v.points_mean is not None else -1e9),
    )
