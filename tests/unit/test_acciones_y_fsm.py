"""Acciones tipadas, serialización y máquina de estados."""

import pytest

from musst.engine import (
    BetAction,
    Card,
    DiscardAction,
    GameEngine,
    MusAction,
    MusGame,
    OrdagoAction,
    RulesConfig,
    action_from_dict,
    action_to_dict,
)
from musst.engine.game import ALLOWED_TRANSITIONS, IllegalTransition, Phase


@pytest.mark.parametrize(
    "action",
    [MusAction(), BetAction(5), OrdagoAction(), DiscardAction((Card.parse("12O"), Card.parse("1C")))],
)
def test_serializacion_ida_y_vuelta(action):
    assert action_from_dict(action_to_dict(action)) == action


@pytest.mark.parametrize(
    "data",
    [{}, {"type": "volar"}, {"type": "bet"}, {"type": "bet", "amount": "2"}, {"type": "discard", "cards": "12O"}, 5],
)
def test_acciones_malformadas(data):
    with pytest.raises(ValueError):
        action_from_dict(data)


def test_tabla_de_transiciones_cubre_todas_las_fases():
    assert set(ALLOWED_TRANSITIONS) == set(Phase)
    assert ALLOWED_TRANSITIONS[Phase.GAME_OVER] == frozenset()


def test_transicion_ilegal():
    game = MusGame(seed=1)
    with pytest.raises(IllegalTransition):
        game._set_phase(Phase.PUNTO)


def test_game_engine_es_puro():
    engine = GameEngine()
    state, _ = engine.new_game(seed=9)
    before = [list(h) for h in state.hands], state.phase, len(state.events)
    new_state, events = engine.apply(state, state.mano, MusAction())
    assert ([list(h) for h in state.hands], state.phase, len(state.events)) == before
    assert events and new_state is not state


def test_configuracion_validada():
    with pytest.raises(ValueError):
        RulesConfig(target_points=0)
    with pytest.raises(ValueError):
        RulesConfig.from_dict({"puntos": 40})
    assert RulesConfig.from_dict({"target_points": 60}).target_points == 60
