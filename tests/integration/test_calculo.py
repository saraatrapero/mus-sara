"""«Ver el cálculo»: probabilidades y valor esperado para la jugada de una persona."""

from pathlib import Path

import pytest

from musst.engine.actions import CutMusAction
from musst.engine.observation import build_observation
from musst.web.backend import LocalBackend


def _lance_on_my_turn(b, gid, tok):
    for _ in range(60):
        _, obs = b.handle("GET", f"/api/games/{gid}", None, tok)
        if obs.get("awaiting_deal"):
            b.handle("POST", f"/api/games/{gid}/deal", None, tok)
            continue
        if obs["turn"] == obs["seat"]:
            if obs["phase"] in ("grande", "chica", "pares", "juego", "punto"):
                return obs
            types = [a["type"] for a in obs["legal_actions"]]
            action = (
                {"type": "cut"}
                if "cut" in types
                else {"type": "discard", "cards": [obs["hand"][0]]}
            )
            b.handle("POST", f"/api/games/{gid}/action", {"action": action}, tok)
    pytest.fail("no llegó a un lance en mi turno")


def test_calculo_de_mi_jugada(tmp_path: Path):
    b = LocalBackend(tmp_path)
    _, d = b.handle("POST", "/api/games", {"seed": 4}, None)
    gid, tok = d["game_id"], d["seat_token"]
    _lance_on_my_turn(b, gid, tok)
    status, r = b.handle("GET", f"/api/games/{gid}/calculo", None, tok)
    assert status == 200
    for key in (
        "estado",
        "informacion_conocida",
        "informacion_desconocida",
        "metodo",
        "probabilidades",
        "acciones",
    ):
        assert key in r
    for p in r["probabilidades"].values():
        post = p["a_posteriori"]
        assert sum(post[k]["p"] for k in ("gana", "pierde", "nadie")) == pytest.approx(
            1.0, abs=2e-4
        )
    assert r["accion_elegida"] in {a["accion"] for a in r["acciones"]}
    # Reproducible: la misma petición en el mismo momento da el mismo cálculo.
    assert b.handle("GET", f"/api/games/{gid}/calculo", None, tok)[1] == r


def test_calculo_sin_turno_solo_probabilidades_y_sin_token_no(tmp_path: Path):
    b = LocalBackend(tmp_path)
    _, d = b.handle("POST", "/api/games", {"seed": 6}, None)
    gid, tok = d["game_id"], d["seat_token"]
    if d["observation"].get("awaiting_deal"):
        b.handle("POST", f"/api/games/{gid}/deal", None, tok)
    status, r = b.handle("GET", f"/api/games/{gid}/calculo", None, tok)
    assert status == 200 and "probabilidades" in r
    status, _ = b.handle("GET", f"/api/games/{gid}/calculo", None, "token-falso")
    assert status == 403


def test_el_calculo_no_usa_cartas_ajenas():
    from musst.agents.mathematical import calculation_report
    from musst.engine.game import MusGame

    game = MusGame(seed=5)
    while game.phase.value == "mus":
        game.apply(game.turn, CutMusAction())
    seat = game.turn
    other = game.clone()
    a, b = [s for s in range(4) if s != seat][:2]
    other.hands[a], other.hands[b] = other.hands[b], other.hands[a]
    r1 = calculation_report(build_observation(game, seat), seed=3)
    r2 = calculation_report(build_observation(other, seat), seed=3)
    assert r1 == r2
