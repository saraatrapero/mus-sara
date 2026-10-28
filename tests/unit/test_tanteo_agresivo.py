"""El agente del tanteo según el marcador (petición de la usuaria).

- A punto de salir (falta 1 tanto): un «no quiero» ya da la partida, así que se echa órdago
  aunque la mano sea regular: el rival tiene que jugarse la partida o perderla.
- Rival a punto de ganar: más agresivo, aunque vayamos por delante.
- Si un «no quiero» le regala al rival los tantos que le faltan, rechazar es perder la partida.
"""

import random

from musst.agents.base import AgentContext, AgentReport, Estimate
from musst.agents.strategy import StrategyAgent
from musst.engine import AcceptAction, BetAction, OrdagoAction, RejectAction
from musst.engine.observation import build_observation
from tests.helpers import act, rigged_game

HANDS = {0: "12O 12C 3E 3B", 1: "1O 1C 4E 5B", 2: "4O 5C 6E 7B", 3: "4C 5E 6B 7O"}


def _evs(game, seat, p, threshold=0.55):
    ctx = AgentContext(build_observation(game, seat), random.Random(0), {"bluff_rate": 0.0})
    ctx.reports["probabilidad"] = AgentReport(
        "probabilidad",
        {k: Estimate(p, 1.0) for k in ("p_win", "p_win_if_accept_bet", "p_win_if_accept_ordago")},
    )
    ctx.reports["marcador"] = AgentReport(
        "marcador", {"ordago_threshold": Estimate(threshold, 1.0)}
    )
    return {type(c.action): c.ev for c in StrategyAgent().candidates(ctx)}


def test_a_punto_de_salir_echa_ordago_a_grande():
    game = rigged_game(HANDS, score=(39, 10))  # al asiento 0 le falta 1 tanto
    evs = _evs(game, 0, p=0.4)  # mano regular, y además va ganando
    assert OrdagoAction in evs
    assert evs[OrdagoAction] == max(evs.values())


def test_a_punto_de_salir_no_echa_ordago_sin_nada():
    game = rigged_game(HANDS, score=(39, 10))
    assert OrdagoAction not in _evs(game, 0, p=0.1)


def test_con_dos_tantos_por_salir_no_es_automatico():
    game = rigged_game(HANDS, score=(38, 10))  # el «no quiero» (1) ya no basta
    assert OrdagoAction not in _evs(game, 0, p=0.4)


def test_rival_a_punto_de_ganar_echa_ordago_aunque_vaya_por_delante():
    game = rigged_game(HANDS, score=(38, 37))  # a los rivales les faltan 3
    evs = _evs(game, 0, p=0.7, threshold=0.4)
    assert OrdagoAction in evs


def test_ganando_y_rival_lejos_sigue_prudente():
    game = rigged_game(HANDS, score=(30, 5))
    assert OrdagoAction not in _evs(game, 0, p=0.7, threshold=0.4)


def test_no_rechaza_si_el_no_quiero_le_da_la_partida_al_rival():
    game = rigged_game(HANDS, score=(39, 10))  # a la pareja del asiento 0 le falta 1
    act(game, BetAction(2))  # envida el asiento 0
    evs = _evs(game, 1, p=0.1)  # mano muy floja del asiento 1
    assert evs[AcceptAction] > evs[RejectAction]


def test_ante_un_ordago_que_le_da_la_partida_si_no_lo_quiere_lo_ve():
    game = rigged_game(HANDS, score=(39, 10))
    act(game, OrdagoAction())
    evs = _evs(game, 1, p=0.2)
    assert evs[AcceptAction] > evs[RejectAction]
