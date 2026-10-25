"""Adaptación: bot profesional con memoria frente a perfiles sintéticos.

Compara el bot profesional *sin memoria* (aprende de cero en cada partida) con el mismo bot
*con memoria persistente* frente a un rival farolero y otro conservador, y mide el error del
PlayerModel a lo largo de las partidas.

    python -m experiments.adaptation --games 30 --seed 7
"""

from __future__ import annotations

import argparse

from experiments.common import write_csv
from musst import play_game
from musst.agents.orchestrator import ProBot
from musst.learning.player_model import PRIORS
from musst.learning.synthetic import SyntheticPlayer
from musst.learning.updater import Learner

PROFILES = {
    "farolero": dict(bluff=0.8, risk_tolerance=0.3),
    "conservador": dict(bluff=0.0, risk_tolerance=0.05, value_threshold=0.85),
}


def run(profile: str, games: int, seed: int, memory: bool) -> list[dict[str, object]]:
    learner = Learner()
    rows = []
    wins = 0
    for g in range(games):
        lrn = learner if memory else Learner()
        rival = lambda s: SyntheticPlayer(seed=s, **PROFILES[profile])  # noqa: E731
        bots = [
            ProBot(seed + g, lrn),
            rival(seed + g),
            ProBot(seed + g + 1, lrn),
            rival(seed + g + 1),
        ]
        res = play_game(bots, seed=seed + g, names=["pro", "rival", "pro", "rival"]).result
        wins += res.winner == 0
        est = lrn.long_model("rival").estimate("bluff_frequency")
        rows.append(
            {
                "profile": profile,
                "memory": memory,
                "game": g + 1,
                "win_rate_so_far": round(wins / (g + 1), 3),
                "bluff_estimate": round(est.value, 3),
                "confidence": round(est.confidence, 3),
                "prior": PRIORS["bluff_frequency"],
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=30)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    rows: list[dict[str, object]] = []
    for profile in PROFILES:
        for memory in (False, True):
            r = run(profile, args.games, args.seed, memory)
            rows += r
            last = r[-1]
            print(
                f"{profile:<12} memoria={memory!s:<5} victorias={last['win_rate_so_far']:.0%} "
                f"P(farol) estimada={last['bluff_estimate']:.2f} (conf. {last['confidence']:.2f})"
            )
    print("CSV:", write_csv("adaptation.csv", rows))


if __name__ == "__main__":
    main()
