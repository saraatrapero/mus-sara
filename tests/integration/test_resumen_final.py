"""Resumen final: cada bot explica qué decidió y por qué; prudencia con el órdago al principio."""

from dataclasses import replace
from pathlib import Path

from musst.bots.builtin.simple import SimpleBot
from musst.bots.toolkit import early_game
from musst.engine.game import MusGame
from musst.engine.observation import build_observation
from musst.server.razones import action_label
from musst.web.backend import LocalBackend


def _play_to_the_end(b, gid, tok):
    for _ in range(3000):
        _, obs = b.handle("GET", f"/api/games/{gid}", None, tok)
        if obs["finished"]:
            return obs
        if obs.get("awaiting_deal"):
            b.handle("POST", f"/api/games/{gid}/deal", None, tok)
            continue
        if obs["turn"] != obs["seat"]:
            b.handle("POST", f"/api/games/{gid}/tick", None, tok)
            continue
        types = [a["type"] for a in obs["legal_actions"]]
        if "cut" in types:
            action = {"type": "cut"}
        elif "discard" in types:
            action = {"type": "discard", "cards": [obs["hand"][0]]}
        elif "pass" in types:
            action = {"type": "pass"}
        else:
            action = {"type": "reject"}  # nunca quiero: la partida no se decide por mí
        b.handle("POST", f"/api/games/{gid}/action", {"action": action}, tok)
    raise AssertionError("la partida no terminó")


def test_el_resumen_explica_las_decisiones_de_los_bots(tmp_path: Path):
    b = LocalBackend(tmp_path)
    _, d = b.handle("POST", "/api/games", {"seed": 7, "target": 20}, None)
    gid, tok = d["game_id"], d["seat_token"]
    _play_to_the_end(b, gid, tok)
    status, a = b.handle("GET", f"/api/games/{gid}/analysis", None, tok)
    assert status == 200
    reasons = a["bot_reasons"]
    assert reasons, "sin explicaciones de los bots"
    assert {r["seat"] for r in reasons} <= {1, 2, 3}
    for r in reasons:
        assert r["reason"] and r["action"] and r["round"] >= 1
        assert r["type"] != "discard"
    # Hay razones de los dos tipos de bot: el compañero sencillo (reglas) y los rivales medios
    # (probabilidades calculadas).
    assert any("/100" in r["reason"] for r in reasons if r["seat"] == 2 and r["type"] != "mus")
    assert any("probabilidad" in r["reason"] for r in reasons if r["seat"] in (1, 3))
    # Método y agentes de cada decisión (para el resumen de cada jugada).
    medio = [r for r in reasons if r["seat"] in (1, 3) and r["type"] != "mus"]
    assert all("Monte Carlo" in r["metodo"] for r in medio)
    assert any(any("Probabilidad" in a for a in r["agentes"]) for r in medio)
    assert all(r["agentes"] == [] for r in reasons if r["seat"] == 2)


def test_entre_jugadas_se_ven_las_razones_de_la_jugada_anterior(tmp_path: Path):
    b = LocalBackend(tmp_path)
    _, d = b.handle("POST", "/api/games", {"seed": 7}, None)
    gid, tok = d["game_id"], d["seat_token"]
    for _ in range(500):
        _, obs = b.handle("GET", f"/api/games/{gid}", None, tok)
        if obs.get("awaiting_deal") and obs["round"] > 1:
            break
        if obs.get("awaiting_deal"):
            b.handle("POST", f"/api/games/{gid}/deal", None, tok)
        elif obs["turn"] != obs["seat"]:
            b.handle("POST", f"/api/games/{gid}/tick", None, tok)
        else:
            types = [a["type"] for a in obs["legal_actions"]]
            act = (
                next({"type": t} for t in ("cut", "pass", "reject", "accept") if t in types)
                if "discard" not in types
                else {"type": "discard", "cards": [obs["hand"][0]]}
            )
            b.handle("POST", f"/api/games/{gid}/action", {"action": act}, tok)
    assert obs.get("awaiting_deal") and obs["round"] > 1
    prev = obs["round_reasons"]
    assert prev and all(r["round"] == obs["round"] - 1 for r in prev)
    assert all("metodo" in r and "agentes" in r for r in prev)


def test_etiquetas_en_castellano():
    assert action_label("BET_2") == "Envido 2"
    assert action_label("ACCEPT_NO_LOSE") == "Quiero"
    assert action_label("ORDAGO") == "¡Órdago!"
    assert action_label({"type": "reject"}) == "No quiero"


def test_prudencia_con_el_ordago_al_principio_de_la_partida():
    obs = build_observation(MusGame(seed=1), 0)
    assert early_game(obs)  # 0-0: es pronto
    assert not early_game(replace(obs, score=(20, 3)))  # una pareja ya va por la mitad

    class Ordago:
        is_ordago = True
        stake = 0
        previous = 1

    bot = SimpleBot(seed=0, noise=0.0)
    # Con 90/100 un sencillo vería un órdago a mitad de partida (umbral 85), pero no al principio.
    action = bot._respond(replace(obs, phase="grande", current_bet=Ordago()), 0.9)
    assert action.type == "reject"
    assert "95/100" in bot.last_reason["regla"]
