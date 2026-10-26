"""Bots en subproceso (sandbox) con el protocolo JSON."""

from pathlib import Path

from musst import play_game
from musst.bots.builtin import SimpleBot
from musst.bots.sandbox import SubprocessBot

ROOT = Path(__file__).resolve().parents[2]


def test_bot_externo_de_ejemplo_juega_en_subproceso():
    ext = SubprocessBot(ROOT / "bots" / "ejemplo", "bot:EjemploBot", name="ejemplo")
    match = play_game([ext, SimpleBot(1), SimpleBot(2), SimpleBot(3)], seed=7, mode="tournament")
    assert not match.errors, match.errors
    assert match.result.winner in (0, 1)


def test_bot_que_no_carga_pierde_sin_romper(tmp_path):
    (tmp_path / "bot.py").write_text("raise ImportError('roto')\n")
    ext = SubprocessBot(tmp_path, "bot:Nada")
    match = play_game([ext, SimpleBot(1), SimpleBot(2), SimpleBot(3)], seed=7, mode="tournament")
    assert match.result.winner == 1
    assert match.errors[0].seat == 0


def test_bot_colgado_pierde_por_timeout(tmp_path):
    (tmp_path / "bot.py").write_text(
        "import time\nfrom musst.bots.api import Bot\n"
        "class Lento(Bot):\n    def decide(self, observation):\n        time.sleep(30)\n"
    )
    ext = SubprocessBot(tmp_path, "bot:Lento", timeout_s=0.5)
    match = play_game([ext, SimpleBot(1), SimpleBot(2), SimpleBot(3)], seed=7, mode="tournament")
    assert match.result.winner == 1
    assert match.errors[0].kind == "timeout"


def test_los_print_del_bot_no_rompen_el_protocolo(tmp_path):
    (tmp_path / "bot.py").write_text(
        "from musst.bots.builtin import SimpleBot\n"
        "class Hablador(SimpleBot):\n"
        "    def decide(self, observation):\n        print('hola')\n        return super().decide(observation)\n"
    )
    ext = SubprocessBot(tmp_path, "bot:Hablador")
    match = play_game([ext, SimpleBot(1), SimpleBot(2), SimpleBot(3)], seed=3, mode="tournament")
    assert not match.errors
