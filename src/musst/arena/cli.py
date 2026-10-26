"""CLI del torneo: ``musst-arena --games 10 --seed 2026 --out scoreboard_out``."""

from __future__ import annotations

import argparse
import sys

from musst.arena.scoreboard import to_markdown, write_scoreboard
from musst.arena.tournament import Participant, run_tournament
from musst.bots.registry import all_entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Torneo automático de bots de MUS.ST")
    parser.add_argument("--games", type=int, default=10, help="seeds por emparejamiento")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", default="scoreboard_out")
    parser.add_argument("--only", nargs="*", help="limitar a estos bots")
    parser.add_argument("--exclude", nargs="*", default=[], help="excluir bots")
    parser.add_argument("--time-limit", type=float, default=2.0)
    args = parser.parse_args(argv)

    entries = [e for e in all_entries(sandboxed=True) if e.name not in args.exclude]
    if args.only:
        entries = [e for e in entries if e.name in args.only]
    participants = [Participant(e.name, e.factory, e.author, e.version) for e in entries]
    if len(participants) < 2:
        print("Se necesitan al menos dos bots", file=sys.stderr)
        return 1
    result = run_tournament(
        participants,
        games_per_pair=args.games,
        seed=args.seed,
        time_limit_s=args.time_limit,
        progress=lambda msg: print(msg, file=sys.stderr),
    )
    out = write_scoreboard(result, args.out)
    print(to_markdown(result))
    print(f"Scoreboard escrito en {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
