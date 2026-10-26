"""Envites, reenvites y órdagos (FEM VI)."""

import pytest

from musst.engine import (
    AcceptAction,
    AcceptNoLoseAction,
    BetAction,
    IllegalAction,
    OrdagoAction,
    PassAction,
    Phase,
    RaiseAction,
    RejectAction,
)
from musst.engine.events import EventKind
from tests.helpers import act, rigged_game

NEUTRAL = {0: "4O 5C 6E 7B", 1: "4C 5E 6B 7O", 2: "4E 5B 6O 7C", 3: "4B 5O 6C 7E"}


def test_negada_un_tanto_en_el_acto():
    game = rigged_game(NEUTRAL)
    act(game, BetAction(2), RejectAction(), RejectAction())
    assert game.score == [1, 0]
    assert game.phase is Phase.CHICA
    awarded = [e for e in game.events if e.kind is EventKind.POINTS_AWARDED]
    assert awarded[-1].payload["concept"] == "negada"


def test_vale_el_quiero_del_companero():
    """FEM VI.4: si uno no quiere y su compañero quiere, vale el quiero."""
    game = rigged_game(NEUTRAL)
    act(game, BetAction(2), RejectAction())
    assert game.phase is Phase.GRANDE
    assert game.turn == 3
    act(game, AcceptAction())
    assert game.lances[Phase.GRANDE].status == "accepted"
    assert game.lances[Phase.GRANDE].accepted_stake == 2


def test_responde_la_pareja_contraria_y_el_companero_no_puede_subir():
    game = rigged_game(NEUTRAL)
    act(game, BetAction(3))
    assert game.turn == 1
    assert game.legal_specs(2) == []


def test_reenvite_no_querido_cobra_la_apuesta_anterior():
    game = rigged_game(NEUTRAL)
    act(game, BetAction(2), RaiseAction(3))
    assert game.lances[Phase.GRANDE].stake == 5
    assert game.turn in (0, 2)
    act(game, RejectAction(), RejectAction())
    assert game.score == [0, 2]


def test_cantidad_de_envite_fuera_de_rango():
    game = rigged_game(NEUTRAL)
    with pytest.raises(IllegalAction):
        game.apply(0, BetAction(1))
    with pytest.raises(IllegalAction):
        game.apply(0, BetAction(1000))


def test_todos_pasan():
    game = rigged_game(NEUTRAL)
    act(game, PassAction(), PassAction(), PassAction(), PassAction())
    assert game.lances[Phase.GRANDE].status == "passed"
    assert game.phase is Phase.CHICA


def test_ordago_aceptado_termina_el_juego():
    hands = {0: "12O 12C 3E 3B", 1: "1O 1C 4E 5B", 2: "4O 5C 6E 7B", 3: "4C 5E 6B 7O"}
    game = rigged_game(hands, score=(10, 30))
    act(game, OrdagoAction(), AcceptAction())
    assert game.finished
    assert game.result.winner == 0 and game.result.reason == "ordago"
    assert any(e.kind is EventKind.HANDS_REVEALED for e in game.events)


def test_ordago_rechazado_da_negada_y_sigue_la_jugada():
    game = rigged_game(NEUTRAL)
    act(game, OrdagoAction(), RejectAction(), RejectAction())
    assert game.score == [1, 0]
    assert not game.finished
    assert game.phase is Phase.CHICA


def test_ordago_sobre_envite_rechazado_cobra_el_envite():
    game = rigged_game(NEUTRAL)
    act(game, BetAction(5), OrdagoAction(), RejectAction(), RejectAction())
    assert game.score == [0, 5]


def test_no_se_sube_un_ordago():
    game = rigged_game(NEUTRAL)
    act(game, OrdagoAction())
    types = {s.type for s in game.legal_specs(game.turn)}
    assert types == {"accept", "reject"}


def test_en_pares_solo_hablan_quienes_los_tienen():
    hands = {0: "12O 12C 4E 5B", 1: "1O 1C 6E 7B", 2: "4O 5C 6B 7O", 3: "4C 5E 6O 7C"}
    game = rigged_game(hands)
    act(game, *[PassAction()] * 8)  # grande y chica en paso
    assert game.phase is Phase.PARES
    assert game.lances[Phase.PARES].participants == [0, 1]
    assert game.turn == 0
    act(game, BetAction(2))
    assert game.turn == 1  # el 3 no tiene pares y no responde
    act(game, RejectAction())
    assert game.lances[Phase.PARES].status == "rejected"


def test_pares_de_una_sola_pareja_no_hay_envites():
    hands = {0: "12O 12C 4E 5B", 2: "1O 1C 6E 7B", 1: "4O 5C 6B 7O", 3: "4C 5E 6O 7C"}
    game = rigged_game(hands)
    act(game, *[PassAction()] * 8)
    assert game.lances[Phase.PARES].status == "no_bet"
    assert game.phase in (Phase.JUEGO, Phase.PUNTO)


def test_punto_si_nadie_tiene_juego():
    game = rigged_game(NEUTRAL)
    act(game, *[PassAction()] * 8)
    assert game.phase is Phase.PUNTO
    assert game.declarations["juego"] == {0: False, 1: False, 2: False, 3: False}


def test_quiero_y_no_pierdo_postre_con_33():
    """FEM VI.9: el postre con 33 solo puede querer un órdago a juego con 'quiero y no pierdo'."""
    # mano = 0, postre (reparte) = 3
    hands = {
        0: "12O 11C 10E 1B",  # 31
        1: "12C 11E 10B 1O",  # 31
        2: "4O 5C 6E 7B",
        3: "12E 11O 6C 7C",  # 33, postre
    }
    game = rigged_game(hands)
    act(game, *[PassAction()] * 8)
    while game.phase is Phase.PARES:
        act(game, PassAction())
    assert game.phase is Phase.JUEGO
    act(game, OrdagoAction())
    assert game.turn == 1
    act(game, RejectAction())
    assert game.turn == 3
    types = {s.type for s in game.legal_specs(3)}
    assert "accept" not in types
    # Su compañero (1) tiene juego: puede "querer y no perder".
    assert "accept_no_lose" in types
    act(game, AcceptNoLoseAction())
    assert game.finished
