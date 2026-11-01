"""Elo de Bradley-Terry del torneo (musst.arena.bradley_terry)."""

import pytest

from musst.arena.bradley_terry import elo, margen_95, victorias


def test_simetria_de_los_cruces():
    cruces = {("a", "b"): (7, 10)}
    assert victorias(cruces, "a", "b") == (7, 10)
    assert victorias(cruces, "b", "a") == (3, 10)
    assert victorias(cruces, "a", "c") == (0, 0)


def test_quien_gana_mas_tiene_mas_elo_y_la_media_es_1500():
    cruces = {("a", "b"): (80, 100), ("b", "c"): (70, 100), ("a", "c"): (90, 100)}
    e = elo(["a", "b", "c"], cruces)
    assert e["a"] > e["b"] > e["c"]
    assert sum(e.values()) / 3 == pytest.approx(1500, abs=1)


def test_diferencia_de_200_puntos_es_un_76_por_ciento():
    # Con muchas partidas el prior de media victoria apenas pesa.
    e = elo(["a", "b"], {("a", "b"): (7600, 10000)})
    assert e["a"] - e["b"] == pytest.approx(200, abs=3)


def test_tiene_en_cuenta_contra_quien_se_gana():
    # x e y ganan el 50 % de sus partidas, pero x solo jugó contra el fuerte e y contra el débil.
    cruces = {
        ("fuerte", "debil"): (90, 100),
        ("x", "fuerte"): (50, 100),
        ("y", "debil"): (50, 100),
    }
    e = elo(["fuerte", "debil", "x", "y"], cruces)
    assert e["x"] > e["y"]


def test_quien_no_gana_nunca_tiene_elo_finito():
    e = elo(["a", "b"], {("a", "b"): (10, 10)})
    assert e["b"] < e["a"] and e["b"] > 0


def test_margen_95():
    assert margen_95(50, 100) == pytest.approx(0.098, abs=0.001)
    assert margen_95(0, 0) == 0.0
