"""Utilidades públicas para bots. Trabajan **solo** sobre la :class:`Observation`.

Incluye muestreo de manos rivales compatibles con la información pública (Monte Carlo) y
heurísticas de fuerza por lance.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from musst.engine import evaluation as ev
from musst.engine.cards import Card, full_deck
from musst.engine.observation import Observation
from musst.engine.signals import truthful_signals

LANCE_NAMES = ("grande", "chica", "pares", "juego", "punto")


def unseen_cards(obs: Observation) -> list[Card]:
    """Cartas que pueden estar en manos ajenas: todas menos las mías y mis descartes de la jugada."""
    mine = set(obs.hand)
    discarded: set[Card] = set()
    for event in obs.history:
        if event["kind"] == "DeckReshuffled" and event["round"] == obs.round_no:
            discarded.clear()  # FEM III.15: los descartes vuelven al mazo
        elif (
            event["kind"] == "CardsDiscarded"
            and event["round"] == obs.round_no
            and "cards" in event["payload"]
        ):
            discarded.update(Card.parse(c) for c in event["payload"]["cards"])
    return [c for c in full_deck() if c not in mine and c not in discarded]


def speaking_order(mano: int) -> list[int]:
    return [(mano + i) % 4 for i in range(4)]


def _consistent(hand: Sequence[Card], seat: int, obs: Observation) -> bool:
    signals = obs.signals_seen.get(seat)
    if signals and seat != obs.seat:
        truthful = {s.value for s in truthful_signals(hand)}
        if not set(signals) <= truthful:  # las señas son siempre verdaderas (FEM VIII.4)
            return False
    pares = obs.declarations.get("pares", {})
    if seat in pares and ev.pairs(hand).has_pairs != pares[seat]:
        return False
    juego = obs.declarations.get("juego", {})
    return not (seat in juego and ev.has_juego(hand) != juego[seat])


def sample_world(
    obs: Observation, rng: random.Random, max_tries: int = 50
) -> dict[int, tuple[Card, ...]]:
    """Muestra manos para los otros tres asientos compatibles con lo que sé.

    Restricciones: declaraciones públicas de pares/juego y señas que he visto (verdaderas).
    Se reparte primero a los asientos más restringidos (los que han hecho señas), cada uno con
    varios intentos, para que una seña rara (p. ej. 31) no obligue a descartar mundos enteros.
    """
    pool = unseen_cards(obs)
    others = sorted(
        (s for s in range(4) if s != obs.seat), key=lambda s: -len(obs.signals_seen.get(s, ()))
    )
    world: dict[int, tuple[Card, ...]] = {obs.seat: obs.hand}
    for _ in range(max_tries):
        remaining = list(pool)
        ok = True
        for seat in others:
            for _ in range(max_tries):
                hand = tuple(rng.sample(remaining, 4))
                if _consistent(hand, seat, obs):
                    break
            else:
                ok = False
                break
            world[seat] = hand
            for card in hand:
                remaining.remove(card)
        if ok:
            return world
    rng.shuffle(pool)
    for i, seat in enumerate(others):  # se relaja la restricción si es muy improbable
        world[seat] = tuple(pool[i * 4 : i * 4 + 4])
    return world


def lance_keys(lance: str, world: dict[int, tuple[Card, ...]]) -> dict[int, tuple[int, ...]]:
    return ev.lance_keys(lance, world)


def lance_winner(lance: str, world: dict[int, tuple[Card, ...]], mano: int) -> int | None:
    """Ganador del lance con las reglas del motor (:func:`musst.engine.evaluation.lance_winner`)."""
    return ev.lance_winner(lance, world, speaking_order(mano))


@dataclass(frozen=True)
class WinEstimate:
    p_win: float
    samples: int

    @property
    def confidence(self) -> float:
        """Error estándar → confianza en [0, 1]."""
        if self.samples == 0:
            return 0.0
        se: float = (self.p_win * (1 - self.p_win) / self.samples) ** 0.5
        return max(0.0, 1.0 - 4 * se)


def estimate_lance_win(
    obs: Observation,
    lance: str,
    rng: random.Random,
    samples: int = 200,
    weight: Callable[[dict[int, tuple[Card, ...]]], float] | None = None,
) -> WinEstimate:
    """P(mi pareja gana ``lance``) por Monte Carlo sobre las cartas no vistas.

    ``weight`` permite reponderar cada mundo muestreado (p. ej. con un modelo de rival).
    """
    wins = 0.0
    total = 0.0
    for _ in range(samples):
        world = sample_world(obs, rng)
        w = 1.0 if weight is None else weight(world)
        winner = lance_winner(lance, world, obs.mano)
        total += w
        if winner is not None and winner % 2 == obs.team:
            wins += w
    return WinEstimate(wins / total if total else 0.0, samples)


# --------------------------------------------------------------------- heurísticas
def hand_strength(hand: Sequence[Card], lance: str) -> float:
    """Fuerza heurística de una mano en un lance, en [0, 1]. Rápida y explicable."""
    ranks = sorted((r for r in (ev.grande_key(hand))), reverse=True)
    if lance == "grande":
        kings = ranks.count(12)
        return min(1.0, 0.15 + 0.25 * kings + (0.08 if ranks[0] == 12 and ranks[1] >= 11 else 0))
    if lance == "chica":
        aces = ranks.count(1)
        low = sum(1 for r in ranks if r <= 4)
        return min(1.0, 0.1 + 0.25 * aces + 0.06 * low)
    if lance == "pares":
        p = ev.pairs(hand)
        if p.kind is ev.PairsKind.DUPLES:
            return 0.85 + 0.15 * (p.ranks[0] / 12)
        if p.kind is ev.PairsKind.MEDIAS:
            return 0.6 + 0.25 * (p.ranks[0] / 12)
        if p.kind is ev.PairsKind.PAR:
            return 0.25 + 0.35 * (p.ranks[0] / 12)
        return 0.0
    total = ev.total_points(hand)
    if lance == "juego":
        if total < 31:
            return 0.0
        order = ev.JUEGO_ORDER.index(total)
        return 1.0 - order * 0.11
    return min(1.0, max(0.0, (total - 20) / 10))


LANCE_WEIGHTS = {"grande": 0.3, "chica": 0.15, "pares": 0.3, "juego": 0.35, "punto": 0.05}


def hand_value(hand: Sequence[Card]) -> float:
    """Valor global de una mano (media ponderada de su fuerza en cada lance), en [0, 1]."""
    juego = ev.total_points(hand) >= 31
    return sum(
        w * hand_strength(hand, lance)
        for lance, w in LANCE_WEIGHTS.items()
        if lance != ("punto" if juego else "juego")
    )


def strength_percentile(
    hand: Sequence[Card], lance: str, samples: int = 300, seed: int = 0
) -> float:
    """Percentil de la mano frente a manos aleatorias (con la misma heurística)."""
    rng = random.Random(seed)
    deck = [c for c in full_deck() if c not in hand]
    mine = hand_strength(hand, lance)
    below = sum(1 for _ in range(samples) if hand_strength(rng.sample(deck, 4), lance) < mine)
    return below / samples


def discard_options(hand: Sequence[Card], min_discard: int = 1) -> list[tuple[Card, ...]]:
    """Todos los descartes posibles (de ``min_discard`` a 4 cartas)."""
    return [combo for n in range(min_discard, 5) for combo in itertools.combinations(hand, n)]


def keep_heuristic_discard(hand: Sequence[Card]) -> tuple[Card, ...]:
    """Descarte clásico: guardar reyes, ases útiles y parejas; tirar el resto (mín. 1)."""
    norm = [ev.grande_key([c])[0] for c in hand]
    counts = {r: norm.count(r) for r in norm}
    discard = [c for c, r in zip(hand, norm, strict=True) if r != 12 and counts[r] < 2]
    if not discard:
        lowest = min(zip(hand, norm, strict=True), key=lambda t: (counts[t[1]] >= 2, t[1]))
        discard = [lowest[0]]
    return tuple(discard)
