"""CLI del torneo.

``musst-arena --games 10 --seed 2026 --out scoreboard_out`` o, con los nombres de mus-cunef,
``mus-torneo -n 10 --participantes reglas,basico,medio --markdown clasificacion.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from musst.arena.scoreboard import to_markdown, write_scoreboard
from musst.arena.tournament import Participant, run_tournament
from musst.bots.registry import all_entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Torneo automático de bots de MUS.ST")
    parser.add_argument(
        "--games",
        "-n",
        type=int,
        default=10,
        help="repartos por cruce (cada uno se juega dos veces)",
    )
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", default="scoreboard_out")
    parser.add_argument("--only", nargs="*", help="limitar a estos bots")
    parser.add_argument("--participantes", help="lista separada por comas (igual que --only)")
    parser.add_argument("--markdown", help="escribir también la clasificación en este .md")
    parser.add_argument("--json", help="escribir también el resultado en este .json")
    parser.add_argument("--exclude", nargs="*", default=[], help="excluir bots")
    parser.add_argument("--time-limit", type=float, default=2.0)
    args = parser.parse_args(argv)

    if args.participantes:
        args.only = [p.strip() for p in args.participantes.split(",") if p.strip()]
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
    if args.markdown:
        data = result.to_dict()
        cabecera = (
            "# Clasificación de bots\n\n"
            f"{data['generated_at']} · {result.games_per_pair} repartos por cruce, cada uno jugado "
            f"en los dos sentidos (mus duplicado) · semilla {result.seed}. Elo de Bradley-Terry: "
            "media 1500; 200 puntos de diferencia ≈ 76 % de victorias.\n\n"
        )
        Path(args.markdown).write_text(cabecera + to_markdown(result))
    if args.json:
        Path(args.json).write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    print(to_markdown(result))
    print(f"Scoreboard escrito en {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
