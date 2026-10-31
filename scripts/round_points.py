"""Mide la distribución de tantos por jugada para la equidad de partida (musst.probability.equity).

Juega ``N`` partidas completas entre cuatro bots de nivel *medio* con semillas fijas, cuenta
los tantos que gana cada pareja en cada jugada (eventos ``PointsAwarded``) y escribe la tabla
de frecuencias en ``src/musst/probability/round_points_data.py``. La última jugada de cada
partida se descarta: está cortada por el final del juego.

Uso (reproducible)::

    python scripts/round_points.py 1000 0

(1000 partidas con semillas 0..999). Con varios núcleos se reparte el trabajo, sin cambiar el
resultado (cada partida depende solo de su semilla).
"""

from __future__ import annotations

import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

from musst.agents.orchestrator import MediumBot
from musst.engine.events import EventKind
from musst.runtime.runner import play_game

OUT = Path(__file__).resolve().parents[1] / "src" / "musst" / "probability" / "round_points_data.py"


def rounds_of(seed: int) -> list[tuple[int, int]]:
    bots = [MediumBot(seed * 4 + i) for i in range(4)]
    match = play_game(bots, seed=seed)
    per_round: dict[int, list[int]] = {}
    for e in match.events:
        if e.kind is EventKind.POINTS_AWARDED:
            per_round.setdefault(e.round_no, [0, 0])[e.payload["team"]] += e.payload["points"]
    last = max(per_round, default=0)
    return [(a, b) for r, (a, b) in sorted(per_round.items()) if r != last]


def main(n: int, first_seed: int) -> None:
    with Pool() as pool:
        results = pool.map(rounds_of, range(first_seed, first_seed + n))
    counts = Counter(r for rounds in results for r in rounds)
    total = sum(counts.values())
    lines = [
        '"""Tantos por jugada (pareja 0, pareja 1) medidos con ``scripts/round_points.py``.',
        "",
        "Generado automáticamente: no editar a mano.",
        '"""',
        "",
        f"GAMES = {n}",
        f"FIRST_SEED = {first_seed}",
        f"ROUNDS = {total}",
        'BOTS = "medio"',
        "COUNTS: dict[tuple[int, int], int] = {",
        *(f"    {k}: {v}," for k, v in sorted(counts.items())),
        "}",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{total} jugadas de {n} partidas → {OUT}")


if __name__ == "__main__":
    main(
        int(sys.argv[1]) if len(sys.argv) > 1 else 1000,
        int(sys.argv[2]) if len(sys.argv) > 2 else 0,
    )
