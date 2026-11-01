"""Fuerza de una mano: probabilidad de ganar a una mano rival al azar en cada lance.

Sirve a los bots para decidir (el heurístico la usa directamente y el bot entrenado podrá usarla
como característica de entrada).

Cómo se calcula: a 8 reyes, todo lo que importa de una mano (grande, chica, pares, juego y punto)
depende solo de los **rangos** de sus cartas (el 3 vale como el rey y el 2 como el as). Solo hay
330 combinaciones de 4 rangos, así que se pueden enumerar todas, cada una con su peso (cuántas
manos reales de 4 cartas le corresponden en la baraja de 40). Con eso la fuerza es exacta y se
calcula al instante.

Simplificación: no se descuentan las cartas propias de la baraja (el rival se trata como una
mano al azar de las 40 cartas). El error es pequeño y el cálculo queda independiente de la mano.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter
from functools import cache
from itertools import accumulate, combinations_with_replacement
from math import comb, prod

from musst.compat.musarena.cards import Carta, Palo
from musst.compat.musarena.hands import Lance, Mano, clave, tiene_juego, tiene_pares

#: Rangos distintos a 8 reyes y cuántas cartas de la baraja hay de cada uno.
_COPIAS = {1: 8, 4: 4, 5: 4, 6: 4, 7: 4, 10: 4, 11: 4, 12: 8}

# Qué manos rivales cuentan en cada lance: en pares y juego solo apuestan quienes tienen la
# jugada, y al punto solo se juega si nadie tiene juego.
_CONDICION = {
    Lance.GRANDE: lambda m: True,
    Lance.CHICA: lambda m: True,
    Lance.PARES: tiene_pares,
    Lance.JUEGO: tiene_juego,
    Lance.PUNTO: lambda m: not tiene_juego(m),
}


def _manos_tipo() -> list[tuple[list[Carta], int]]:
    """Las 330 combinaciones de rangos, cada una con su número de manos reales."""
    manos = []
    for rangos in combinations_with_replacement(sorted(_COPIAS), 4):
        peso = prod(comb(_COPIAS[r], n) for r, n in Counter(rangos).items())
        manos.append(([Carta(r, Palo.OROS) for r in rangos], peso))
    return manos


@cache
def _tabla(lance: Lance) -> tuple[list[tuple[int, ...]], list[int], int]:
    """Claves ordenadas de las manos rivales posibles y sus pesos acumulados."""
    condicion = _CONDICION[lance]
    pares = sorted((clave(lance, m), peso) for m, peso in _manos_tipo() if condicion(m))
    claves = [k for k, _ in pares]
    acumulados = list(accumulate(peso for _, peso in pares))
    return claves, acumulados, acumulados[-1]


def fuerza(lance: Lance, mano: Mano) -> float:
    """Probabilidad (0-1) de ganar a una mano rival al azar en ``lance``; los empates cuentan 1/2.

    En pares, juego y punto el rival se elige solo entre las manos que juegan ese lance
    (con pares, con juego o sin juego, respectivamente).
    """
    claves, acumulados, total = _tabla(lance)
    k = clave(lance, mano)
    i, j = bisect_left(claves, k), bisect_right(claves, k)
    peores = acumulados[i - 1] if i > 0 else 0
    empates = (acumulados[j - 1] if j > 0 else 0) - peores
    return (peores + empates / 2) / total
