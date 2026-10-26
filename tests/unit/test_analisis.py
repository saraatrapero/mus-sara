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


def test_contrafactuales_de_las_decisiones_del_jugador():
    from musst.analytics.analysis import decision_counterfactuals

    found = []
    for seed in range(1, 8):
        h = history_of(seed)
        for seat in range(4):
            found += decision_counterfactuals(h, seat)
    assert found
    for c in found:
        assert c["elegiste"] in ("aceptar", "rechazar")
        assert c["acierto"] == (c["tantos"] >= c["alternativa"])
        if c["elegiste"] == "aceptar":
            assert abs(c["tantos"]) == c["envite"]
