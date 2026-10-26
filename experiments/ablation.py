"""Ablación del bot profesional: ¿qué diferencia con el medio ayuda y cuál resta?

python -m experiments.ablation --seeds 75

Cada variante es el profesional con un solo cambio y juega contra el bot medio (mus duplicado).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import replace

from experiments.common import duplicate_game, parallel_map, wilson, write_csv
from musst.agents.orchestrator import LEVELS, AgentBot, MediumBot, Orchestrator

PRO = LEVELS["profesional"]
VARIANTS = {
    "profesional": PRO,
    "sin_farol": replace(PRO, agents=tuple(a for a in PRO.agents if a != "farol")),
    "sin_pareja": replace(PRO, agents=tuple(a for a in PRO.agents if a != "pareja")),
    "sin_comportamiento": replace(
        PRO, agents=tuple(a for a in PRO.agents if a != "comportamiento")
    ),
    "riesgo_medio": replace(PRO, risk_aversion=LEVELS["medio"].risk_aversion),
    "muestras_medio": replace(
        PRO, samples=LEVELS["medio"].samples, samples_deep=LEVELS["medio"].samples_deep
    ),
}


def make(variant: str) -> Callable[[int], AgentBot]:
    def factory(seed: int) -> AgentBot:
        bot = AgentBot("profesional", seed)
        bot.level = VARIANTS[variant]
        bot.orchestrator = Orchestrator(VARIANTS[variant])
        bot.name = variant
        return bot

    return factory


def _job(args: tuple[str, int]) -> tuple[str, int, int, int]:
    variant, seed = args
    wins, n, diff = duplicate_game(make(variant), MediumBot, seed)
    return variant, wins, n, diff


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=75)
    parser.add_argument("--seed", type=int, default=31)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    jobs = [(v, args.seed + i * 7) for v in VARIANTS for i in range(args.seeds)]
    results = parallel_map(_job, jobs, args.workers)
    rows = []
    for v in VARIANTS:
        mine = [r for r in results if r[0] == v]
        wins, n, diff = (sum(r[i] for r in mine) for i in (1, 2, 3))
        lo, hi = wilson(wins, n)
        rows.append(
            {
                "variante": v,
                "games": n,
                "wins_vs_medio": wins,
                "win_rate": round(wins / n, 3),
                "ci_low": round(lo, 3),
                "ci_high": round(hi, 3),
                "points_diff_per_game": round(diff / n, 2),
            }
        )
        print(
            f"{v:>20} {wins:>4}/{n} = {wins / n:.1%}  IC95 [{lo:.1%}, {hi:.1%}]  Δtantos {diff / n:+.1f}"
        )
    print("CSV:", write_csv("ablation.csv", rows))


if __name__ == "__main__":
    main()
