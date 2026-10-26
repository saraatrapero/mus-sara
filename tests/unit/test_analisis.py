"""Análisis post-partida."""

from musst import play_game
from musst.analytics.analysis import key_moments, seat_statistics, what_if
from musst.bots.builtin import SimpleBot


def history_of(seed):
    match = play_game([SimpleBot(i) for i in range(4)], seed=seed)
    return [e.to_dict() for e in match.events if e.visible_to(None)]


def test_estadisticas_y_momentos():
    h = history_of(3)
    stats = seat_statistics(h, 0)
    assert stats["decisiones"] > 0
    assert set(stats["por_lance"]) == {"grande", "chica", "pares", "juego", "punto"}
    moments = key_moments(h)
    assert moments and moments[0].points >= moments[-1].points


def test_contrafactual_usa_las_manos_reveladas():
    h = history_of(3)
    rounds = sorted({e["round"] for e in h if e["kind"] == "HandsRevealed"})
    result = what_if(h, rounds[0], "grande", 0, stake=4)
    assert result is not None
    assert result["si_aceptas"] in (4, -4)
    assert result["mejor_opcion"] in ("aceptar", "rechazar")
