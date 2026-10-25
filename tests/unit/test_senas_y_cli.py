"""Señas FEM (preparadas) y CLIs."""

from musst.arena.cli import main as arena_main
from musst.cli import main as play_main
from musst.engine.cards import parse_hand
from musst.engine.signals import SIGNAL_GESTURES, Signal, truthful_signals


def test_todas_las_senas_tienen_gesto_oficial():
    assert set(SIGNAL_GESTURES) == set(Signal)


def test_senas_veraces():
    assert truthful_signals(parse_hand("12O 3C 4E 5B")) >= {Signal.DOS_REYES}
    assert truthful_signals(parse_hand("1O 2C 4E 5B")) >= {Signal.DOS_ASES}
    assert Signal.DUPLES in truthful_signals(parse_hand("12O 12C 1E 1B"))
    assert Signal.MEDIAS_REYES in truthful_signals(parse_hand("12O 12C 3E 4B"))
    assert Signal.TREINTA_Y_UNA in truthful_signals(parse_hand("12O 11C 10E 1B"))
    assert Signal.CIEGO in truthful_signals(parse_hand("4O 5C 6E 7B")) or truthful_signals(
        parse_hand("4O 5C 6E 7B")
    )


def test_cli_partida(capsys):
    assert play_main(["--bots", "sencillo", "random", "--seed", "1"]) == 0
    assert "ganador" in capsys.readouterr().out


def test_cli_torneo(tmp_path, capsys):
    assert arena_main(["--games", "1", "--only", "sencillo", "random", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "scoreboard.json").exists()
    assert "| 1 |" in capsys.readouterr().out
