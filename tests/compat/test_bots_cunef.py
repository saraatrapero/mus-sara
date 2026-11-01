"""Bots basico y reglas de mus-cunef jugando sobre el motor FEM de MUS.ST."""

import pytest

from musst.bots.builtin.simple import SimpleBot
from musst.bots.cunef import basico, disponibles, hay_numpy, reglas
from musst.bots.registry import get_entry
from musst.runtime.runner import play_game

necesita_numpy = pytest.mark.skipif(not hay_numpy(), reason="reglas necesita numpy")


def _partidas(fabrica, n, seed0=0):
    """n partidas de la pareja 0 (fabrica) contra dos SimpleBot. Devuelve (victorias, resultados)."""
    victorias, resultados = 0, []
    for k in range(n):
        bots = [fabrica(), SimpleBot(k), fabrica(), SimpleBot(k + 100)]
        r = play_game(bots, seed=seed0 + k, mode="tournament")
        assert not r.errors, r.errors
        victorias += r.result.winner == 0
        resultados.append(r)
    return victorias, resultados


def test_basico_juega_partidas_completas_sin_faltas():
    victorias, _ = _partidas(basico, 12)
    assert victorias >= 1  # gana alguna: juega de verdad, no solo legal


@necesita_numpy
@pytest.mark.parametrize("estilo", ["equilibrado", "agresivo", "conservador"])
def test_reglas_juega_partidas_completas_sin_faltas(estilo):
    _, resultados = _partidas(lambda: reglas(estilo), 4, seed0=50)
    tiempos = [t for r in resultados for s in (0, 2) for t in r.decision_times.get(s, [])]
    assert max(tiempos) < 2.0  # muy por debajo del límite de 5 s del runner


@necesita_numpy
def test_reglas_aprende_de_las_manos_enseñadas():
    bot = reglas(seed=1)
    play_game([bot, SimpleBot(1), reglas(seed=2), SimpleBot(2)], seed=7, mode="tournament")
    assert bot._avisadas >= 1  # recibió on_hand_end con las cartas de las jugadas terminadas


def test_registro_incluye_los_bots_de_mus_cunef():
    nombres = set(disponibles())
    assert "basico" in nombres
    assert get_entry("basico").author == "mus-cunef"
    if hay_numpy():
        assert {"reglas", "reglas_agresivo", "reglas_conservador"} <= nombres
