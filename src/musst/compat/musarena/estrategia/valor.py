"""Valor de una mano antes de los lances: sirve para decidir el mus y elegir el descarte.

El **valor** resume en un número lo prometedora que es una mano en los cuatro lances. Se basa en
la fuerza de la mano en cada lance, elevada al cuadrado porque en la mesa hay que ganar a **dos**
rivales, y suma lo que se cobra seguro por tener pares o juego:

    valor = 2·G² + 2·C² + [pares: bonus + 2,5·P²] + [juego: bonus + 2,5·J²  |  sin juego: Pt²]

donde G, C, P, J y Pt son las fuerzas en grande, chica, pares, juego y punto. Los pesos son
heurísticos y se pueden ajustar (serán un buen punto de partida para el bot entrenado).

El **percentil** dice qué parte de las manos posibles tiene menos valor (0 = la peor, 1 = la
mejor). Es más fácil de interpretar que el valor en bruto: "corto con manos del 60 % mejor".
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from functools import cache

import numpy as np

from musst.compat.musarena.cards import Carta
from musst.compat.musarena.estrategia.tipos import (
    BONUS_JUEGO,
    BONUS_PARES,
    FUERZA,
    INDICE,
    PESOS_BASE,
    ROBOS,
    TIENE_JUEGO,
    TIENE_PARES,
    peso,
    restantes,
)
from musst.compat.musarena.hands import Lance

#: Valor de cada tipo de mano.
VALOR: np.ndarray = (
    2.0 * FUERZA[Lance.GRANDE] ** 2
    + 2.0 * FUERZA[Lance.CHICA] ** 2
    + np.where(TIENE_PARES, BONUS_PARES + 2.5 * FUERZA[Lance.PARES] ** 2, 0.0)
    + np.where(TIENE_JUEGO, BONUS_JUEGO + 2.5 * FUERZA[Lance.JUEGO] ** 2,
               FUERZA[Lance.PUNTO] ** 2)
)
VALOR.setflags(write=False)


def _percentiles() -> np.ndarray:
    total = PESOS_BASE.sum()
    peores = np.array([PESOS_BASE[VALOR < v].sum() for v in VALOR])
    iguales = np.array([PESOS_BASE[VALOR == v].sum() for v in VALOR])
    resultado = (peores + iguales / 2) / total
    resultado.setflags(write=False)
    return resultado


#: Percentil de cada tipo de mano (qué parte de las manos reales vale menos).
PERCENTIL: np.ndarray = _percentiles()


def valor_tras_descarte(cartas: Sequence[Carta], descartadas: Iterable[Carta]) -> float:
    """Valor medio de la mano después de tirar ``descartadas`` y robar otras tantas.

    Se promedia sobre todas las combinaciones de rangos que se pueden robar, cada una con su
    probabilidad según las cartas que quedan (se descuentan las cuatro propias).
    """
    tiradas = set(descartadas)
    mano = tuple(sorted(c.rango for c in cartas))
    guardadas = tuple(sorted(c.rango for c in cartas if c not in tiradas))
    return _valor_tras(mano, guardadas)


@cache
def _valor_tras(mano: tuple[int, ...], guardadas: tuple[int, ...]) -> float:
    """Igual que :func:`valor_tras_descarte`, por rangos (así se puede memorizar)."""
    n = len(mano) - len(guardadas)
    if n == 0:
        return float(VALOR[INDICE[mano]])
    quedan = dict(restantes())
    for r in mano:
        quedan[r] -= 1
    total = suma = 0.0
    for robo in ROBOS[n]:
        w = peso(robo, quedan)
        if w:
            total += w
            suma += w * VALOR[INDICE[tuple(sorted(guardadas + robo))]]
    return float(suma / total)
