"""Escalera de niveles: ¿la diferencia entre bots es real y medible?

python -m experiments.level_ladder --seeds 60 --seed 12345
python -m experiments.level_ladder --seeds 250 --pair medio profesional
"""

from __future__ import annotations

import argparse
import itertools

from experiments.common import duplicate_game, parallel_map, wilson, write_csv
from musst.bots.builtin import MediumBot, ProBot, RandomBot, SimpleBot

BOTS = {"random": RandomBot, "sencillo": SimpleBot, "medio": MediumBot, "profesional": ProBot}


def _job(args: tuple[str, str, int]) -> tuple[str, str, int, int, int]:
    a, b, seed = args
    wins, n, diff = duplicate_game(BOTS[a], BOTS[b], seed)
    return a, b, wins, n, diff


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=60)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--pair",
        nargs=2,
        metavar=("A", "B"),
        help="solo este emparejamiento (p. ej. medio profesional)",
    )
    args = parser.parse_args()
    pairs = [tuple(args.pair)] if args.pair else list(itertools.combinations(BOTS, 2))
    jobs = [(a, b, args.seed + i * 7) for a, b in pairs for i in range(args.seeds)]
    results = parallel_map(_job, jobs, args.workers)
    rows = []
    for a, b in pairs:
        mine = [r for r in results if r[0] == a and r[1] == b]
        wins = sum(r[2] for r in mine)
        n = sum(r[3] for r in mine)
        diff = sum(r[4] for r in mine)
        lo, hi = wilson(wins, n)
        rows.append(
            {
                "bot_a": a,
                "bot_b": b,
                "games": n,
                "wins_a": wins,
                "win_rate_a": round(wins / n, 3),
                "ci_low": round(lo, 3),
                "ci_high": round(hi, 3),
                "points_diff_per_game": round(diff / n, 2),
            }
        )
        print(
            f"{a:>12} vs {b:<12} {wins:>4}/{n} = {wins / n:.1%}  IC95 [{lo:.1%}, {hi:.1%}]  Δtantos {diff / n:+.1f}"
        )
    print(
        "CSV:",
        write_csv(
            "level_ladder_" + "_".join(args.pair) + ".csv" if args.pair else "level_ladder.csv",
            rows,
        ),
    )


if __name__ == "__main__":
    main()
