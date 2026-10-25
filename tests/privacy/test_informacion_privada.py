"""La información privada nunca se filtra (Req 5.1.1, RNF-02)."""

import json
import random

from musst.bots.builtin import RandomBot
from musst.engine import EventKind, MusGame, build_observation, build_spectator_view


def random_play(seed: int, steps: int = 400):
    game = MusGame(seed=seed)
    bots = [RandomBot(seed + i) for i in range(4)]
    for _ in range(steps):
        if game.finished:
            break
        yield game
        seat = game.turn
        game.apply(seat, bots[seat].decide(build_observation(game, seat)))


def hidden_codes(game: MusGame, seat: int) -> set[str]:
    return {c.code for s in range(4) if s != seat for c in game.hands[s]} | {
        c.code for c in game.deck
    }


def revealed_this_round(game: MusGame) -> bool:
    return any(
        e.kind is EventKind.HANDS_REVEALED and e.round_no == game.round_no for e in game.events
    )


def test_ninguna_observacion_contiene_cartas_ajenas_ni_del_mazo():
    for seed in range(60):
        for game in random_play(seed):
            if revealed_this_round(game):
                continue
            for seat in range(4):
                obs = build_observation(game, seat).to_dict()
                hidden = hidden_codes(game, seat)
                current = [e for e in obs["history"] if e["round"] == game.round_no]
                text = json.dumps({**obs, "history": current})
                own = {c.code for c in game.hands[seat]}
                leaked = {code for code in hidden if f'"{code}"' in text} - own
                assert not leaked, f"seed={seed} asiento={seat} fuga={leaked}"


def test_observacion_identica_si_solo_cambian_cartas_ocultas():
    game = MusGame(seed=11)
    other = game.clone()
    a, b = other.hands[1], other.hands[3]
    other.hands[1], other.hands[3] = b, a
    rng = random.Random(1)
    rng.shuffle(other.deck)
    obs_a = build_observation(game, 0).to_dict()
    obs_b = build_observation(other, 0).to_dict()
    # Los eventos privados de otros asientos no son visibles, así que la vista coincide.
    assert obs_a == obs_b


def test_espectador_no_ve_ninguna_mano_antes_del_final():
    game = MusGame(seed=5)
    view = json.dumps(build_spectator_view(game))
    assert all(f'"{c.code}"' not in view for h in game.hands for c in h)


def test_eventos_de_sistema_nunca_visibles():
    game = MusGame(seed=5)
    for seat in [None, 0, 1, 2, 3]:
        assert not any(e.kind is EventKind.DECK_SHUFFLED for e in game.events if e.visible_to(seat))
