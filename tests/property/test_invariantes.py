"""Invariantes del motor con partidas aleatorias (hypothesis)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from musst.bots.builtin import RandomBot
from musst.engine import MusGame, build_observation
from musst.runtime.runner import play_game


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10**6))
def test_cartas_conservadas_marcador_creciente_y_acciones_legales(seed):
    game = MusGame(seed=seed)
    bots = [RandomBot(seed + i) for i in range(4)]
    last = list(game.score)
    steps = 0
    while not game.finished and steps < 3000:
        steps += 1
        seat = game.turn
        action = bots[seat].decide(build_observation(game, seat))
        assert game.validate(seat, action) is None
        game.apply(seat, action)
        cards = [c for h in game.hands for c in h] + game.deck + game.discard_pile
        assert len(cards) == 40 and len(set(cards)) == 40
        assert game.score[0] >= last[0] and game.score[1] >= last[1]
        last = list(game.score)
    assert game.finished


@settings(max_examples=15, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10**6))
def test_reproducible_con_la_misma_seed(seed):
    def run():
        match = play_game([RandomBot(seed + i) for i in range(4)], seed=seed)
        return [(e.kind, e.payload) for e in match.events]

    assert run() == run()
