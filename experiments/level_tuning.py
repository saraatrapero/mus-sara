"""Ajuste de niveles: cada variante juega contra un rival fijo (mus duplicado).

python -m experiments.level_tuning --seeds 75
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import replace

from experiments.common import duplicate_game, parallel_map, wilson, write_csv
from musst.agents.orchestrator import LEVELS, AgentBot, LevelConfig, Orchestrator
from musst.bots.api import Bot
from musst.bots.builtin import SimpleBot

PRO, MED = LEVELS["profesional"], LEVELS["medio"]
CONFIGS: dict[str, LevelConfig] = {
    "medio_actual": MED,
    "pro_actual": PRO,
    "pro+pareja": replace(PRO, team_bonus=True),
    "pro+descarte": replace(PRO, discard_draws=30),
    "pro+ambos": replace(PRO, team_bonus=True, discard_draws=30),
    "pro+lectura": replace(PRO, read_all=True),
    "pro+todo": replace(PRO, read_all=True, team_bonus=True, discard_draws=30),
    "medio_intermedio": replace(MED, discard_draws=0, noise=0.12, samples=90, samples_deep=90),
    "medio_nuevo": replace(
        MED, read_bets=False, discard_draws=0, noise=0.08, samples=120, samples_deep=120
    ),
}
MATCHES = [
    ("pro_actual", "medio_actual"),
    ("pro+pareja", "medio_actual"),
    ("pro+descarte", "medio_actual"),
    ("pro+ambos", "medio_actual"),
    ("medio_nuevo", "medio_actual"),
    ("medio_nuevo", "sencillo"),
    ("pro+lectura", "medio_actual"),
    ("pro+todo", "medio_actual"),
    ("pro+ambos", "medio_intermedio"),
    ("medio_intermedio", "sencillo"),
]


def make(name: str) -> Callable[[int], Bot]:
    if name == "sencillo":
        return SimpleBot

    def factory(seed: int) -> AgentBot:
        cfg = CONFIGS[name]
        bot = AgentBot("profesional" if cfg.learn else "medio", seed)
        bot.level = cfg
        bot.orchestrator = Orchestrator(cfg)
        bot.name = name
        return bot

    return factory


def _job(args: tuple[str, str, int]) -> tuple[str, str, int, int, int]:
    a, b, seed = args
    wins, n, diff = duplicate_game(make(a), make(b), seed)
    return a, b, wins, n, diff


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=75)
    parser.add_argument("--seed", type=int, default=99)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--only", nargs="*", help="índices de MATCHES a jugar")
    args = parser.parse_args()
    matches = [MATCHES[int(i)] for i in args.only] if args.only else MATCHES
    jobs = [(a, b, args.seed + i * 7) for a, b in matches for i in range(args.seeds)]
    results = parallel_map(_job, jobs, args.workers)
    rows = []
    for a, b in matches:
        mine = [r for r in results if r[0] == a and r[1] == b]
        wins, n, diff = (sum(r[i] for r in mine) for i in (2, 3, 4))
        lo, hi = wilson(wins, n)
        rows.append(
            {
                "a": a,
                "b": b,
                "games": n,
                "wins_a": wins,
                "rate": round(wins / n, 3),
                "ci_low": round(lo, 3),
                "ci_high": round(hi, 3),
                "diff": round(diff / n, 2),
            }
        )
        print(
            f"{a:>14} vs {b:<13} {wins:>4}/{n} = {wins / n:.1%}  IC95 [{lo:.1%}, {hi:.1%}]  Δtantos {diff / n:+.1f}",
            flush=True,
        )
    print("CSV:", write_csv("level_tuning.csv", rows))


if __name__ == "__main__":
    main()
