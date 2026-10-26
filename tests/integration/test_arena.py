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
