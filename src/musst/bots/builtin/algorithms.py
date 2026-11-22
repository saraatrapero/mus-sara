"""Bots basados en algoritmos clásicos de búsqueda y optimización."""

from __future__ import annotations

import heapq
import random

from musst.bots.api import (
    AcceptAction,
    AcceptNoLoseAction,
    Action,
    BetAction,
    Bot,
    CutMusAction,
    DiscardAction,
    MusAction,
    OrdagoAction,
    PassAction,
    RaiseAction,
    RejectAction,
)
from musst.bots.toolkit import (
    discard_options,
    hand_strength,
    hand_value,
    lance_winner,
    sample_world,
)
from musst.engine.observation import Observation


def _concrete_actions(obs: Observation) -> list[Action]:
    actions: list[Action] = []
    types = obs.legal_types()

    if "mus" in types:
        actions.append(MusAction())
    if "cut" in types:
        actions.append(CutMusAction())
    if "discard" in types:
        spec = obs.spec("discard")
        minimum = spec.min_amount if spec and spec.min_amount else 1
        actions.extend(DiscardAction(cards) for cards in discard_options(obs.hand, minimum)[:32])
    if "pass" in types:
        actions.append(PassAction())
    if "accept" in types:
        actions.append(AcceptAction())
    if "accept_no_lose" in types:
        actions.append(AcceptNoLoseAction())
    if "reject" in types:
        actions.append(RejectAction())
    if "ordago" in types:
        actions.append(OrdagoAction())

    for kind in ("bet", "raise"):
        spec = obs.spec(kind)
        if spec:
            minimum = spec.min_amount or 2
            maximum = spec.max_amount or minimum
            values = sorted(set((minimum, (minimum + maximum) // 2, maximum)))
            actions.extend(
                BetAction(value) if kind == "bet" else RaiseAction(value) for value in values
            )

    return actions or [spec.default() for spec in obs.legal_actions if spec.type != "discard"]


def _value(obs: Observation, action: Action) -> float:
    strength = hand_value(obs.hand)
    lance_strength = hand_strength(
        obs.hand,
        obs.phase if obs.phase in ("grande", "chica", "pares", "juego", "punto") else "grande",
    )

    if isinstance(action, DiscardAction):
        discarded = set(action.cards)
        kept = tuple(card for card in obs.hand if card not in discarded)
        return hand_value(kept)
    if isinstance(action, (MusAction,)):
        return 0.55 - strength
    if isinstance(action, CutMusAction):
        return 0.30 + strength
    if isinstance(action, PassAction):
        return lance_strength * 0.35
    if isinstance(action, (AcceptAction, AcceptNoLoseAction)):
        stake = obs.current_bet.stake if obs.current_bet else 2
        return lance_strength - stake / 100
    if isinstance(action, RejectAction):
        return 0.55 - lance_strength
    if isinstance(action, OrdagoAction):
        return lance_strength + max(0.0, (obs.target - max(obs.score)) / obs.target)
    if isinstance(action, (BetAction, RaiseAction)):
        stake = action.amount
        return (
            lance_strength
            - stake / 60
            + max(0.0, (obs.target - max(obs.score)) / obs.target) * 0.15
        )
    return lance_strength


class _SearchBot(Bot):
    author = "MUS.ST"

    def __init__(self) -> None:
        self.rng = random.Random()
        self.last_explanation = ""

    def _choose(self, obs: Observation) -> Action:
        raise NotImplementedError

    def decide(self, observation: Observation) -> Action:
        action = self._choose(observation)
        self.last_explanation = f"{self.name}: {action.type} según la estrategia de búsqueda"
        return action


class GreedyBot(_SearchBot):
    """Agente voraz: compara todas las opciones y toma la mejor inmediata."""

    name = "greedy"

    def _choose(self, obs: Observation) -> Action:
        actions = _concrete_actions(obs)
        chosen = max(actions, key=lambda action: _value(obs, action))
        self.last_explanation = (
            f"Greedy elige {chosen.type}: maximiza el valor inmediato de la mano y del marcador"
        )
        return chosen


class DijkstraBot(_SearchBot):
    """Agente Dijkstra: minimiza el coste acumulado de las decisiones y riesgos."""

    name = "dijkstra"

    def _choose(self, obs: Observation) -> Action:
        actions = _concrete_actions(obs)
        own_score = obs.score[obs.team]
        rival_score = obs.score[1 - obs.team]
        queue: list[tuple[float, int, Action, str]] = []

        for index, action in enumerate(actions):
            immediate = 1.0 - _value(obs, action)
            score_risk = abs(rival_score - own_score) / max(obs.target, 1) * 0.25
            depth = 1
            node = f"{obs.phase}|{obs.round_no}|{own_score}|{rival_score}|{action.type}"
            heapq.heappush(queue, (immediate + score_risk + depth * 0.02, index, action, node))

        _, _, chosen, node = heapq.heappop(queue)
        self.last_explanation = (
            f"Dijkstra elige {chosen.type}: minimiza coste y riesgo acumulado desde {node}"
        )
        return chosen


class AStarBot(_SearchBot):
    """Agente A*: combina coste real con una heurística que estima opciones de victoria."""

    name = "a_star"

    def _choose(self, obs: Observation) -> Action:
        actions = _concrete_actions(obs)
        strength = hand_value(obs.hand)
        points_needed = max(0, obs.target - obs.score[obs.team])
        heuristic = max(0.0, 1.0 - strength - (points_needed / obs.target) * 0.35)

        worlds = [
            sample_world(obs, random.Random(obs.round_no * 1000 + i), max_tries=12)
            for i in range(8)
        ]
        possible_wins = 0
        if worlds and obs.phase in ("grande", "chica", "pares", "juego", "punto"):
            for world in worlds:
                winner = lance_winner(obs.phase, world, obs.mano)
                if winner is not None and winner % 2 == obs.team:
                    possible_wins += 1
        win_probability = possible_wins / max(len(worlds), 1)

        queue: list[tuple[float, int, Action]] = []
        for index, action in enumerate(actions):
            real_cost = 1.0 - _value(obs, action)
            estimated_total = max(0.0, real_cost) + heuristic - win_probability * 0.30
            heapq.heappush(queue, (estimated_total, index, action))

        _, _, chosen = heapq.heappop(queue)
        self.last_explanation = f"A* elige {chosen.type}: coste real {real_cost:.2f}, heurística {heuristic:.2f}, victoria posible {win_probability:.0%}"
        return chosen


__all__ = ["AStarBot", "DijkstraBot", "GreedyBot"]
