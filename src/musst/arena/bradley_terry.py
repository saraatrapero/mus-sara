"""Puntuación Elo con el modelo de Bradley-Terry (traído de mus-cunef/mus, ``torneo.py``).

En Bradley-Terry cada participante tiene una fuerza ``f`` y la probabilidad de que A gane a B es
``fA / (fA + fB)``. Las fuerzas se ajustan **con todos los enfrentamientos a la vez** (algoritmo
MM de Hunter), así que, a diferencia del % de victorias, se tiene en cuenta contra quién se ganó;
y a diferencia del Elo "partida a partida", no depende del orden en que se jugaron.

Se expresa en la escala de Elo: media 1500, y 200 puntos de diferencia ≈ 76 % de victorias.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

Cruces = Mapping[tuple[str, str], tuple[int, int]]
"""(a, b) → (victorias de a contra b, partidas entre los dos). Basta con una de las dos claves."""


def victorias(cruces: Cruces, a: str, b: str) -> tuple[int, int]:
    """(victorias de a contra b, partidas entre los dos)."""
    if (a, b) in cruces:
        return cruces[(a, b)]
    if (b, a) in cruces:
        v, n = cruces[(b, a)]
        return n - v, n
    return 0, 0


def elo(participantes: Sequence[str], cruces: Cruces, iteraciones: int = 500) -> dict[str, float]:
    """Elo de Bradley-Terry de cada participante.

    A cada cruce se le suma media victoria a cada lado (un "prior" suave), para que quien no gane
    nunca no tenga fuerza cero (−∞ en Elo) y el ajuste siempre converja.
    """
    if not participantes:
        return {}
    fuerza = dict.fromkeys(participantes, 1.0)
    for _ in range(iteraciones):
        nueva = {}
        for i in participantes:
            ganadas = denominador = 0.0
            for j in participantes:
                if i == j:
                    continue
                v, n = victorias(cruces, i, j)
                ganadas += v + 0.5
                denominador += (n + 1) / (fuerza[i] + fuerza[j])
            nueva[i] = ganadas / denominador if denominador else 1.0
        media = math.exp(sum(math.log(f) for f in nueva.values()) / len(nueva))
        fuerza = {k: f / media for k, f in nueva.items()}
    return {k: 1500 + 400 * math.log10(f) for k, f in fuerza.items()}


def margen_95(victorias_: int, partidas: int) -> float:
    """Margen de error al 95 % del % de victorias (aproximación normal)."""
    if partidas == 0:
        return 0.0
    p = victorias_ / partidas
    return 1.96 * math.sqrt(p * (1 - p) / partidas)
