"""Probabilidades de cada lance y distribución de tantos, con los evaluadores del motor.

Para un reparto H (mis cartas + las de los otros tres), el resultado de un lance para mi pareja
es uno de:

* ``gana`` — el mejor jugador del lance es de mi pareja;
* ``pierde`` — es de la pareja rival;
* ``nadie`` — en pares/juego, nadie lo tiene y el lance no se juega.

``empate_cartas`` marca que la mejor jugada de cada pareja es **idéntica**: lo decide quien
está más cerca del mano (FEM), así que no hay empate en el resultado, pero conviene saber
cuántas veces se gana o se pierde solo por la posición.

Las magnitudes son distintas y no se mezclan:

* P(ganar un lance) — este módulo;
* tantos de la jugada si todo va en paso — :func:`round_points_paso`;
* P(ganar la partida) — :mod:`musst.probability.equity`;
* valor esperado de una decisión — :mod:`musst.probability.decision`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from musst.engine import evaluation as ev
from musst.engine.cards import Card
from musst.engine.config import RulesConfig
from musst.probability.combinatorics import hand_distribution, rank_classes
from musst.probability.estimators import (
    Method,
    ProbabilityEstimate,
    exact,
    weighted_mean,
    weighted_proportion,
)
from musst.probability.sampler import SeatConstraint, World

OUTCOMES = ("gana", "pierde", "nadie")


def speaking_order(mano: int) -> list[int]:
    return [(mano + i) % 4 for i in range(4)]


def lance_outcome(
    lance: str, world: World, mano: int, team: int, eight_kings: bool = True
) -> tuple[str, bool]:
    """(resultado para ``team``, ¿empate de cartas entre las dos parejas?)."""
    keys = ev.lance_keys(lance, world, eight_kings)
    if not keys:
        return "nadie", False
    winner = ev.best_seat(keys, speaking_order(mano))
    mine = [k for s, k in keys.items() if s % 2 == team]
    theirs = [k for s, k in keys.items() if s % 2 != team]
    tie = bool(mine and theirs and max(mine) == max(theirs))
    return ("gana" if winner % 2 == team else "pierde"), tie


def lances_in_play(world: World, eight_kings: bool = True) -> tuple[str, ...]:
    """Lances que se juegan con este reparto: punto solo si nadie tiene juego."""
    juego = any(ev.has_juego(h, eight_kings) for h in world.values())
    return ("grande", "chica", "pares", "juego") if juego else ("grande", "chica", "pares", "punto")


def round_points_paso(
    world: World, mano: int, team: int, config: RulesConfig | None = None
) -> tuple[int, int]:
    """Tantos (míos, suyos) de la jugada si **todos los lances van en paso** (sin envites):
    grande y chica valen ``paso_points`` y pares/juego/punto lo que valgan las jugadas de la
    pareja ganadora (reglas y tanteo del motor)."""
    cfg = config or RulesConfig()
    k8 = cfg.eight_kings
    pts = [0, 0]
    for lance in lances_in_play(world, k8):
        winner = ev.lance_winner(lance, world, speaking_order(mano), k8)
        if winner is None:
            continue
        t = winner % 2
        if lance in ("grande", "chica"):
            pts[t] += cfg.paso_points
        else:
            pts[t] += ev.play_points(lance, (world[t], world[t + 2]), cfg)
    return (pts[team], pts[1 - team])


@dataclass(frozen=True)
class LanceProbabilities:
    lance: str
    win: ProbabilityEstimate
    lose: ProbabilityEstimate
    nobody: ProbabilityEstimate
    tie_cards: ProbabilityEstimate

    def to_dict(self) -> dict[str, object]:
        return {
            "gana": self.win.to_dict(),
            "pierde": self.lose.to_dict(),
            "nadie": self.nobody.to_dict(),
            "empate_de_cartas": self.tie_cards.to_dict(),
        }


@dataclass(frozen=True)
class PointsDistribution:
    """Distribución de los tantos de la jugada (en paso) para mi pareja y la rival."""

    mine: dict[int, float]
    theirs: dict[int, float]
    net_mean: float
    net_var: float
    method: Method

    def to_dict(self) -> dict[str, object]:
        return {
            "mios": {k: round(v, 4) for k, v in sorted(self.mine.items())},
            "suyos": {k: round(v, 4) for k, v in sorted(self.theirs.items())},
            "diferencia_media": round(self.net_mean, 3),
            "diferencia_varianza": round(self.net_var, 3),
            "metodo": self.method.value,
        }


@dataclass(frozen=True)
class RoundAnalysis:
    lances: dict[str, LanceProbabilities]
    points: PointsDistribution


def analyze(
    worlds: Sequence[World],
    weights: Sequence[float],
    mano: int,
    team: int,
    method: Method,
    lances: Iterable[str] = ev.LANCES,
    config: RulesConfig | None = None,
    is_exact: bool = False,
) -> RoundAnalysis:
    """Probabilidades de cada lance y distribución de tantos sobre repartos ponderados.

    Con ``is_exact`` los pesos son probabilidades exactas (enumeración completa) y no hay
    error de muestreo; si no, cada valor lleva su SE e IC95."""
    k8 = (config or RulesConfig()).eight_kings
    out: dict[str, LanceProbabilities] = {}
    for lance in lances:
        results = [lance_outcome(lance, w, mano, team, k8) for w in worlds]

        def est(values: list[float], m: Method = method) -> ProbabilityEstimate:
            if is_exact:
                total = sum(weights)
                return exact(sum(w * v for w, v in zip(weights, values, strict=True)) / total)
            return weighted_proportion(values, weights, m)

        out[lance] = LanceProbabilities(
            lance,
            est([1.0 if r == "gana" else 0.0 for r, _ in results]),
            est([1.0 if r == "pierde" else 0.0 for r, _ in results]),
            est([1.0 if r == "nadie" else 0.0 for r, _ in results]),
            est([1.0 if t else 0.0 for _, t in results]),
        )
    pts = [round_points_paso(w, mano, team, config) for w in worlds]
    total = sum(weights) or 1.0
    mine: dict[int, float] = {}
    theirs: dict[int, float] = {}
    for (a, b), w in zip(pts, weights, strict=True):
        mine[a] = mine.get(a, 0.0) + w / total
        theirs[b] = theirs.get(b, 0.0) + w / total
    net_mean, net_var, _ = weighted_mean([a - b for a, b in pts], list(weights))
    return RoundAnalysis(out, PointsDistribution(mine, theirs, net_mean, net_var, method))


def analytic_win_probability(
    hand: tuple[Card, ...],
    seat: int,
    mano: int,
    lance: str,
    pool: Sequence[Card],
    constraints: Mapping[int, SeatConstraint],
    opponent_weight: Callable[[int, tuple[Card, ...]], float] | None = None,
    eight_kings: bool = True,
) -> ProbabilityEstimate:
    """P(mi pareja gana el lance) con las **marginales exactas** de cada asiento.

    Cada uno de los otros tres asientos tiene su distribución exacta (hipergeométrica
    multivariante sobre las cartas desconocidas, condicionada a sus declaraciones y señas).
    Se combinan **como si fueran independientes** (en realidad compiten por las mismas cartas):
    por eso el resultado se etiqueta ``analitica_aproximada`` y no ``exacta``::

        P(gana) ≈ Σ_{t_c} P_c(t_c) · Π_{o rival} P_o(o no supera a la mejor jugada de mi pareja)

    ``opponent_weight`` reescala la marginal de cada rival por una verosimilitud (Bayes sobre
    la marginal: P_o(t | E) ∝ P_o(t)·P(E | t)), p. ej. «quiere el envite».
    """
    classes = rank_classes(eight_kings)
    counts = classes.counts(pool)
    order = speaking_order(mano)
    pos = {s: order.index(s) for s in range(4)}
    partner = (seat + 2) % 4
    opps = [(seat + 1) % 4, (seat + 3) % 4]

    def key_of(h: tuple[Card, ...]) -> tuple[int, ...] | None:
        keys = ev.lance_keys(lance, {0: h}, eight_kings)
        return keys.get(0)

    def marginal(s: int) -> list[tuple[tuple[int, ...] | None, float]]:
        c = constraints.get(s, SeatConstraint())
        dist = hand_distribution(counts, classes, lambda h: c.admits(h, eight_kings))
        items = [(classes.representative(t), p) for t, p in dist.items]
        if opponent_weight is not None and s in opps:
            items = [(h, p * opponent_weight(s, h)) for h, p in items]
            z = sum(p for _, p in items) or 1.0
            items = [(h, p / z) for h, p in items]
        return [(key_of(h), p) for h, p in items]

    mine = key_of(hand)
    opp_m = {o: marginal(o) for o in opps}
    win = 0.0
    for kp, pp in marginal(partner):
        if mine is None and kp is None:
            continue
        # Mejor jugada de mi pareja y quién la tiene (en empate, el más cercano al mano).
        if kp is None or (
            mine is not None and (mine > kp or (mine == kp and pos[seat] < pos[partner]))
        ):
            best, holder = mine, seat
        else:
            best, holder = kp, partner
        assert best is not None
        p_all = pp
        for o in opps:
            p_all *= sum(
                p
                for k, p in opp_m[o]
                if k is None or k < best or (k == best and pos[holder] < pos[o])
            )
        win += p_all
    return ProbabilityEstimate(min(1.0, max(0.0, win)), Method.ANALYTIC)
