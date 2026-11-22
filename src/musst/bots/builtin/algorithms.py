"""Bots basados en algoritmos clásicos de búsqueda y optimización."""

from __future__ import annotations

import heapq

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
    RejectAction,
    RaiseAction,
)
from musst.bots.toolkit import discard_options, hand_strength, hand_value
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
            actions.extend(BetAction(value) if kind == "bet" else RaiseAction(value) for value in values)

    return actions or [spec.default() for spec in obs.legal_actions if spec.type != "discard"]


def _value(obs: Observation, action: Action) -> float:
    strength = hand_value(obs.hand)
    lance_strength = hand_strength(obs.hand, obs.phase if obs.phase in ("grande", "chica", "pares", "juego", "punto") else "grande")

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
        return lance_strength - stake / 60 + max(0.0, (obs.target - max(obs.score)) / obs.target) * 0.15
    return lance_strength


class _SearchBot(Bot):
    author = "MUS.ST"

    def _choose(self, obs: Observation) -> Action:
        raise NotImplementedError

    def decide(self, observation: Observation) -> Action:
        return self._choose(observation)


class GreedyBot(_SearchBot):
    """Elige siempre la acción con mayor valor inmediato."""

    name = "greedy"

    def _choose(self, obs: Observation) -> Action:
        actions = _concrete_actions(obs)
        return max(actions, key=lambda action: _value(obs, action))


class DijkstraBot(_SearchBot):
    """Construye un grafo de acciones legales y elige el camino de menor coste acumulado."""

    name = "dijkstra"

    def _choose(self, obs: Observation) -> Action:
        actions = _concrete_actions(obs)
        start = "inicio"
        queue: list[tuple[float, int, str]] = [(0.0, 0, start)]
        costs: dict[str, float] = {start: 0.0}
        chosen: dict[str, Action] = {}

        for index, action in enumerate(actions):
            node = f"accion:{index}"
            chosen[node] = action
            cost = 1.0 - _value(obs, action)
            edge = costs[start] + max(0.0, cost)
            if edge < costs.get(node, float("inf")):
                costs[node] = edge
                heapq.heappush(queue, (edge, index + 1, node))

        best_node = min((node for node in costs if node != start), key=lambda node: costs[node])
        return chosen[best_node]


class AStarBot(_SearchBot):
    """Busca el mejor curso inmediato con A*: coste real más una heurística de fuerza de mano."""

    name = "a_star"

    def _choose(self, obs: Observation) -> Action:
        actions = _concrete_actions(obs)
        strength = hand_value(obs.hand)
        score_progress = max(obs.score) / obs.target
        heuristic = max(0.0, 1.0 - strength - score_progress * 0.25)

        queue: list[tuple[float, int, Action]] = []
        for index, action in enumerate(actions):
            real_cost = 1.0 - _value(obs, action)
            estimated_total = max(0.0, real_cost) + heuristic
            heapq.heappush(queue, (estimated_total, index, action))

        return heapq.heappop(queue)[2]


__all__ = ["GreedyBot", "DijkstraBot", "AStarBot"]
