"""Los 330 tipos de mano y sus propiedades precalculadas.

A 8 reyes, todo lo que importa de una mano (grande, chica, pares, juego y punto) depende solo
de los **rangos** de sus cartas: el 3 vale como el rey y el 2 como el as. Por eso las 91.390
manos posibles de 4 cartas se agrupan en solo **330 tipos** (multiconjuntos de 4 rangos de los
8 que hay). Trabajar con tipos en lugar de manos hace que el análisis sea exacto y rápido.

Para cada tipo se precalcula, en tablas (arrays de numpy) indexadas por su número (0-329):

- rangos, pares, puntos, bonus de pares y de juego;
- su **nivel** en cada lance: posición de su clave entre todas las claves posibles (0 es la
  peor). Comparar niveles equivale a comparar manos;
- su **fuerza** en cada lance contra una mano rival al azar (ver :mod:`musst.compat.musarena.fuerza`).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from functools import cache
from itertools import combinations_with_replacement
from math import comb, prod

import numpy as np

from musst.compat.musarena.cards import Carta, Palo
from musst.compat.musarena.fuerza import fuerza
from musst.compat.musarena.hands import Lance, TipoPares, bonus_juego, clave, puntos, tipo_pares

#: Rangos distintos a 8 reyes y cuántas cartas de la baraja hay de cada uno.
COPIAS: dict[int, int] = {1: 8, 4: 4, 5: 4, 6: 4, 7: 4, 10: 4, 11: 4, 12: 8}
RANGOS: tuple[int, ...] = tuple(sorted(COPIAS))

#: Rangos de cada tipo de mano, de menor a mayor.
TIPOS: tuple[tuple[int, ...], ...] = tuple(combinations_with_replacement(RANGOS, 4))
N_TIPOS = len(TIPOS)
INDICE: dict[tuple[int, ...], int] = {rangos: i for i, rangos in enumerate(TIPOS)}

_MANOS = [[Carta(r, Palo.OROS) for r in rangos] for rangos in TIPOS]


def _tabla(valores: Iterable[object], dtype: type) -> np.ndarray:
    array = np.array(list(valores), dtype=dtype)
    array.setflags(write=False)  # las tablas son constantes: que nadie las cambie por error
    return array


TIPO_PARES: tuple[TipoPares, ...] = tuple(tipo_pares(m) for m in _MANOS)
TIENE_PARES = _tabla((t is not TipoPares.NADA for t in TIPO_PARES), bool)
BONUS_PARES = _tabla((int(t) for t in TIPO_PARES), float)
PUNTOS = _tabla((puntos(m) for m in _MANOS), int)
TIENE_JUEGO = _tabla((p >= 31 for p in PUNTOS), bool)
BONUS_JUEGO = _tabla((bonus_juego(m) for m in _MANOS), float)


def _niveles(lance: Lance) -> tuple[np.ndarray, int]:
    claves = [clave(lance, m) for m in _MANOS]
    orden = {k: i for i, k in enumerate(sorted(set(claves)))}
    return _tabla((orden[k] for k in claves), int), len(orden)


_NIVELES_Y_CUANTOS = {lance: _niveles(lance) for lance in Lance}

#: Nivel de cada tipo en cada lance (mayor es mejor) y número de niveles distintos.
NIVEL: dict[Lance, np.ndarray] = {lance: n for lance, (n, _) in _NIVELES_Y_CUANTOS.items()}
N_NIVELES: dict[Lance, int] = {lance: c for lance, (_, c) in _NIVELES_Y_CUANTOS.items()}

#: Fuerza de cada tipo en cada lance contra una mano al azar (0-1).
FUERZA: dict[Lance, np.ndarray] = {
    lance: _tabla((fuerza(lance, m) for m in _MANOS), float) for lance in Lance
}


def indice_de(cartas: Iterable[Carta]) -> int:
    """Número de tipo de una mano de 4 cartas."""
    return INDICE[tuple(sorted(c.rango for c in cartas))]


def restantes(conocidas: Iterable[Carta] = ()) -> dict[int, int]:
    """Cuántas cartas de cada rango quedan sin contar las ``conocidas``."""
    quedan = dict(COPIAS)
    for c in conocidas:
        quedan[c.rango] -= 1
    return quedan


def peso(rangos: Sequence[int], quedan: dict[int, int]) -> int:
    """Número de formas de sacar esos rangos de las cartas que ``quedan``."""
    return prod(comb(quedan[r], n) for r, n in Counter(rangos).items())


def pesos(quedan: dict[int, int] | None = None) -> np.ndarray:
    """Número de manos reales de cada tipo que se pueden formar con las cartas que ``quedan``."""
    quedan = COPIAS if quedan is None else quedan
    return np.array([peso(rangos, quedan) for rangos in TIPOS], dtype=float)


#: Cuántas manos reales hay de cada tipo en la baraja completa.
PESOS_BASE = _tabla(pesos(), float)


@cache
def _pesos_sin(rangos: tuple[int, ...]) -> np.ndarray:
    quedan = dict(COPIAS)
    for r in rangos:
        quedan[r] -= 1
    return _tabla(pesos(quedan), float)


def pesos_sin(cartas: Iterable[Carta]) -> np.ndarray:
    """Manos reales de cada tipo que quedan sin las ``cartas`` conocidas (memorizado, de solo
    lectura: haz ``.copy()`` para modificarlo)."""
    return _pesos_sin(tuple(sorted(c.rango for c in cartas)))

#: Combinaciones de ``n`` rangos que se pueden robar (para evaluar descartes).
ROBOS: dict[int, tuple[tuple[int, ...], ...]] = {
    n: tuple(combinations_with_replacement(RANGOS, n)) for n in range(1, 5)
}
