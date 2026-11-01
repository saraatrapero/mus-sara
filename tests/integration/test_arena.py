"""Torneo y scoreboard (Req 4.1, 4.2)."""

import json

from musst.arena.scoreboard import write_scoreboard
from musst.arena.tournament import Participant, run_tournament
from musst.bots.api import Bot
from musst.bots.builtin import RandomBot, SimpleBot


class Broken(Bot):
    name = "roto"

    def decide(self, observation):
        raise RuntimeError("fallo")


def test_torneo_sobrevive_a_un_bot_roto_y_genera_clasificacion(tmp_path):
    parts = [
        Participant("sencillo", lambda: SimpleBot()),
        Participant("random", lambda: RandomBot()),
        Participant("roto", Broken),
    ]
    result = run_tournament(parts, games_per_pair=2, seed=1)
    ranking = result.ranking()
    assert ranking[-1].name == "roto"
    roto = next(s for s in result.standings if s.name == "roto")
    assert roto.wins == 0 and roto.errors == roto.games == 8
    assert sum(s.games for s in result.standings) == 2 * len(result.games)
    out = write_scoreboard(result, tmp_path)
    data = json.loads((out / "scoreboard.json").read_text())
    assert data["ranking"][0]["name"] in ("sencillo", "random")
    assert (out / "index.html").read_text().startswith("<!doctype html>")


def test_torneo_reproducible():
    parts = [Participant("a", lambda: SimpleBot(1)), Participant("b", lambda: RandomBot(2))]
    r1 = run_tournament(parts, games_per_pair=2, seed=5)
    r2 = run_tournament(parts, games_per_pair=2, seed=5)
    assert [(g.winner, g.score) for g in r1.games] == [(g.winner, g.score) for g in r2.games]


def test_clasificacion_por_bradley_terry_con_cruces_y_markdown(tmp_path):
    from musst.arena.cli import main
    from musst.arena.scoreboard import to_markdown

    parts = [
        Participant("sencillo", lambda: SimpleBot()),
        Participant("random", lambda: RandomBot()),
    ]
    result = run_tournament(parts, games_per_pair=3, seed=2)
    cruces = result.cruces()
    assert sum(n for _, n in cruces.values()) == len(result.games) == 6
    ranking = result.ranking()
    assert ranking[0].elo >= ranking[1].elo
    md = to_markdown(result)
    assert "Cruces" in md and "`sencillo`" in md
    # La CLI con los nombres de mus-cunef escribe Markdown y JSON donde se le dice.
    code = main(
        [
            "-n",
            "1",
            "--participantes",
            "sencillo,random",
            "--out",
            str(tmp_path / "sb"),
            "--markdown",
            str(tmp_path / "c.md"),
            "--json",
            str(tmp_path / "c.json"),
        ]
    )
    assert code == 0
    data = json.loads((tmp_path / "c.json").read_text())
    assert {r["name"] for r in data["ranking"]} == {"sencillo", "random"}
    assert data["head_to_head"][0]["games"] == 2
