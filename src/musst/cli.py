"""CLI para jugar una partida sin interfaz: ``musst-play --bots sencillo medio --seed 1``."""

from __future__ import annotations

import argparse

from musst.bots.registry import get_entry
from musst.engine.events import EventKind
from musst.runtime.runner import play_game


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Partida de Mus entre dos parejas de bots")
    parser.add_argument(
        "--bots", nargs=2, default=["sencillo", "medio"], metavar=("PAREJA0", "PAREJA1")
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--verbose", action="store_true", help="mostrar los eventos públicos")
    args = parser.parse_args(argv)
    a, b = (get_entry(name) for name in args.bots)
    bots = [a.factory(), b.factory(), a.factory(), b.factory()]
    match = play_game(bots, seed=args.seed, names=[a.name, b.name, a.name, b.name])
    if args.verbose:
        for e in match.events:
            if e.visible_to(None) and e.kind is not EventKind.DECK_SHUFFLED:
                print(f"[{e.round_no:>2}] {e.kind.value:<16} asiento={e.actor} {e.payload}")
    r = match.result
    print(
        f"seed={match.seed} ganador=pareja {r.winner} ({args.bots[r.winner]}) marcador={r.score} motivo={r.reason}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
