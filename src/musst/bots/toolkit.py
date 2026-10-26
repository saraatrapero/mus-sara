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

LANCE_NAMES = ("grande", "chica", "pares", "juego", "punto")


def unseen_cards(obs: Observation) -> list[Card]:
    """Cartas que pueden estar en manos ajenas: todas menos las mías y mis descartes de la jugada."""
    mine = set(obs.hand)
    discarded: set[Card] = set()
    for event in obs.history:
        if (
            event["kind"] == "CardsDiscarded"
            and event["round"] == obs.round_no
            and "cards" in event["payload"]
        ):
            discarded.update(Card.parse(c) for c in event["payload"]["cards"])
    return [c for c in full_deck() if c not in mine and c not in discarded]


def speaking_order(mano: int) -> list[int]:
    return [(mano + i) % 4 for i in range(4)]


def _consistent(hand: Sequence[Card], seat: int, obs: Observation) -> bool:
    pares = obs.declarations.get("pares", {})
    if seat in pares and ev.pairs(hand).has_pairs != pares[seat]:
        return False
    juego = obs.declarations.get("juego", {})
    return not (seat in juego and ev.has_juego(hand) != juego[seat])


def sample_world(
    obs: Observation, rng: random.Random, max_tries: int = 50
) -> dict[int, tuple[Card, ...]]:
    """Muestra manos para los otros tres asientos compatibles con las declaraciones públicas."""
    pool = unseen_cards(obs)
    others = [s for s in range(4) if s != obs.seat]
    world: dict[int, tuple[Card, ...]] = {obs.seat: obs.hand}
    for _ in range(max_tries):
        rng.shuffle(pool)
        ok = True
        for i, seat in enumerate(others):
            hand = tuple(pool[i * 4 : i * 4 + 4])
            if not _consistent(hand, seat, obs):
                ok = False
                break
            world[seat] = hand
        if ok:
            return world
    for i, seat in enumerate(others):  # se relaja la restricción si es muy improbable
        world[seat] = tuple(pool[i * 4 : i * 4 + 4])
    return world


def lance_keys(lance: str, world: dict[int, tuple[Card, ...]]) -> dict[int, tuple[int, ...]]:
    if lance == "grande":
        return {s: ev.grande_key(h) for s, h in world.items()}
    if lance == "chica":
        return {s: ev.chica_key(h) for s, h in world.items()}
    if lance == "pares":
        return {s: ev.pairs(h).key for s, h in world.items() if ev.pairs(h).has_pairs}
    if lance == "juego":
        return {s: ev.juego_key(h) for s, h in world.items() if ev.has_juego(h)}
    return {s: ev.punto_key(h) for s, h in world.items()}


def lance_winner(lance: str, world: dict[int, tuple[Card, ...]], mano: int) -> int | None:
    keys = lance_keys(lance, world)
    if not keys:
        return None
    return ev.best_seat(keys, speaking_order(mano))


@dataclass(frozen=True)
class WinEstimate:
    p_win: float
    samples: int

    @property
    def confidence(self) -> float:
        """Error estándar → confianza en [0, 1]."""
        if self.samples == 0:
            return 0.0
        se = (self.p_win * (1 - self.p_win) / self.samples) ** 0.5
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
