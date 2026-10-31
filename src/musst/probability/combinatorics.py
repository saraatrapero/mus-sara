"""Combinatoria del reparto: clases de rango y distribución hipergeométrica multivariante.

Todos los lances se evalúan con el **rango normalizado** de cada carta (con ocho reyes, el 3
cuenta como rey y el 2 como as; el palo no importa nunca). Por eso una mano se puede resumir,
sin perder nada, en un *multiconjunto de clases de rango*: con ocho reyes hay 8 clases
(1, 4, 5, 6, 7, 10, 11, 12) y C(8+4−1, 4) = 330 tipos de mano.

Si quedan ``N`` cartas desconocidas, con ``n_r`` de la clase ``r``, la probabilidad de que una
mano de 4 cartas tomada sin reemplazo tenga ``m_r`` cartas de cada clase es la
**hipergeométrica multivariante**::

    P(m) = Π_r C(n_r, m_r) / C(N, 4)        con Σ_r m_r = 4

(identidad de Vandermonde: Σ_m Π_r C(n_r, m_r) = C(N, 4), así que suma 1).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations_with_replacement
from math import comb

from musst.engine.cards import Card, full_deck, normalized_rank

HAND_SIZE = 4

RankCounts = tuple[int, ...]
"""Cartas que quedan de cada clase de rango, en el orden de :attr:`RankClasses.ranks`."""
HandType = tuple[int, ...]
"""Una mano como multiconjunto: rangos normalizados ordenados de menor a mayor."""


def hypergeom_pmf(population: int, successes: int, draws: int, k: int) -> float:
    """P(X = k) con X ~ Hipergeométrica(N=population, K=successes, n=draws).

    Muestreo **sin reemplazo**: P(X = k) = C(K, k) · C(N − K, n − k) / C(N, n).
    """
    if not (0 <= k <= draws and 0 <= successes <= population and draws <= population):
        return 0.0
    if k > successes or draws - k > population - successes:
        return 0.0
    return comb(successes, k) * comb(population - successes, draws - k) / comb(population, draws)


@dataclass(frozen=True)
class RankClasses:
    """Clases de rango de la baraja y las cartas de cada una."""

    ranks: tuple[int, ...]
    cards: tuple[tuple[Card, ...], ...]
    eight_kings: bool

    @classmethod
    def build(cls, eight_kings: bool = True) -> RankClasses:
        by_rank: dict[int, list[Card]] = {}
        for card in full_deck():
            by_rank.setdefault(normalized_rank(card, eight_kings), []).append(card)
        ranks = tuple(sorted(by_rank))
        return cls(ranks, tuple(tuple(by_rank[r]) for r in ranks), eight_kings)

    def index(self, card: Card) -> int:
        return self.ranks.index(normalized_rank(card, self.eight_kings))

    def counts(self, cards: Iterable[Card]) -> RankCounts:
        """Cuántas cartas de cada clase hay en ``cards``."""
        c = Counter(self.index(card) for card in cards)
        return tuple(c.get(i, 0) for i in range(len(self.ranks)))

    def representative(self, hand_type: HandType) -> tuple[Card, ...]:
        """Una mano concreta del tipo dado. Cualquier otra del mismo tipo se evalúa igual en
        todos los lances, porque la evaluación solo usa rangos normalizados."""
        used: Counter[int] = Counter()
        out = []
        for rank in hand_type:
            i = self.ranks.index(rank)
            out.append(self.cards[i][used[i]])
            used[i] += 1
        return tuple(out)


@lru_cache(maxsize=4)
def rank_classes(eight_kings: bool = True) -> RankClasses:
    return RankClasses.build(eight_kings)


@lru_cache(maxsize=4)
def hand_types(n_classes: int) -> tuple[tuple[tuple[int, int], ...], ...]:
    """Todos los multiconjuntos de 4 clases, como pares ``(índice de clase, multiplicidad)``."""
    out = []
    for combo in combinations_with_replacement(range(n_classes), HAND_SIZE):
        c = Counter(combo)
        out.append(tuple(sorted(c.items())))
    return tuple(out)


def type_weight(counts: RankCounts, hand_type: Sequence[tuple[int, int]]) -> int:
    """Número de manos concretas de ese tipo con las cartas que quedan: Π_r C(n_r, m_r)."""
    w = 1
    for i, m in hand_type:
        w *= comb(counts[i], m)
        if w == 0:
            return 0
    return w


def ranks_of(classes: RankClasses, hand_type: Sequence[tuple[int, int]]) -> HandType:
    return tuple(classes.ranks[i] for i, m in hand_type for _ in range(m))


@dataclass(frozen=True)
class HandDistribution:
    """Distribución **exacta** del tipo de mano de un asiento: (tipo, probabilidad)."""

    classes: RankClasses
    items: tuple[tuple[HandType, float], ...]

    def probability(self, event: Callable[[tuple[Card, ...]], bool]) -> float:
        """P(la mano cumple ``event``), evaluando una mano representativa de cada tipo."""
        return sum(p for t, p in self.items if event(self.classes.representative(t)))

    def total(self) -> float:
        return sum(p for _, p in self.items)


def hand_distribution(
    counts: RankCounts,
    classes: RankClasses,
    condition: Callable[[tuple[Card, ...]], bool] | None = None,
) -> HandDistribution:
    """Distribución exacta (hipergeométrica multivariante) de una mano de 4 cartas tomada de
    las ``counts`` cartas desconocidas; si hay ``condition``, condicionada a ella (Bayes con
    verosimilitud 0/1: P(t | C) = P(t)·1[C(t)] / P(C))."""
    total = comb(sum(counts), HAND_SIZE)
    items = []
    for ht in hand_types(len(classes.ranks)):
        w = type_weight(counts, ht)
        if not w:
            continue
        t = ranks_of(classes, ht)
        if condition is not None and not condition(classes.representative(t)):
            continue
        items.append((t, w / total))
    z = sum(p for _, p in items)
    if condition is not None:
        if z == 0:
            return HandDistribution(classes, ())
        items = [(t, p / z) for t, p in items]
    return HandDistribution(classes, tuple(items))


def enumerate_deals(
    pool: Sequence[Card],
    seats: Sequence[int],
    classes: RankClasses,
    condition: Callable[[int, tuple[Card, ...]], bool] | None = None,
    max_states: int = 2_000_000,
) -> Iterator[tuple[dict[int, tuple[Card, ...]], float]]:
    """Enumera **todos** los repartos (por tipos de mano) de las cartas desconocidas ``pool``
    entre ``seats``, con su probabilidad exacta bajo el reparto uniforme:

        P(t_1, …, t_k) = Π_j [ Π_r C(n_r^(j), m_r^(j)) / C(N_j, 4) ]

    donde ``n^(j)`` son las cartas que quedan tras repartir a los asientos anteriores. Cada
    tipo se materializa con cartas reales y distintas de ``pool`` (el palo no influye en
    ningún lance). Con ``condition`` se omiten los repartos incompatibles: la suma deja de
    ser 1 y hay que renormalizar (es la P de la evidencia). Pensado para casos reducidos:
    lanza ``ValueError`` si el número de estados se dispara.
    """
    types = hand_types(len(classes.ranks))
    by_class: list[list[Card]] = [[] for _ in classes.ranks]
    for card in pool:
        by_class[classes.index(card)].append(card)
    visited = 0

    def rec(
        j: int, remaining: list[int], acc: dict[int, tuple[Card, ...]], p: float
    ) -> Iterator[tuple[dict[int, tuple[Card, ...]], float]]:
        nonlocal visited
        if j == len(seats):
            yield dict(acc), p
            return
        total = comb(sum(remaining), HAND_SIZE)
        for ht in types:
            w = type_weight(tuple(remaining), ht)
            if not w:
                continue
            visited += 1
            if visited > max_states:
                raise ValueError("Demasiados estados para el cálculo exacto: usa Monte Carlo")
            # Cartas concretas: las siguientes sin usar de cada clase.
            hand = tuple(by_class[i][remaining[i] - k - 1] for i, m in ht for k in range(m))
            seat = seats[j]
            if condition is not None and not condition(seat, hand):
                continue
            for i, m in ht:
                remaining[i] -= m
            acc[seat] = hand
            yield from rec(j + 1, remaining, acc, p * w / total)
            for i, m in ht:
                remaining[i] += m
            del acc[seat]

    yield from rec(0, list(classes.counts(pool)), {}, 1.0)
