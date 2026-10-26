"""Yendo por delante, un bot solo echa o ve un órdago si está casi seguro de ganarlo."""

import random

from musst.agents.base import AgentContext, AgentReport, Estimate
from musst.agents.strategy import StrategyAgent
from musst.engine import AcceptAction, OrdagoAction
from musst.engine.observation import build_observation
from tests.helpers import act, rigged_game

HANDS = {0: "12O 12C 3E 3B", 1: "1O 1C 4E 5B", 2: "4O 5C 6E 7B", 3: "4C 5E 6B 7O"}


def _types(game, seat, p, threshold=0.55):
    ctx = AgentContext(build_observation(game, seat), random.Random(0), {"bluff_rate": 0.0})
    ctx.reports["probabilidad"] = AgentReport(
        "probabilidad",
        {k: Estimate(p, 1.0) for k in ("p_win", "p_win_if_accept_bet", "p_win_if_accept_ordago")},
    )
    ctx.reports["marcador"] = AgentReport("marcador", {"ordago_threshold": Estimate(threshold, 1.0)})
    best = {}
    for c in StrategyAgent().candidates(ctx):
        best[type(c.action)] = c.ev
    return best


def test_ganando_no_ve_un_ordago_dudoso():
    game = rigged_game(HANDS, score=(5, 30))  # la pareja 1 (asiento 1) va ganando
    act(game, OrdagoAction())
    evs = _types(game, 1, p=0.7)
    assert evs[AcceptAction] < 0  # rechazar (0) es mejor


def test_perdiendo_si_ve_el_mismo_ordago():
    game = rigged_game(HANDS, score=(30, 5))
    act(game, OrdagoAction())
    evs = _types(game, 1, p=0.7)
    assert evs[AcceptAction] > 0


def test_ganando_no_echa_ordago_dudoso_pero_si_seguro():
    game = rigged_game(HANDS, score=(30, 5))  # el asiento 0 (pareja 0) va ganando
    assert OrdagoAction not in _types(game, 0, p=0.82)
    assert OrdagoAction in _types(game, 0, p=0.9)
