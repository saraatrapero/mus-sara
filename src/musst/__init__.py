"""MUS.ST — El Mus que aprende cómo juegas.

Partida completa sin interfaz (Req 1.1)::

    from musst import play_game
    from musst.bots.builtin import SimpleBot

    match = play_game([SimpleBot(1), SimpleBot(2), SimpleBot(3), SimpleBot(4)], seed=12345)
    print(match.result)
"""

from musst.runtime.runner import MatchResult, play_game

__version__ = "0.1.0"
__all__ = ["MatchResult", "__version__", "play_game"]
