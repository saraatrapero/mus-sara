"""Bots del repo hermano mus-cunef/mus, listos para jugar en MUS.ST.

Cada función crea un bot de musarena y lo envuelve con :class:`~musst.bots.adaptador.PlayerComoBot`:

* ``basico``: reglas sencillas sobre la fuerza de la mano (solo biblioteca estándar).
* ``reglas`` y sus estilos ``reglas_agresivo`` y ``reglas_conservador``: lee la mesa (qué
  manos puede tener cada uno), calcula la probabilidad de ganar cada lance y decide pensando en
  la vaca. Necesita **numpy** (``pip install -e ".[cunef]"``).
* ``inteligente``: red neuronal entrenada con imitación y PPO (también con numpy).

Si numpy no está instalado (por ejemplo, en la web con Pyodide), :func:`disponibles` solo
devuelve ``basico``.
"""

from __future__ import annotations

import importlib.util
import itertools
from collections.abc import Callable

from musst.bots.adaptador import PlayerComoBot
from musst.bots.api import Bot

_semillas = itertools.count(1)


def hay_numpy() -> bool:
    return importlib.util.find_spec("numpy") is not None


def basico(seed: int | None = None) -> Bot:
    from musst.compat.musarena.players.basic_bot import BasicBot

    return PlayerComoBot(BasicBot(seed=_semilla(seed)), name="basico")


def reglas(estilo: str = "equilibrado", seed: int | None = None) -> Bot:
    from musst.compat.musarena.players.heuristic_bot import HeuristicBot

    nombre = "reglas" if estilo == "equilibrado" else f"reglas_{estilo}"
    return PlayerComoBot(HeuristicBot(seed=_semilla(seed), estilo=estilo), name=nombre)


def _semilla(seed: int | None) -> int:
    """Cada bot con su propia semilla (reproducible dentro de un mismo proceso)."""
    return seed if seed is not None else next(_semillas)


def disponibles() -> dict[str, tuple[Callable[[], Bot], str]]:
    """Nombre → (fábrica, descripción) de los bots de mus-cunef que se pueden crear aquí."""
    bots: dict[str, tuple[Callable[[], Bot], str]] = {
        "basico": (basico, "mus-cunef: reglas sencillas sobre la fuerza de la mano"),
    }
    if hay_numpy():
        bots["reglas"] = (reglas, "mus-cunef: lee la mesa y decide pensando en la vaca")
        bots["reglas_agresivo"] = (
            lambda: reglas("agresivo"),
            "mus-cunef: reglas con estilo agresivo",
        )
        bots["reglas_conservador"] = (
            lambda: reglas("conservador"),
            "mus-cunef: reglas con estilo conservador",
        )
    return bots
