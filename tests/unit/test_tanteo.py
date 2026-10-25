"""Tanteo y fin de juego (FEM VI.6, VII)."""

from musst.engine import AcceptAction, BetAction, PassAction, Phase, RejectAction, RulesConfig
from musst.engine.events import EventKind
from tests.helpers import act, rigged_game


def awards(game):
    return [
        (e.payload["team"], e.payload["points"], e.payload["lance"], e.payload["concept"])
        for e in game.events
        if e.kind is EventKind.POINTS_AWARDED
    ]


def play_all_pass(game):
    round_no = game.round_no
    while game.round_no == round_no and not game.finished:
        act(game, PassAction())


def test_todo_en_paso_grande_chica_pares_y_juego():
    hands = {
        0: "12O 12C 11E 1B",  # grande, par de reyes, 31
        1: "1O 2C 4E 5B",  # chica, duples? (1,1 as par) -> par de ases
        2: "4O 5C 6E 7B",
        3: "4C 5E 6B 7O",
    }
    game = rigged_game(hands)
    play_all_pass(game)
    got = awards(game)
    assert got[0] == (0, 1, "grande", "paso")
    assert got[1] == (1, 1, "chica", "paso")
    # pares: reyes (0) > ases (1); el 0 cobra su par = 1
    assert got[2] == (0, 1, "pares", "pares")
    # juego: solo el 0 tiene 31 -> 3
    assert got[3] == (0, 3, "juego", "juego")
    assert game.round_no == 2


def test_envite_aceptado_se_cobra_al_final_de_la_jugada():
    hands = {0: "12O 12C 3E 7B", 1: "1O 2C 4E 5B", 2: "4O 5C 6E 7C", 3: "4C 5E 6B 7O"}
    game = rigged_game(hands)
    act(game, BetAction(4), AcceptAction())
    assert game.score == [0, 0]  # todavía no
    play_all_pass(game)
    assert awards(game)[0] == (0, 4, "grande", "envite")


def test_deje_en_pares_la_pareja_que_gano_el_envite_cobra_sus_pares():
    hands = {0: "12O 12C 4E 5B", 1: "1O 1C 6E 7B", 2: "4O 5C 6B 7O", 3: "4C 5E 6O 7C"}
    game = rigged_game(hands)
    act(game, *[PassAction()] * 8)
    act(game, BetAction(2), RejectAction())
    assert game.score[0] == 1  # negada en el acto
    play_all_pass(game)
    pares = [a for a in awards(game) if a[2] == "pares"]
    assert pares == [(0, 1, "pares", "negada"), (0, 1, "pares", "pares")]


def test_gana_quien_llega_primero_contando_en_orden_de_lances():
    # Pareja 1 gana la grande en paso y llega a 40 antes de que la 0 cobre su juego.
    hands = {0: "1O 1C 11E 10B", 1: "12O 12C 12E 4B", 2: "4O 5C 6E 7B", 3: "4C 5E 6B 7O"}
    game = rigged_game(hands, score=(39, 39))
    play_all_pass(game)
    assert game.finished
    assert game.result.winner == 1
    assert game.score[0] == 39


def test_negada_en_el_acto_puede_terminar_el_juego():
    game = rigged_game({0: "4O 5C 6E 7B", 1: "4C 5E 6B 7O", 2: "4E 5B 6O 7C", 3: "4B 5O 6C 7E"}, score=(39, 0))
    act(game, BetAction(2), RejectAction(), RejectAction())
    assert game.finished and game.result.winner == 0


def test_negada_no_termina_si_se_configura():
    cfg = RulesConfig(end_on_immediate_points=False)
    game = rigged_game(
        {0: "4O 5C 6E 7B", 1: "4C 5E 6B 7O", 2: "4E 5B 6O 7C", 3: "4B 5O 6C 7E"},
        score=(39, 0),
        config=cfg,
    )
    act(game, BetAction(2), RejectAction(), RejectAction())
    assert not game.finished
    assert game.phase is Phase.CHICA


def test_estamos_dentro():
    game = rigged_game({0: "4O 5C 6E 7B", 1: "4C 5E 6B 7O", 2: "4E 5B 6O 7C", 3: "4B 5O 6C 7E"}, score=(35, 0))
    act(game, BetAction(2), RejectAction(), RejectAction())
    assert any(e.kind is EventKind.TEAM_IS_IN and e.payload["team"] == 0 for e in game.events)


def test_la_mano_rota_al_terminar_la_jugada():
    game = rigged_game({0: "4O 5C 6E 7B", 1: "4C 5E 6B 7O", 2: "4E 5B 6O 7C", 3: "4B 5O 6C 7E"}, mano=2)
    play_all_pass(game)
    assert game.mano == 3 and game.dealer == 2


def test_las_cuatro_manos_se_ensenan_al_final_de_la_jugada():
    game = rigged_game({0: "4O 5C 6E 7B", 1: "4C 5E 6B 7O", 2: "4E 5B 6O 7C", 3: "4B 5O 6C 7E"})
    play_all_pass(game)
    revealed = [e for e in game.events if e.kind is EventKind.HANDS_REVEALED]
    assert len(revealed) == 1 and len(revealed[0].payload["hands"]) == 4
