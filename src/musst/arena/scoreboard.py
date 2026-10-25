"""Exportación del scoreboard a JSON, Markdown y HTML estático (Req 4.2)."""

from __future__ import annotations

import html
import json
from pathlib import Path

from musst.arena.tournament import TournamentResult


def to_markdown(result: TournamentResult) -> str:
    lines = [
        "| # | Bot | Partidas | Victorias | Derrotas | % Victorias (IC 95 %) | Tantos ± / partida | Errores | Elo |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, s in enumerate(result.ranking(), 1):
        low, high = s.wilson()
        diff = (s.points_for - s.points_against) / s.games if s.games else 0
        lines.append(
            f"| {i} | {s.name} | {s.games} | {s.wins} | {s.losses} | "
            f"{s.win_rate:.0%} ({low:.0%}–{high:.0%}) | {diff:+.1f} | {s.errors} | {s.elo:.0f} |"
        )
    return "\n".join(lines) + "\n"


def to_html(result: TournamentResult) -> str:
    data = result.to_dict()
    rows = []
    for i, s in enumerate(data["ranking"], 1):
        low, high = s["win_rate_ci"]
        rows.append(
            "<tr>"
            f"<td>{i}</td><td>{html.escape(s['name'])}</td><td>{s['games']}</td>"
            f"<td>{s['wins']}</td><td>{s['losses']}</td>"
            f"<td>{s['win_rate']:.0%} <small>({low:.0%}–{high:.0%})</small></td>"
            f"<td>{s['point_diff_per_game']:+.1f}</td><td>{s['errors']}</td><td>{s['elo']:.0f}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MUS.ST — Clasificación de bots</title>
<style>
:root{{--bg:#f6f1e7;--fg:#1f2a24;--accent:#7a1f2b;--line:#d8cdb8;--card:#fffdf8}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141a17;--fg:#ece5d6;--accent:#d08a93;--line:#34403a;--card:#1b2420}}}}
body{{margin:0;font-family:Georgia,'Times New Roman',serif;background:var(--bg);color:var(--fg)}}
main{{max-width:960px;margin:0 auto;padding:24px 16px}}
h1{{color:var(--accent);margin:0 0 4px}} p{{margin:4px 0 16px}}
.wrap{{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:8px}}
table{{border-collapse:collapse;width:100%;font-family:system-ui,sans-serif;font-size:14px}}
th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}
th:nth-child(2),td:nth-child(2){{text-align:left}}
</style></head><body><main>
<h1>MUS.ST · Bot Arena</h1>
<p>Generado {html.escape(data["generated_at"])} · seed {data["seed"]} ·
{data["games_per_pair"]} seeds por emparejamiento (mus duplicado) · {len(data["games"])} partidas</p>
<div class="wrap"><table>
<thead><tr><th>#</th><th>Bot</th><th>Partidas</th><th>Victorias</th><th>Derrotas</th>
<th>% Victorias</th><th>Tantos ±/partida</th><th>Errores</th><th>Elo</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
</main></body></html>
"""


def write_scoreboard(result: TournamentResult, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scoreboard.json").write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    (out / "scoreboard.md").write_text(to_markdown(result))
    (out / "index.html").write_text(to_html(result))
    return out
