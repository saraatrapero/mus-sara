"""Señas con miradas (FEM VIII): verdaderas, tras cortar, y solo las ve quien mira."""

import pytest

from musst.bots.builtin import SimpleBot
from musst.engine import MusGame, RulesConfig
from musst.engine.events import EventKind
from musst.engine.game import IllegalAction
from musst.engine.observation import build_observation
from musst.engine.signals import Signal
from musst.runtime.runner import play_game
from tests.helpers import rigged_game

ON = RulesConfig(signals_enabled=True)


def test_sin_senas_la_partida_es_identica():
    a = play_game([SimpleBot(i) for i in range(4)], seed=5).events
    b = play_game([SimpleBot(i) for i in range(4)], seed=5, config=RulesConfig()).events
    assert [e.to_dict() for e in a] == [e.to_dict() for e in b]
    assert not any(e.kind is EventKind.GAZE_CHANGED for e in a)


def test_activar_senas_no_cambia_el_reparto():
    off, on = MusGame(seed=9), MusGame(seed=9, config=ON)
    assert off.hands == on.hands and off.dealer == on.dealer


def test_solo_senas_verdaderas_y_despues_de_cortar():
    game = MusGame(seed=3, config=ON)
    assert game.phase.value == "mus"
    assert game.legal_signals(0) == []
    g = rigged_game({0: "12O 12C 1E 4B"}, config=ON)  # dos reyes
    assert Signal.DOS_REYES in g.legal_signals(0)
    with pytest.raises(IllegalAction):
        g.signal(0, Signal.DUPLES)
    with pytest.raises(IllegalAction):
        g.signal(0, "inventada")
    g.signal(0, Signal.DOS_REYES)
    with pytest.raises(IllegalAction):  # una vez por jugada
        g.signal(0, Signal.DOS_REYES)


def test_solo_la_ven_quienes_miran():
    g = rigged_game({0: "12O 12C 1E 4B"}, config=ON)
    g.gaze = [None, 0, 0, None]  # mira el rival 1 y el compañero 2; el 3 mira a la mesa
    g.signal(0, Signal.DOS_REYES)
    seen = {s: build_observation(g, s).signals_seen for s in range(4)}
    assert seen[1] == {0: ("dos_reyes",)}
    assert seen[2] == {0: ("dos_reyes",)}
    assert seen[3] == {}
    made = [e for e in g.events if e.kind is EventKind.SIGNAL_MADE][-1]
    assert made.payload["seen_by"] == [1, 2]
    assert made.visible_to(0) and not made.visible_to(1) and not made.visible_to(None)


def test_nadie_mira_la_sena_se_pierde():
    g = rigged_game({0: "12O 12C 1E 4B"}, config=ON)
    g.gaze = [None, None, None, None]
    g.signal(0, Signal.DOS_REYES)
    assert not any(e.kind is EventKind.SIGNAL_SEEN for e in g.events)


def test_miradas_publicas_cambian_con_el_tiempo_y_son_reproducibles():
    a, b = MusGame(seed=4, config=ON), MusGame(seed=4, config=ON)
    for _ in range(10):
        a.tick()
        b.tick()
    assert a.gaze == b.gaze
    assert (
        len({tuple(x.payload.values()) for x in a.events if x.kind is EventKind.GAZE_CHANGED}) > 3
    )
    obs = build_observation(a, 1)
    assert list(obs.gazes) == a.gaze


def test_las_senas_vistas_restringen_las_manos_simuladas():
    import random

    from musst.bots.toolkit import sample_world
    from musst.engine.signals import truthful_signals

    g = rigged_game({0: "12O 12C 1E 4B", 2: "1O 1C 1B 5E"}, config=ON)
    g.gaze = [2, None, 0, None]
    g.signal(2, Signal.MEDIAS_ASES)
    obs = build_observation(g, 0)
    rng = random.Random(1)
    for _ in range(20):
        world = sample_world(obs, rng)
        assert Signal.MEDIAS_ASES in truthful_signals(world[2])


def test_los_bots_pasan_senas_y_el_profesional_evita_a_los_rivales():
    from musst.agents.orchestrator import ProBot

    made = []
    for seed in range(1, 6):
        m = play_game([ProBot(1), SimpleBot(2), ProBot(3), SimpleBot(4)], seed=seed, config=ON)
        made += [e for e in m.events if e.kind is EventKind.SIGNAL_MADE]
    assert made
    pro = [e for e in made if e.actor in (0, 2)]
    assert pro
    for e in pro:  # cuidadoso: solo con el compañero mirando y ningún rival
        partner = (e.actor + 2) % 4
        assert partner in e.payload["seen_by"]
        assert not any(s % 2 != e.actor % 2 for s in e.payload["seen_by"])


def test_las_senas_son_siempre_verdaderas_en_partidas_reales():
    from musst.engine.cards import Card
    from musst.engine.signals import truthful_signals

    m = play_game([SimpleBot(i) for i in range(4)], seed=8, config=ON)
    hands = {
        e.round_no: {int(s): [Card.parse(c) for c in cs] for s, cs in e.payload["hands"].items()}
        for e in m.events
        if e.kind is EventKind.HANDS_REVEALED
    }
    for e in m.events:
        if e.kind is EventKind.SIGNAL_MADE and e.round_no in hands:
            assert Signal(e.payload["signal"]) in truthful_signals(hands[e.round_no][e.actor])
