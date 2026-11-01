"""Conformidad del adaptador musarena.Player ↔ musst.Bot (``musst.bots.adaptador``)."""

import random

import pytest

from musst.bots.adaptador import (
    AccionNoTraducible,
    PlayerComoBot,
    a_musst,
    acciones_legales,
    traducir_observacion,
)
from musst.bots.api import Bot
from musst.compat.musarena import actions as ma
from musst.compat.musarena.players.random_bot import RandomBot
from musst.engine.config import RulesConfig
from musst.engine.game import MusGame
from musst.engine.observation import build_observation
from musst.engine.rules import RulesEngine
from musst.runtime.runner import play_game


def _estados(n_partidas=20, seed=0):
    """Recorre partidas al azar y devuelve (juego, asiento, observación) en cada decisión."""
    rng = random.Random(seed)
    for k in range(n_partidas):
        game = MusGame(seed=seed * 1000 + k)
        while not game.finished:
            seat = game.turn
            obs = build_observation(game, seat)
            yield game, seat, obs
            spec = rng.choice(obs.legal_actions)
            game.apply(seat, _cualquiera(spec, obs, rng))


def _cualquiera(spec, obs, rng):
    legales = [a for a in acciones_legales(obs)]
    candidatas = [a_musst(a, obs) for a in legales]
    candidatas = [a for a in candidatas if a.type == spec.type] or candidatas
    return rng.choice(candidatas)


def test_cada_accion_traducida_es_legal_en_el_motor():
    revisadas = 0
    for game, seat, obs in _estados(15):
        legales = acciones_legales(obs)
        assert legales, f"sin acciones legales traducidas en {obs.phase}"
        for accion in legales:
            assert RulesEngine.is_legal(game, seat, a_musst(accion, obs)), accion
            revisadas += 1
    assert revisadas > 1000


def test_todos_los_tipos_legales_tienen_traduccion():
    for _, _, obs in _estados(10, seed=1):
        tipos = {"quiero" if t in ("accept", "accept_no_lose") else t for t in obs.legal_types()}
        traducidos = {type(a).__name__ for a in acciones_legales(obs)}
        assert len(traducidos) >= len(tipos) - (1 if "raise" in tipos else 0)


def test_la_observacion_traducida_no_tiene_cartas_ajenas():
    for game, seat, obs in _estados(5, seed=2):
        mobs = traducir_observacion(obs)
        assert mobs.asiento == seat
        assert {(c.numero, c.palo.value[0].upper()) for c in mobs.cartas} == {
            (c.rank, c.suit.value) for c in game.hands[seat]
        }
        # Las manos de los demás solo aparecen en jugadas ya terminadas (enseñadas).
        assert all(m.numero < obs.round_no for m in mobs.manos_jugadas)


def test_bot_aleatorio_de_musarena_juega_partidas_completas_sin_faltas():
    for seed in range(30):
        bots: list[Bot] = [PlayerComoBot(RandomBot(seed=seed * 4 + i)) for i in range(4)]
        result = play_game(bots, seed=seed)
        assert not result.errors, result.errors
        assert result.result.winner in (0, 1)


def test_accion_fuera_de_la_lista_es_un_fallo_del_bot():
    class Tramposo(RandomBot):
        def choose_action(self, observation, legal_actions):
            return ma.Envido(99)  # nunca está en la lista (tope 40)

    bots = [PlayerComoBot(Tramposo(seed=1))] + [PlayerComoBot(RandomBot(seed=i)) for i in range(3)]
    result = play_game(bots, seed=4, mode="tournament")
    assert result.errors and result.errors[0].seat == 0
    assert result.result.winner == 1  # pierde la pareja del tramposo


def test_tantos_se_escalan_a_una_vaca_de_40():
    game = MusGame(seed=3, config=RulesConfig(target_points=20))
    game.score = [10, 5]
    mobs = traducir_observacion(build_observation(game, game.turn))
    assert mobs.tantos == (20, 10) and mobs.vacas_para_ganar == 1


def test_accion_desconocida_no_se_traduce():
    with pytest.raises(AccionNoTraducible):
        a_musst(object(), build_observation(MusGame(seed=1), 0))
