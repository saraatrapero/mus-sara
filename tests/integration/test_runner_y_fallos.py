"""Partidas completas sin interfaz y robustez ante bots que fallan (Req 1.1, 4.1)."""

import time

import pytest

from musst import play_game
from musst.bots.api import Action, Bot, Observation
from musst.bots.builtin import MediumBot, ProBot, RandomBot, SimpleBot
from musst.engine import BetAction


class CrashBot(Bot):
    name = "crash"

    def decide(self, observation: Observation) -> Action:
        raise RuntimeError("boom")


class IllegalBot(Bot):
    name = "illegal"

    def decide(self, observation: Observation) -> Action:
        return BetAction(-5)


class GarbageBot(Bot):
    name = "garbage"

    def decide(self, observation: Observation) -> Action:
        return "órdago!"  # type: ignore[return-value]


class SlowBot(Bot):
    name = "slow"

    def decide(self, observation: Observation) -> Action:
        time.sleep(0.05)
        return (
            observation.legal_actions[0].default()
            if observation.legal_actions[0].type != "discard"
            else RandomBot(1).decide(observation)
        )


@pytest.mark.parametrize("cls", [RandomBot, SimpleBot, MediumBot, ProBot])
def test_partida_completa_con_cada_bot_interno(cls):
    match = play_game([cls(1), RandomBot(2), cls(3), RandomBot(4)], seed=42)
    assert match.result.winner in (0, 1)
    assert not match.errors


@pytest.mark.parametrize("bad", [CrashBot, IllegalBot, GarbageBot])
def test_en_torneo_el_bot_que_falla_pierde(bad):
    match = play_game([SimpleBot(1), bad(), SimpleBot(3), SimpleBot(4)], seed=1, mode="tournament")
    assert match.result.winner == 0
    assert match.result.reason.startswith("bot_failure")
    assert match.errors and match.errors[0].seat == 1


def test_timeout_en_torneo():
    match = play_game(
        [SlowBot(), SimpleBot(2), SimpleBot(3), SimpleBot(4)],
        seed=1,
        mode="tournament",
        time_limit_s=0.01,
    )
    assert match.result.winner == 1
    assert match.errors[0].kind == "timeout"


def test_fuera_del_torneo_se_sustituye_por_fallback_y_la_partida_termina():
    match = play_game([CrashBot(), SimpleBot(2), SimpleBot(3), SimpleBot(4)], seed=1, mode="casual")
    assert match.result.reason == "points" or match.result.reason == "ordago"
    assert match.errors[0].kind == "exception"


def test_se_necesitan_cuatro_bots():
    with pytest.raises(ValueError):
        play_game([SimpleBot()] * 3)
