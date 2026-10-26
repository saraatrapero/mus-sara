"""Utilidades comunes: duelos en mus duplicado con IC de Wilson y ejecución en paralelo."""

from __future__ import annotations

import csv
import math
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from musst import play_game
from musst.bots.api import Bot

RESULTS = Path(__file__).parent / "results"


def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def duplicate_game(
    a: Callable[[int], Bot], b: Callable[[int], Bot], seed: int
) -> tuple[int, int, int]:
    """Juega la seed en ambos sentidos. Devuelve (victorias de A, partidas, diferencia de tantos)."""
    wins = 0
    diff = 0
    for swap in (False, True):
        first, second = (b, a) if swap else (a, b)
        bots = [first(seed), second(seed + 1), first(seed + 2), second(seed + 3)]
        res = play_game(bots, seed=seed, mode="tournament").result
        a_team = 1 if swap else 0
        wins += res.winner == a_team
        diff += res.score[a_team] - res.score[1 - a_team]
    return wins, 2, diff


def write_csv(name: str, rows: list[dict[str, object]]) -> Path:
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / name
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def parallel_map(fn, items, workers: int = 8):  # type: ignore[no-untyped-def]
    with ProcessPoolExecutor(workers) as ex:
        return list(ex.map(fn, items))
