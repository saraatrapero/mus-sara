"""Evaluación de manos para cada lance.

Toda función devuelve una *clave comparable*: mayor clave = mejor jugada en ese lance.
Los empates los resuelve :func:`best_seat` a favor del jugador más cercano al mano.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import IntEnum

from musst.engine.cards import Card, normalized_rank, point_value

JUEGO_ORDER: tuple[int, ...] = (31, 32, 40, 37, 36, 35, 34, 33)
"""[CONVENCIÓN] Orden de los juegos de mejor a peor."""


class PairsKind(IntEnum):
    NONE = 0
    PAR = 1
    MEDIAS = 2
    DUPLES = 3


@dataclass(frozen=True)
class PairsResult:
    kind: PairsKind
    ranks: tuple[int, ...]
    """Rangos normalizados que forman la jugada, de mayor a menor."""

    @property
    def has_pairs(self) -> bool:
        return self.kind is not PairsKind.NONE

    @property
    def key(self) -> tuple[int, ...]:
        return (int(self.kind), *self.ranks)


def grande_key(hand: Sequence[Card], eight_kings: bool = True) -> tuple[int, ...]:
    """Cartas ordenadas de mayor a menor; se compara lexicográficamente."""
    return tuple(sorted((normalized_rank(c, eight_kings) for c in hand), reverse=True))


def chica_key(hand: Sequence[Card], eight_kings: bool = True) -> tuple[int, ...]:
    """En chica gana la carta más baja: se niega para que mayor clave = mejor."""
    return tuple(-r for r in sorted(normalized_rank(c, eight_kings) for c in hand))


def pairs(hand: Sequence[Card], eight_kings: bool = True) -> PairsResult:
    """Par, medias (tres iguales) o duples (dos parejas o cuatro iguales)."""
    counts = Counter(normalized_rank(c, eight_kings) for c in hand)
    groups = sorted(((n, r) for r, n in counts.items() if n >= 2), reverse=True)
    if not groups:
        return PairsResult(PairsKind.NONE, ())
    if groups[0][0] == 4:
        rank = groups[0][1]
        return PairsResult(PairsKind.DUPLES, (rank, rank))
    if len(groups) == 2:
        high, low = sorted((groups[0][1], groups[1][1]), reverse=True)
        return PairsResult(PairsKind.DUPLES, (high, low))
    count, rank = groups[0]
    return PairsResult(PairsKind.MEDIAS if count == 3 else PairsKind.PAR, (rank,))


def total_points(hand: Sequence[Card], eight_kings: bool = True) -> int:
    """Suma de valores para juego/punto."""
    return sum(point_value(c, eight_kings) for c in hand)


def has_juego(hand: Sequence[Card], eight_kings: bool = True) -> bool:
    return total_points(hand, eight_kings) >= 31


def juego_key(hand: Sequence[Card], eight_kings: bool = True) -> tuple[int, ...]:
    """Clave de juego; ``(-1,)`` si no hay juego."""
    total = total_points(hand, eight_kings)
    if total < 31:
        return (-1,)
    return (len(JUEGO_ORDER) - JUEGO_ORDER.index(total),)


def punto_key(hand: Sequence[Card], eight_kings: bool = True) -> tuple[int, ...]:
    return (total_points(hand, eight_kings),)


def best_seat(keys: dict[int, tuple[int, ...]], order: Iterable[int]) -> int:
    """Asiento con la mejor clave; en empate, el primero en ``order`` (más cercano al mano)."""
    best: int | None = None
    for seat in order:
        if seat not in keys:
            continue
        if best is None or keys[seat] > keys[best]:
            best = seat
    if best is None:
        raise ValueError("No hay asientos que comparar")
    return best
