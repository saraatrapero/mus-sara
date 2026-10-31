"""Creencias sobre las manos ajenas: teorema de Bayes con las acciones observadas.

Se separan dos modelos (inferencia estadística):

* **Cartas** — P(H): qué manos son posibles y con qué probabilidad. Sale de la combinatoria
  (hipergeométrica multivariante, :mod:`musst.probability.sampler`). Es objetiva.
* **Decisiones** — P(E | H): con qué probabilidad un jugador con la mano H hace lo que hemos
  visto (envidar, pasar, querer, cortar el mus…). Es un modelo de comportamiento, con
  parámetros por jugador que aprende el PlayerModel (farol, agresividad, aceptación).

Teorema de Bayes, para cada reparto H de las cartas desconocidas::

    P(H | E) = P(E | H) · P(H) / P(E),     P(E) = Σ_H P(E | H) · P(H)

con P(E | H) = Π_e P(e | mano del que actuó en H) (las acciones se consideran condicionalmente
independientes dada la mano: es una hipótesis del modelo). Ninguna acción es una certeza:
todas las verosimilitudes tienen un suelo > 0 (faroles, tapados, errores), así que un envite a
grande **desplaza** la distribución hacia manos con reyes, pero no descarta las demás.

Las señas y las declaraciones de pares/juego sí son certezas (FEM: las señas son verdaderas y
las declaraciones obligatorias) y se aplican como restricciones en el muestreo.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from musst.agents.specialists import action_likelihood, bet_likelihood, discard_weight
from musst.bots.toolkit import hand_strength, hand_value
from musst.engine.cards import Card
from musst.engine.observation import Observation
from musst.learning.player_model import PRIORS
from musst.probability.sampler import World

K = TypeVar("K", bound=Hashable)

LIKELIHOOD_FLOOR = 0.05
"""Ninguna acción tiene probabilidad 0 con ninguna mano."""
CUT_SHARPNESS = 0.06
ORDAGO_EXTRA_THRESHOLD = 0.15
"""Un órdago se supone con una mano algo más fuerte que un envite normal."""

BET_KINDS = {"BetPlaced": "bet", "BetRaised": "bet", "OrdagoDeclared": "ordago"}
RESPONSE_KINDS = {
    "Passed": "pass",
    "BetAccepted": "accept",
    "OrdagoAccepted": "accept",
    "BetRejected": "reject",
}


def bayes_update(
    prior: Mapping[K, float], likelihood: Callable[[K], float]
) -> tuple[dict[K, float], float]:
    """Bayes discreto exacto: devuelve P(H | E) para cada H y la evidencia P(E)."""
    joint = {h: p * likelihood(h) for h, p in prior.items()}
    evidence = sum(joint.values())
    if evidence <= 0:
        raise ValueError("Evidencia con probabilidad 0 bajo el prior")
    return {h: v / evidence for h, v in joint.items()}, evidence


@dataclass(frozen=True)
class Evidence:
    """Una acción observada de otro asiento en esta jugada."""

    seat: int
    kind: str
    """``bet``, ``ordago``, ``pass``, ``accept``, ``reject``, ``mus``, ``cut`` o ``asked``."""
    lance: str = ""
    n: int = 1
    """Envites que lleva ese asiento en el lance (incluido este), o cartas pedidas."""

    def describe(self) -> str:
        what = {
            "bet": "envida",
            "ordago": "echa órdago",
            "pass": "pasa",
            "accept": "quiere",
            "reject": "no quiere",
            "mus": "da mus",
            "cut": "corta el mus",
            "asked": f"pide {self.n} cartas",
        }[self.kind]
        return f"asiento {self.seat} {what}" + (f" a {self.lance}" if self.lance else "")


def evidence_from(obs: Observation) -> list[Evidence]:
    """Acciones de los otros tres asientos en la jugada actual, sacadas del historial público.

    Mus/corte: solo cuentan los de la **última** ronda de mus (tras el último descarte), que se
    decidieron con las cartas que tienen ahora; los anteriores eran con otra mano.
    """
    events = [e for e in obs.history if e["round"] == obs.round_no]
    last_discard = max(
        (i for i, e in enumerate(events) if e["kind"] in ("CardsReceived", "DeckReshuffled")),
        default=-1,
    )
    out: list[Evidence] = []
    bets: dict[tuple[int, str], int] = {}
    for i, e in enumerate(events):
        actor = e["actor"]
        kind = e["kind"]
        payload = e["payload"]
        if kind == "CardsDiscarded" and "count" in payload and payload["seat"] != obs.seat:
            out.append(Evidence(payload["seat"], "asked", n=int(payload["count"])))
            continue
        if actor is None or actor == obs.seat:
            continue
        if kind in ("MusRequested", "MusCut") and i > last_discard:
            out.append(Evidence(actor, "cut" if kind == "MusCut" else "mus"))
        elif kind in BET_KINDS:
            lance = payload.get("lance", "")
            bets[(actor, lance)] = bets.get((actor, lance), 0) + 1
            out.append(Evidence(actor, BET_KINDS[kind], lance, bets[(actor, lance)]))
        elif kind in RESPONSE_KINDS:
            out.append(Evidence(actor, RESPONSE_KINDS[kind], payload.get("lance", "")))
    return out


@dataclass(frozen=True)
class SeatBehaviour:
    """Parámetros del modelo de decisiones de un jugador (los aprende el PlayerModel)."""

    bluff: float = PRIORS["bluff_frequency"]
    bet_threshold: float = 0.7
    accept_threshold: float = 0.55
    cut_threshold: float = 0.42


@dataclass
class BehaviourModel:
    """P(acción | mano): modelo de decisiones, separado del modelo de cartas."""

    seats: dict[int, SeatBehaviour] = field(default_factory=dict)

    def params(self, seat: int) -> SeatBehaviour:
        return self.seats.get(seat, SeatBehaviour())

    def likelihood(self, e: Evidence, hand: Sequence[Card]) -> float:
        p = self.params(e.seat)
        if e.kind in ("bet", "ordago"):
            tau = p.bet_threshold + (ORDAGO_EXTRA_THRESHOLD if e.kind == "ordago" else 0.0)
            value = bet_likelihood(hand_strength(hand, e.lance), p.bluff, e.n, tau)
        elif e.kind in ("pass", "accept", "reject"):
            value = action_likelihood(e.kind, hand_strength(hand, e.lance), p.bluff)
        elif e.kind in ("cut", "mus"):
            cut = 1 / (1 + math.exp(-(hand_value(hand) - p.cut_threshold) / CUT_SHARPNESS))
            value = cut if e.kind == "cut" else 1 - cut
        elif e.kind == "asked":
            value = discard_weight(hand_value(hand), float(e.n))
        else:  # pragma: no cover - tipos cerrados arriba
            value = 1.0
        return max(LIKELIHOOD_FLOOR, min(1.0, value))

    def world_likelihood(self, evidence: Sequence[Evidence], world: World) -> float:
        """P(E | H) = Π_e P(e | mano del asiento e en el reparto H)."""
        value = 1.0
        for e in evidence:
            value *= self.likelihood(e, world[e.seat])
        return value


def posterior_weights(
    worlds: Sequence[World],
    prior_weights: Sequence[float],
    evidence: Sequence[Evidence],
    model: BehaviourModel,
) -> list[float]:
    """Pesos ∝ P(H | E) para mundos muestreados con pesos ∝ P(H) (importancia)."""
    return [
        w * model.world_likelihood(evidence, world) if w > 0 else 0.0
        for world, w in zip(worlds, prior_weights, strict=True)
    ]
