"""Fase de mus y descartes (FEM III, IV)."""

import pytest

from musst.engine import (
    BetAction,
    CutMusAction,
    DiscardAction,
    IllegalAction,
    MusAction,
    MusGame,
    Phase,
    RulesConfig,
)
from musst.engine.events import EventKind


def all_mus(game: MusGame) -> None:
    for _ in range(4):
        game.apply(game.turn, MusAction())


def test_reparto_inicial_cuatro_cartas_y_mano_a_la_derecha_del_que_reparte():
    game = MusGame(seed=3)
    assert all(len(h) == 4 for h in game.hands)
    assert game.mano == (game.dealer + 1) % 4
    assert game.turn == game.mano
    assert len(game.deck) == 24


def test_cortar_mus_empieza_la_grande():
    game = MusGame(seed=3)
    game.apply(game.mano, CutMusAction())
    assert game.phase is Phase.GRANDE
    assert game.turn == game.mano


def test_mus_de_los_cuatro_lleva_a_descartes_que_empiezan_por_el_que_reparte():
    game = MusGame(seed=3)
    all_mus(game)
    assert game.phase is Phase.DISCARD
    order = [(game.dealer - i) % 4 for i in range(4)]
    assert order[-1] == game.mano  # FEM III.11: el mano es el último
    for seat in order:
        assert game.turn == seat
        game.apply(seat, DiscardAction((game.hands[seat][0],)))
    assert game.phase is Phase.MUS
    assert all(len(h) == 4 for h in game.hands)
    assert game.turn == game.mano


def test_descarte_ilegal():
    game = MusGame(seed=3)
    all_mus(game)
    seat = game.turn
    other = game.hands[(seat + 1) % 4][0]
    with pytest.raises(IllegalAction):
        game.apply(seat, DiscardAction(()))
    with pytest.raises(IllegalAction):
        game.apply(seat, DiscardAction((other,)))
    with pytest.raises(IllegalAction):
        game.apply(seat, DiscardAction((game.hands[seat][0], game.hands[seat][0])))


def test_se_rebaraja_el_descarte_cuando_se_acaba_el_mazo():
    game = MusGame(seed=4, config=RulesConfig(max_mus_rounds=50))
    for _ in range(5):
        all_mus(game)
        for _ in range(4):
            seat = game.turn
            game.apply(seat, DiscardAction(tuple(game.hands[seat])))
    assert any(e.kind is EventKind.DECK_RESHUFFLED for e in game.events)
    cards = [c for h in game.hands for c in h] + game.deck + game.discard_pile
    assert len(cards) == 40 and len(set(cards)) == 40


def test_limite_de_rondas_de_mus_obliga_a_cortar():
    game = MusGame(seed=4, config=RulesConfig(max_mus_rounds=1))
    all_mus(game)
    for _ in range(4):
        seat = game.turn
        game.apply(seat, DiscardAction((game.hands[seat][0],)))
    assert [s.type for s in game.legal_specs(game.turn)] == ["cut"]
    with pytest.raises(IllegalAction):
        game.apply(game.turn, MusAction())


def test_fuera_de_turno_y_accion_de_otra_fase():
    game = MusGame(seed=3)
    with pytest.raises(IllegalAction, match="turno"):
        game.apply((game.mano + 1) % 4, MusAction())
    with pytest.raises(IllegalAction):
        game.apply(game.mano, BetAction(2))
