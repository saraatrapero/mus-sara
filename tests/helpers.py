"""Utilidades de test: partidas con manos fijadas ("baraja amañada")."""

from __future__ import annotations

from musst.engine import CutMusAction, MusGame, RulesConfig, parse_hand


def rigged_game(
    hands: dict[int, str],
    mano: int = 0,
    score: tuple[int, int] = (0, 0),
    config: RulesConfig | None = None,
    seed: int = 1,
) -> MusGame:
    """Partida con manos fijadas, mus cortado por el mano y en el lance de grande.

    ``hands`` usa códigos de naipe: ``{0: "12O 12C 3E 1B", ...}``. El mazo se recompone
    para que las 40 cartas sigan siendo únicas.
    """
    game = MusGame(seed=seed, config=config)
    game.mano = mano
    game.dealer = (mano - 1) % 4
    parsed = {s: list(parse_hand(h)) for s, h in hands.items()}
    used = [c for h in parsed.values() for c in h]
    assert len(set(used)) == len(used), "cartas repetidas en el escenario"
    pool = [c for hand in game.hands for c in hand] + game.deck
    pool = [c for c in pool if c not in used]
    for seat in range(4):
        if seat in parsed:
            game.hands[seat] = parsed[seat]
        else:
            game.hands[seat] = [pool.pop() for _ in range(4)]
    game.deck = pool
    game.score = list(score)
    game.apply(mano, CutMusAction())
    return game


def act(game: MusGame, *actions: object) -> None:
    """Aplica acciones en orden, cada una por el asiento al que le toca."""
    for action in actions:
        seat = game.turn
        assert seat is not None
        game.apply(seat, action)  # type: ignore[arg-type]
