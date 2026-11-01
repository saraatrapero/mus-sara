"""Cada bot de la mesa es un personaje de parodia distinto (apodo inventado y caricatura)."""

from musst.server.personajes import AVISO, PERSONAJES, reparto
from musst.web.backend import LocalBackend


def test_reparto_de_personajes_distintos_y_reproducible():
    assert len(set(reparto(7, 3))) == 3
    assert reparto(7, 3) == reparto(7, 3)
    assert set(reparto(7, 8)) == set(PERSONAJES)
    assert "parodia" in AVISO


def test_los_bots_de_la_mesa_son_personajes(tmp_path):
    b = LocalBackend(tmp_path)
    _, data = b.handle("POST", "/api/games", {"seed": 4}, None)
    bots = [s for s in data["observation"]["seats"] if s["kind"] == "bot"]
    assert len(bots) == 3
    assert len({s["avatar"] for s in bots}) == 3
    for s in bots:
        assert s["avatar"] in PERSONAJES
        assert s["name"] == PERSONAJES[s["avatar"]]


def test_los_nombres_elegidos_se_respetan(tmp_path):
    b = LocalBackend(tmp_path)
    _, data = b.handle("POST", "/api/games", {"seed": 4, "names": {"1": "Pepe"}}, None)
    seat1 = data["observation"]["seats"][1]
    assert seat1["name"] == "Pepe" and seat1["avatar"] in PERSONAJES
