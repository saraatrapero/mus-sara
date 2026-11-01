"""Validación matemática del motor probabilístico (musst.probability)."""

import itertools
import random
from math import comb, isclose

import pytest

from musst.engine import evaluation as ev
from musst.engine.cards import Card, full_deck, parse_hand
from musst.probability.combinatorics import (
    enumerate_deals,
    hand_distribution,
    hypergeom_pmf,
    rank_classes,
)
from musst.probability.estimators import (
    Method,
    effective_sample_size,
    weighted_proportion,
    wilson_interval,
)
from musst.probability.sampler import SeatConstraint, WorldSampler, sample_worlds

ORDER = [0, 1, 2, 3]
MINE = parse_hand("12O 12C 1E 5B")
POOL = [c for c in full_deck() if c not in MINE]


def team_wins(lance, world):
    w = ev.lance_winner(lance, world, ORDER)
    return 1.0 if w is not None and w % 2 == 0 else 0.0


# ------------------------------------------------------------------ combinatoria
def test_hipergeometrica_suma_uno_y_coincide_con_la_formula():
    # 36 cartas desconocidas, 6 reyes (8 − 2 míos): P(k reyes en 4 cartas)
    pmf = [hypergeom_pmf(36, 6, 4, k) for k in range(5)]
    assert isclose(sum(pmf), 1.0)
    assert all(p >= 0 for p in pmf)
    assert isclose(pmf[2], comb(6, 2) * comb(30, 2) / comb(36, 4))
    assert hypergeom_pmf(36, 6, 4, 5) == 0.0


def test_hipergeometrica_no_es_binomial():
    # Sin reemplazo: P(4 reyes) es menor que con reemplazo (binomial).
    binom = (6 / 36) ** 4
    assert hypergeom_pmf(36, 6, 4, 4) < binom


def test_distribucion_exacta_de_una_mano_coincide_con_fuerza_bruta():
    dist = hand_distribution(rank_classes().counts(POOL), rank_classes())
    assert isclose(dist.total(), 1.0, abs_tol=1e-12)
    assert all(p > 0 for _, p in dist.items)
    hands = list(itertools.combinations(POOL, 4))
    assert len(hands) == comb(36, 4)
    for event in (
        lambda h: ev.pairs(h).has_pairs,
        ev.has_juego,
        lambda h: ev.total_points(h) == 31,
        lambda h: ev.pairs(h).kind is ev.PairsKind.DUPLES,
    ):
        brute = sum(1 for h in hands if event(h)) / len(hands)
        assert isclose(dist.probability(event), brute, abs_tol=1e-12)


def test_condicionar_es_bayes_con_verosimilitud_cero_uno():
    classes = rank_classes()
    counts = classes.counts(POOL)
    prior = hand_distribution(counts, classes)
    post = hand_distribution(counts, classes, condition=ev.has_juego)
    p_juego = prior.probability(ev.has_juego)
    p_31 = prior.probability(lambda h: ev.total_points(h) == 31)
    # P(31 | juego) = P(juego | 31)·P(31) / P(juego) = P(31) / P(juego)
    assert isclose(post.probability(lambda h: ev.total_points(h) == 31), p_31 / p_juego)
    assert isclose(post.total(), 1.0)


def test_mis_descartes_cambian_el_espacio_muestral():
    classes = rank_classes()
    full = hand_distribution(classes.counts(POOL), classes)
    # Si me he descartado de los otros dos reyes de verdad (12E, 12B), quedan 4 reyes (los treses).
    pool = [c for c in POOL if c not in (Card.parse("12E"), Card.parse("12B"))]
    less = hand_distribution(classes.counts(pool), classes)
    king = lambda h: any(c.rank in (12, 3) for c in h)  # noqa: E731
    assert less.probability(king) < full.probability(king)
    assert isclose(less.probability(king), 1 - comb(30, 4) / comb(34, 4))


def test_enumeracion_de_repartos_suma_uno():
    pool = random.Random(3).sample(POOL, 12)
    deals = list(enumerate_deals(pool, (1, 2, 3), rank_classes()))
    assert isclose(sum(p for _, p in deals), 1.0)
    for world, _ in deals:  # cartas reales y distintas del mazo desconocido
        cards = [c for h in world.values() for c in h]
        assert len(set(cards)) == 12 and set(cards) <= set(pool)


# ------------------------------------------------------------------ Monte Carlo vs exacto
@pytest.mark.parametrize("lance", ["grande", "chica", "pares", "juego", "punto"])
def test_monte_carlo_converge_al_valor_exacto_con_restricciones(lance):
    rng = random.Random(11)
    pool = tuple(rng.sample(POOL, 16))
    constraints = {1: SeatConstraint(pares=True), 3: SeatConstraint(juego=False)}
    sampler = WorldSampler(0, MINE, pool, constraints)
    exact = sum(p * team_wins(lance, w) for w, p in sampler.exact_worlds())
    worlds, weights = sample_worlds(sampler, random.Random(5), 4000)
    est = weighted_proportion([team_wins(lance, w) for w in worlds], weights, Method.MONTE_CARLO)
    assert abs(est.value - exact) <= 4 * est.se + 1e-9
    low, high = est.interval
    assert low - 1e-9 <= est.value <= high + 1e-9


def test_el_muestreo_respeta_restricciones_y_cartas_conocidas():
    constraints = {
        1: SeatConstraint(pares=True, juego=True),
        2: SeatConstraint(pares=False),
        3: SeatConstraint(juego=False, signals=frozenset({"treinta"})),
    }
    sampler = WorldSampler(0, MINE, tuple(POOL), constraints)
    rng = random.Random(2)
    for _ in range(300):
        s = sampler.sample(rng)
        assert s.weight > 0
        cards = [c for h in s.world.values() for c in h]
        assert len(set(cards)) == 16
        assert s.world[0] == MINE
        assert not set(MINE) & {c for seat in (1, 2, 3) for c in s.world[seat]}
        for seat, c in constraints.items():
            assert c.admits(s.world[seat])


def test_reproducible_con_la_misma_semilla():
    sampler = WorldSampler(0, MINE, tuple(POOL), {1: SeatConstraint(pares=True)})
    a = sample_worlds(sampler, random.Random(42), 50)
    b = sample_worlds(sampler, random.Random(42), 50)
    assert a == b


# ------------------------------------------------------------------ estimadores
def test_wilson_y_tamano_efectivo():
    low, high = wilson_interval(0.5, 100)
    assert 0.40 < low < 0.41 and 0.59 < high < 0.60
    assert effective_sample_size([1.0] * 10) == pytest.approx(10)
    assert effective_sample_size([1.0, 0.0, 0.0]) == pytest.approx(1)
    est = weighted_proportion([1, 0, 1, 1], [1, 1, 1, 1], Method.MONTE_CARLO)
    assert est.value == 0.75 and est.se == pytest.approx((0.75 * 0.25 / 4) ** 0.5)


def test_un_reparto_imposible_sale_completo_y_con_peso_cero():
    # Regresión: con 16 cartas bajas nadie puede tener juego (máximo 7+7+6+6 = 26).
    low = tuple(c for c in POOL if c.rank in (4, 5, 6, 7))[:12]
    sampler = WorldSampler(0, MINE, low, {1: SeatConstraint(juego=True)})
    s = sampler.sample(random.Random(0))
    assert s.weight == 0.0
    assert set(s.world) == {0, 1, 2, 3}
    assert all(len(h) == 4 for h in s.world.values())
