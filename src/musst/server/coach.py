"""Asistente de reglas y situaciones de entrenamiento.

* :func:`explain_legal_actions` explica **solo** las acciones legales del momento; no recomienda.
* Las situaciones de entrenamiento muestran el análisis de los agentes **después** de responder.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from musst.agents.base import AgentContext
from musst.agents.orchestrator import LEVELS, Orchestrator
from musst.engine.actions import ActionSpec, action_from_dict, action_to_dict
from musst.engine.cards import parse_hand
from musst.engine.observation import BetView, Observation

ACTION_HELP: dict[str, str] = {
    "mus": "MUS: pides descartarte. Solo hay descarte si los cuatro dan mus.",
    "cut": "CORTO (no hay mus): se juega con estas cartas. Empiezan los lances.",
    "discard": "DESCARTE: elige de 1 a 4 cartas para cambiarlas por otras del mazo.",
    "pass": "PASO: no apuestas en este lance. Si todos pasan, el lance se cobra al final 'en paso'.",
    "bet": "ENVIDO: apuestas tantos (envido = 2). La pareja contraria debe querer, no querer o subir.",
    "raise": "REENVÍO: subes la apuesta. Si no te quieren, cobras la apuesta anterior.",
    "accept": "QUIERO: aceptas. Los tantos se cuentan al final de la jugada, en orden de lances.",
    "accept_no_lose": "QUIERO Y NO PIERDO: única forma de aceptar un órdago a juego siendo postre con 33 (FEM VI.9).",
    "reject": "NO QUIERO: rechazas. La otra pareja cobra la negada (1) o la apuesta anterior.",
    "ordago": "ÓRDAGO: apuestas el juego entero. Si te lo quieren, se enseñan las cartas y quien gane el lance gana la partida.",
}

PHASE_HELP: dict[str, str] = {
    "mus": "Fase de mus: decide si quieres cambiar cartas o jugar con las que tienes.",
    "discard": "Descarte: elige qué cartas cambias.",
    "grande": "GRANDE: gana la mano con las cartas más altas (rey, 3, caballo, sota, 7…).",
    "chica": "CHICA: gana la mano con las cartas más bajas (as, 2, 4, 5…).",
    "pares": "PARES: solo hablan quienes tienen pareja, medias o duples.",
    "juego": "JUEGO: solo hablan quienes suman 31 o más. La mejor es 31, luego 32, 40, 37…33.",
    "punto": "PUNTO: nadie tiene juego; gana quien más se acerque a 30.",
    "game_over": "La partida ha terminado.",
}


def explain_legal_actions(obs: Observation) -> dict[str, Any]:
    """¿Qué puedo hacer ahora? Solo describe las acciones legales; nunca decide."""
    if not obs.is_my_turn:
        return {"phase": PHASE_HELP.get(obs.phase, ""), "actions": [], "note": "No es tu turno."}
    items = []
    for spec in obs.legal_actions:
        text = ACTION_HELP.get(spec.type, spec.type)
        if spec.type in ("bet", "raise") and spec.min_amount is not None:
            text += f" Cantidad: de {spec.min_amount} a {spec.max_amount}."
        items.append({"type": spec.type, "text": text})
    note = ""
    if obs.current_bet is not None:
        bet = obs.current_bet
        what = "un órdago" if bet.is_ordago else f"un envite de {bet.stake}"
        note = f"La pareja contraria ha lanzado {what} a {bet.lance}."
    return {"phase": PHASE_HELP.get(obs.phase, ""), "actions": items, "note": note}


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    hand: str
    phase: str
    score: tuple[int, int]
    mano: int
    bet: tuple[int, bool] | None  # (apuesta, ¿órdago?)
    declarations: dict[str, dict[int, bool]]
    prompt: str


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "envite-grande-35-38",
        "Final apretado",
        "12O 3C 11E 7B",
        "grande",
        (35, 38),
        1,
        (4, False),
        {},
        "Tienes estas cartas. Vas 35-38. El rival ha envidado 4 a grande. ¿Qué haces?",
    ),
    Scenario(
        "ordago-chica",
        "Órdago a chica",
        "1O 2C 4E 12B",
        "chica",
        (12, 20),
        1,
        (0, True),
        {},
        "Tienes dos ases y un cuatro. El rival lanza órdago a chica con el marcador 12-20.",
    ),
    Scenario(
        "pares-duples",
        "Duples de mano",
        "12O 12C 1E 1B",
        "pares",
        (5, 5),
        0,
        None,
        {"pares": {0: True, 1: True, 2: False, 3: True}},
        "Eres mano con duples de reyes y ases. Los dos rivales tienen pares. ¿Envidas?",
    ),
    Scenario(
        "juego-31-postre",
        "La 31 de postre",
        "12O 11C 10E 1B",
        "juego",
        (20, 22),
        1,
        (2, False),
        {
            "pares": {0: False, 1: False, 2: False, 3: False},
            "juego": {0: True, 1: True, 2: False, 3: True},
        },
        "Tienes 31 pero no eres mano. Te envidan 2 a juego. ¿Qué haces?",
    ),
)


def scenario_observation(sc: Scenario) -> Observation:
    seat = 0
    responders = (0, 2) if sc.bet else ()
    specs: tuple[ActionSpec, ...]
    if sc.bet is None:
        specs = (ActionSpec("pass"), ActionSpec("bet", 2, 40), ActionSpec("ordago"))
        bet = None
    else:
        stake, is_ordago = sc.bet
        bet = BetView(sc.phase, 1, stake, 1, is_ordago, responders)
        base = [ActionSpec("accept"), ActionSpec("reject")]
        if not is_ordago:
            base += [ActionSpec("raise", 2, 40 - stake), ActionSpec("ordago")]
        specs = tuple(base)
    return Observation(
        seat=seat,
        partner=2,
        team=0,
        hand=parse_hand(sc.hand),
        phase=sc.phase,
        turn=seat,
        dealer=(sc.mano - 1) % 4,
        mano=sc.mano,
        round_no=1,
        score=sc.score,
        target=40,
        declarations=sc.declarations,
        current_bet=bet,
        lance_participants=(0, 1, 2, 3),
        lance_statuses={},
        cards_in_deck=24,
        mus_rounds=0,
        legal_actions=specs,
        history=_scenario_history(sc),
    )


def _scenario_history(sc: Scenario) -> tuple[dict[str, Any], ...]:
    """Historial público mínimo: el envite del rival (para que los agentes lo tengan en cuenta)."""
    if sc.bet is None:
        return ()
    stake, is_ordago = sc.bet
    kind = "OrdagoDeclared" if is_ordago else "BetPlaced"
    payload: dict[str, Any] = {"lance": sc.phase}
    if not is_ordago:
        payload["amount"] = stake
    return (
        {"seq": 0, "kind": kind, "round": 1, "phase": sc.phase, "actor": 1, "payload": payload},
    )


def scenario_public(sc: Scenario) -> dict[str, Any]:
    obs = scenario_observation(sc)
    return {
        "id": sc.id,
        "title": sc.title,
        "prompt": sc.prompt,
        "observation": obs.to_dict(),
    }


def analyse_answer(sc: Scenario, answer: dict[str, Any], seed: int = 0) -> dict[str, Any]:
    """Análisis del agente profesional tras responder (no antes)."""
    obs = scenario_observation(sc)
    chosen = action_from_dict(answer)
    if chosen.type not in obs.legal_types():
        raise ValueError("Esa acción no es legal en esta situación")
    orchestrator = Orchestrator(LEVELS["profesional"])
    ctx = AgentContext(obs, random.Random(seed), {"samples": 600, "samples_deep": 1200})
    decision = orchestrator.decide(ctx)
    expl = decision.explanation()
    by_type = {a["action"].split("_")[0]: a for a in expl["alternatives"]}
    mine = by_type.get(chosen.type.upper())
    return {
        "tu_respuesta": action_to_dict(chosen),
        "recomendacion": expl["decision"],
        "p_ganar_lance": round(ctx.estimate("probabilidad", "p_win").value, 3),
        "confianza": expl["confidence"],
        "alternativas": expl["alternatives"],
        "tu_valor_esperado": mine["ev"] if mine else None,
        "explicacion": expl["narrative"],
        "nota": "Estimaciones por simulación con la información que tenías: no son certezas.",
    }
