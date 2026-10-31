"""Evaluación de manos para cada lance.

Toda función devuelve una *clave comparable*: mayor clave = mejor jugada en ese lance.
Los empates los resuelve :func:`best_seat` a favor del jugador más cercano al mano.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

from musst.engine.cards import Card, normalized_rank, point_value

if TYPE_CHECKING:
    from musst.engine.config import RulesConfig

LANCES: tuple[str, ...] = ("grande", "chica", "pares", "juego", "punto")

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


# ------------------------------------------------------------------ resolución de un lance
# Funciones puras: las usa el propio motor (MusGame) y cualquier módulo que necesite saber quién
# gana un lance con unas manos dadas (bots, análisis, motor probabilístico). Así las reglas
# existen en un único sitio.
def lance_keys(
    lance: str, hands: Mapping[int, Sequence[Card]], eight_kings: bool = True
) -> dict[int, tuple[int, ...]]:
    """Clave de cada asiento que juega el lance (en pares y juego, solo quien lo tiene)."""
    if lance == "grande":
        return {s: grande_key(h, eight_kings) for s, h in hands.items()}
    if lance == "chica":
        return {s: chica_key(h, eight_kings) for s, h in hands.items()}
    if lance == "pares":
        out = {}
        for s, h in hands.items():
            p = pairs(h, eight_kings)
            if p.has_pairs:
                out[s] = p.key
        return out
    if lance == "juego":
        return {s: juego_key(h, eight_kings) for s, h in hands.items() if has_juego(h, eight_kings)}
    if lance == "punto":
        return {s: punto_key(h, eight_kings) for s, h in hands.items()}
    raise ValueError(f"Lance desconocido: {lance}")


def lance_winner(
    lance: str, hands: Mapping[int, Sequence[Card]], order: Iterable[int], eight_kings: bool = True
) -> int | None:
    """Asiento que gana el lance; en empate, el más cercano al mano (primero de ``order``).

    ``None`` si nadie juega el lance (nadie tiene pares, o nadie tiene juego)."""
    keys = lance_keys(lance, hands, eight_kings)
    if not keys:
        return None
    return best_seat(keys, order)


def play_points(lance: str, team_hands: Iterable[Sequence[Card]], config: RulesConfig) -> int:
    """Tantos de jugada que cobra una pareja al ganar pares, juego o punto [CONVENCIÓN]."""
    k8 = config.eight_kings
    if lance == "punto":
        return config.punto_points
    total = 0
    for hand in team_hands:
        if lance == "pares":
            kind = pairs(hand, k8).kind
            total += {
                PairsKind.PAR: config.par_points,
                PairsKind.MEDIAS: config.medias_points,
                PairsKind.DUPLES: config.duples_points,
            }.get(kind, 0)
        elif lance == "juego":
            points = total_points(hand, k8)
            if points == 31:
                total += config.juego_31_points
            elif points > 31:
                total += config.juego_points
    return total
