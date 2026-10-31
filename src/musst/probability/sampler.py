"""Repartos posibles de las cartas desconocidas, compatibles con lo que sabe un asiento.

Restricciones duras (información pública o propia, FEM):

* las cartas que no puede tener nadie más: las mías y mis descartes de esta jugada;
* las declaraciones de pares y juego («sí»/«no») de cada asiento;
* las señas que he visto, que son siempre verdaderas (FEM VIII.4).

Distribución objetivo: **uniforme sobre los repartos compatibles**,
π(h_1, h_2, h_3) ∝ Π_s 1[h_s cumple las restricciones de s].

Muestreo secuencial exacto con pesos de importancia. Para cada asiento ``s``, con las cartas
que quedan (N_s cartas), se calcula exactamente con la hipergeométrica multivariante la
fracción de manos compatibles::

    Z_s = Σ_{t compatible} Π_r C(n_r, m_r) / C(N_s, 4)

y se toma una mano de su distribución condicionada exacta (tipo ∝ Π_r C(n_r, m_r), palos al
azar). La propuesta es q = Π_s 1[c_s]/(Z_s·C(N_s,4)), así que el peso de importancia
π/q ∝ Π_s Z_s. A diferencia del rechazo con relajación de ``toolkit.sample_world``, no hay
sesgo: el estimador autonormalizado converge al valor exacto (ver tests).
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from math import comb

from musst.bots.toolkit import unseen_cards
from musst.engine import evaluation as ev
from musst.engine.cards import Card
from musst.engine.observation import Observation
from musst.engine.signals import truthful_signals
from musst.probability.combinatorics import (
    HAND_SIZE,
    RankClasses,
    enumerate_deals,
    hand_types,
    rank_classes,
    ranks_of,
    type_weight,
)

World = dict[int, tuple[Card, ...]]


@dataclass(frozen=True)
class SeatConstraint:
    """Lo que se sabe en público (o por señas vistas) de la mano de un asiento."""

    pares: bool | None = None
    juego: bool | None = None
    signals: frozenset[str] = frozenset()

    @property
    def empty(self) -> bool:
        return self.pares is None and self.juego is None and not self.signals

    def admits(self, hand: tuple[Card, ...], eight_kings: bool = True) -> bool:
        if self.pares is not None and ev.pairs(hand, eight_kings).has_pairs != self.pares:
            return False
        if self.juego is not None and ev.has_juego(hand, eight_kings) != self.juego:
            return False
        if self.signals:
            truthful = {s.value for s in truthful_signals(hand, eight_kings)}
            if not self.signals <= truthful:
                return False
        return True


def constraints_from(obs: Observation) -> dict[int, SeatConstraint]:
    """Restricciones de los otros tres asientos, sacadas **solo** de la observación."""
    out = {}
    for seat in range(4):
        if seat == obs.seat:
            continue
        out[seat] = SeatConstraint(
            obs.declarations.get("pares", {}).get(seat),
            obs.declarations.get("juego", {}).get(seat),
            frozenset(obs.signals_seen.get(seat, ())),
        )
    return out


@lru_cache(maxsize=256)
def _valid_types(
    constraint: SeatConstraint, eight_kings: bool
) -> tuple[tuple[tuple[int, int], ...], ...]:
    """Tipos de mano (multiconjuntos de clases) que cumplen la restricción."""
    classes = rank_classes(eight_kings)
    return tuple(
        ht
        for ht in hand_types(len(classes.ranks))
        if constraint.admits(classes.representative(ranks_of(classes, ht)), eight_kings)
    )


@dataclass
class WorldSample:
    world: World
    weight: float
    """Peso de importancia Π_s Z_s (0 si el reparto resultó imposible)."""


@dataclass
class WorldSampler:
    """Genera repartos de las cartas desconocidas para los asientos ``others``."""

    seat: int
    hand: tuple[Card, ...]
    pool: tuple[Card, ...]
    constraints: dict[int, SeatConstraint]
    eight_kings: bool = True
    others: tuple[int, ...] = field(init=False)

    def __post_init__(self) -> None:
        self.others = tuple(s for s in range(4) if s != self.seat)
        if len(self.pool) < HAND_SIZE * len(self.others):
            raise ValueError("No quedan cartas suficientes para repartir")

    @classmethod
    def from_observation(cls, obs: Observation, eight_kings: bool = True) -> WorldSampler:
        return cls(obs.seat, obs.hand, tuple(unseen_cards(obs)), constraints_from(obs), eight_kings)

    @property
    def classes(self) -> RankClasses:
        return rank_classes(self.eight_kings)

    def sample(self, rng: random.Random) -> WorldSample:
        classes = self.classes
        by_class: list[list[Card]] = [[] for _ in classes.ranks]
        for card in self.pool:
            by_class[classes.index(card)].append(card)
        world: World = {self.seat: self.hand}
        weight = 1.0
        for seat in self.others:
            constraint = self.constraints.get(seat, SeatConstraint())
            counts = tuple(len(c) for c in by_class)
            n_cards = sum(counts)
            if constraint.empty:
                flat = [c for cards in by_class for c in cards]
                hand = tuple(rng.sample(flat, HAND_SIZE))
            else:
                types = _valid_types(constraint, self.eight_kings)
                weights = [type_weight(counts, ht) for ht in types]
                z = sum(weights)
                if z == 0:
                    return WorldSample(world, 0.0)
                weight *= z / comb(n_cards, HAND_SIZE)
                (ht,) = rng.choices(types, weights=weights)
                hand = tuple(c for i, m in ht for c in rng.sample(by_class[i], m))
            for card in hand:
                by_class[classes.index(card)].remove(card)
            world[seat] = hand
        return WorldSample(world, weight)

    def exact_worlds(self, max_states: int = 2_000_000) -> Iterator[tuple[World, float]]:
        """Todos los repartos compatibles con su probabilidad exacta (normalizada).

        Solo para casos reducidos (pocas cartas desconocidas): ``ValueError`` si no cabe."""

        def condition(seat: int, hand: tuple[Card, ...]) -> bool:
            return self.constraints.get(seat, SeatConstraint()).admits(hand, self.eight_kings)

        deals = list(enumerate_deals(self.pool, self.others, self.classes, condition, max_states))
        z = sum(p for _, p in deals)
        if z == 0:
            return
        for world, p in deals:
            yield {self.seat: self.hand, **world}, p / z


def sample_worlds(
    sampler: WorldSampler, rng: random.Random, n: int
) -> tuple[list[World], list[float]]:
    worlds, weights = [], []
    for _ in range(n):
        s = sampler.sample(rng)
        worlds.append(s.world)
        weights.append(s.weight)
    return worlds, weights


Statistic = Callable[[World], float]
