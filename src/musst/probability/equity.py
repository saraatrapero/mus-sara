"""Equidad de partida: P(ganar la partida) según los tantos que faltan a cada pareja.

No es lo mismo ganar 2 tantos a 5-5 que a 38-35: lo que importa es cuánto cambia la
probabilidad de **ganar la partida**. Se modela el resto de la partida como una cadena de
Markov sobre (a, b) = tantos que me faltan, tantos que les faltan. En cada jugada las parejas
ganan (x, y) tantos con probabilidad D(x, y)::

    E(a, b) = Σ_{x,y} D(x, y) · f(a − x, b − y)

    f(a', b') = 1    si a' ≤ 0 < b'        (llego yo)
              = 0    si b' ≤ 0 < a'        (llegan ellos)
              = 1/2  si a' ≤ 0 y b' ≤ 0    (los dos en la misma jugada: el orden de los lances
                                            no está en D; se toma 1/2, supuesto del modelo)
              = E(a', b') en otro caso

Si D(0, 0) > 0, E(a, b) aparece a los dos lados y se despeja: E = (Σ_{(x,y)≠(0,0)} …)/(1 − D(0,0)).

D se **mide** (no se supone): frecuencias de tantos por jugada en partidas del motor entre
bots de nivel medio, generadas con ``scripts/round_points.py`` (semillas fijas; ver
``round_points_data.py``). Se simetriza, D(x, y) = D(y, x), para que no dependa del asiento.
"""

from __future__ import annotations

from functools import lru_cache

from musst.probability.round_points_data import COUNTS


@lru_cache(maxsize=1)
def round_distribution() -> tuple[tuple[int, int, float], ...]:
    """D(x, y) simetrizada: tuplas (x, y, probabilidad)."""
    sym: dict[tuple[int, int], float] = {}
    for (x, y), n in COUNTS.items():
        sym[(x, y)] = sym.get((x, y), 0.0) + n
        sym[(y, x)] = sym.get((y, x), 0.0) + n
    total = sum(sym.values())
    return tuple((x, y, n / total) for (x, y), n in sorted(sym.items()))


@lru_cache(maxsize=4)
def _table(size: int) -> tuple[tuple[float, ...], ...]:
    dist = round_distribution()
    p00 = sum(p for x, y, p in dist if x == 0 and y == 0)
    rest = [(x, y, p) for x, y, p in dist if (x, y) != (0, 0)]
    e = [[0.0] * (size + 1) for _ in range(size + 1)]
    for a in range(1, size + 1):
        for b in range(1, size + 1):
            acc = 0.0
            for x, y, p in rest:
                a2, b2 = a - x, b - y
                if a2 <= 0:
                    acc += p * (0.5 if b2 <= 0 else 1.0)
                elif b2 <= 0:
                    continue
                else:
                    acc += p * e[a2][b2]
            e[a][b] = acc / (1 - p00)
    return tuple(tuple(row) for row in e)


def win_probability(my_left: int, their_left: int) -> float:
    """P(mi pareja gana la partida) cuando me faltan ``my_left`` tantos y a ellos ``their_left``."""
    if my_left <= 0:
        return 0.5 if their_left <= 0 else 1.0
    if their_left <= 0:
        return 0.0
    size = 20
    while size < max(my_left, their_left):
        size *= 2
    return _table(size)[my_left][their_left]


def equity_after(mine: int, theirs: int, target: int, d_mine: int, d_theirs: int) -> float:
    """P(ganar la partida) tras sumar ``d_mine`` y ``d_theirs`` tantos al marcador actual."""
    return win_probability(target - mine - d_mine, target - theirs - d_theirs)
