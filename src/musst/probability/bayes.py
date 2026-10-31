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

from musst.agents.specialists import discard_weight
from musst.bots.toolkit import hand_strength, hand_value
from musst.engine.cards import Card
from musst.engine.observation import Observation
from musst.probability.behaviour_data import FITS
from musst.probability.sampler import World

K = TypeVar("K", bound=Hashable)

LIKELIHOOD_FLOOR = 0.02
"""Ninguna acción tiene probabilidad 0 con ninguna mano (faroles, tapados, errores)."""
CUT_SHARPNESS = 0.06


def logit(p: float) -> float:
    p = min(1 - 1e-6, max(1e-6, p))
    return math.log(p / (1 - p))


def fitted_probability(lance: str, decision: str, strength: float, shift: float = 0.0) -> float:
    """P(decisión | fuerza s) = σ(a + b·s + shift), con (a, b) estimados por máxima
    verosimilitud (``scripts/behaviour_fit.py``); ``shift`` desplaza el intercepto según lo que
    el PlayerModel sabe de ese jugador. Si el lance tiene pocos datos, el ajuste conjunto."""
    a, b, _, _ = FITS.get((lance, decision)) or FITS[("*", decision)]
    x = a + b * strength + shift
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    z = math.exp(x)
    return z / (1 + z)


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
    """``bet``, ``ordago`` (al abrir el lance), ``raise``, ``ordago_resp`` (como respuesta a un
    envite), ``pass``, ``accept``, ``reject``, ``accept_ordago``, ``reject_ordago``, ``mus``,
    ``cut`` o ``asked``."""
    lance: str = ""
    n: int = 1
    """Envites que lleva ese asiento en el lance (incluido este), o cartas pedidas."""

    def describe(self) -> str:
        what = {
            "bet": "envida",
            "ordago": "echa órdago",
            "raise": "reenvida",
            "ordago_resp": "responde con órdago",
            "pass": "pasa",
            "accept": "quiere",
            "reject": "no quiere",
            "accept_ordago": "quiere el órdago",
            "reject_ordago": "no quiere el órdago",
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
    pending: str | None = None  # envite en curso en el lance: None, "bet" u "ordago"
    for i, e in enumerate(events):
        actor = e["actor"]
        kind = e["kind"]
        payload = e["payload"]
        if kind == "LanceStarted":
            pending = None
            continue
        if kind == "CardsDiscarded" and "count" in payload and payload["seat"] != obs.seat:
            out.append(Evidence(payload["seat"], "asked", n=int(payload["count"])))
            continue
        lance = payload.get("lance", "")
        was = pending
        if kind in ("BetPlaced", "BetRaised"):
            pending = "bet"
        elif kind == "OrdagoDeclared":
            pending = "ordago"
        if actor is None or actor == obs.seat:
            continue
        if kind in ("MusRequested", "MusCut") and i > last_discard:
            out.append(Evidence(actor, "cut" if kind == "MusCut" else "mus"))
        elif kind == "Passed":
            out.append(Evidence(actor, "pass", lance))
        elif kind in ("BetPlaced", "BetRaised", "OrdagoDeclared"):
            bets[(actor, lance)] = bets.get((actor, lance), 0) + 1
            n = bets[(actor, lance)]
            if kind == "BetPlaced":
                out.append(Evidence(actor, "bet", lance, n))
            elif kind == "BetRaised":
                out.append(Evidence(actor, "raise", lance, n))
            else:
                out.append(Evidence(actor, "ordago" if was is None else "ordago_resp", lance, n))
        elif kind == "BetAccepted":
            out.append(Evidence(actor, "accept", lance))
        elif kind == "OrdagoAccepted":
            out.append(Evidence(actor, "accept_ordago", lance))
        elif kind == "BetRejected":
            out.append(Evidence(actor, "reject_ordago" if was == "ordago" else "reject", lance))
    return out


@dataclass(frozen=True)
class SeatBehaviour:
    """Ajuste del modelo de decisiones a un jugador concreto (lo aprende el PlayerModel):
    desplazamientos del intercepto, en la escala logit, de «envida» y de «quiere»."""

    envida_shift: float = 0.0
    quiere_shift: float = 0.0
    cut_threshold: float = 0.42


@dataclass
class BehaviourModel:
    """P(acción | mano): modelo de decisiones, separado del modelo de cartas.

    Las decisiones de los lances usan regresiones logísticas estimadas por máxima verosimilitud
    con las manos enseñadas al final de cada jugada (``behaviour_data.py``). Mus/corte y cartas
    pedidas usan las verosimilitudes heurísticas de siempre (no hay ajuste)."""

    seats: dict[int, SeatBehaviour] = field(default_factory=dict)

    def params(self, seat: int) -> SeatBehaviour:
        return self.seats.get(seat, SeatBehaviour())

    def prob(self, seat: int, lance: str, decision: str, hand: Sequence[Card]) -> float:
        """P(el asiento toma la decisión | su mano), sin suelo."""
        p = self.params(seat)
        shift = {"envida": p.envida_shift, "quiere": p.quiere_shift}.get(decision, 0.0)
        return fitted_probability(lance, decision, hand_strength(hand, lance), shift)

    def likelihood(self, e: Evidence, hand: Sequence[Card]) -> float:
        if e.kind in ("cut", "mus"):
            v = hand_value(hand) - self.params(e.seat).cut_threshold
            cut = 1 / (1 + math.exp(-v / CUT_SHARPNESS))
            value = cut if e.kind == "cut" else 1 - cut
        elif e.kind == "asked":
            value = discard_weight(hand_value(hand), float(e.n))
        else:

            def pr(decision: str) -> float:
                return self.prob(e.seat, e.lance, decision, hand)

            value = {
                # P(envite) = P(envida) − P(órdago al abrir): el órdago es una forma de envidar.
                "bet": lambda: pr("envida") - pr("ordago_abre"),
                "ordago": lambda: pr("ordago_abre"),
                "pass": lambda: 1 - pr("envida"),
                # Querer o subir: «quiere» menos la parte de órdagos (no se ajusta la subida aparte).
                "accept": lambda: pr("quiere") - pr("ordago_responde"),
                "raise": lambda: pr("quiere") - pr("ordago_responde"),
                "ordago_resp": lambda: pr("ordago_responde"),
                "reject": lambda: 1 - pr("quiere"),
                "accept_ordago": lambda: pr("quiere_ordago"),
                "reject_ordago": lambda: 1 - pr("quiere_ordago"),
            }[e.kind]()
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
