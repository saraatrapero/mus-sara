"""Bayes, equidad de partida, valor esperado y agentes matemáticos."""

import importlib.util
import json
import math
import random
from pathlib import Path

import pytest

from musst.agents.mathematical import MathJudge
from musst.agents.orchestrator import AgentBot, MathBot, MediumBot
from musst.engine import evaluation as ev
from musst.engine.actions import CutMusAction, OrdagoAction
from musst.engine.cards import full_deck, parse_hand
from musst.engine.game import MusGame
from musst.engine.observation import build_observation
from musst.probability import equity
from musst.probability.bayes import (
    BehaviourModel,
    Evidence,
    bayes_update,
    evidence_from,
    posterior_weights,
)
from musst.probability.decision import ActionValue, DecisionModel
from musst.probability.estimators import Method, weighted_proportion
from musst.probability.lances import analyze
from musst.probability.round_points_data import COUNTS, ROUNDS
from musst.probability.sampler import SeatConstraint, WorldSampler, sample_worlds
from musst.runtime.runner import play_game

MINE = parse_hand("12O 12C 1E 5B")
POOL = [c for c in full_deck() if c not in MINE]


def kings(hand):
    return sum(1 for c in hand if c.rank in (12, 3))


# ------------------------------------------------------------------ Bayes
def test_bayes_con_un_ejemplo_conocido():
    # Prueba diagnóstica: prevalencia 1 %, sensibilidad 90 %, falsos positivos 5 %.
    post, evidence = bayes_update(
        {"enfermo": 0.01, "sano": 0.99}, {"enfermo": 0.9, "sano": 0.05}.get
    )
    assert evidence == pytest.approx(0.0585)
    assert post["enfermo"] == pytest.approx(0.009 / 0.0585)
    assert sum(post.values()) == pytest.approx(1.0)


def test_un_envite_desplaza_la_creencia_pero_no_es_una_certeza():
    pool = tuple(random.Random(4).sample(POOL, 16))
    sampler = WorldSampler(0, MINE, pool, {})
    model = BehaviourModel()
    bet = [Evidence(1, "bet", "grande", 1)]
    exact = list(sampler.exact_worlds())
    prior_2k = sum(p for w, p in exact if kings(w[1]) >= 2)
    post_exact = {i: p * model.world_likelihood(bet, w) for i, (w, p) in enumerate(exact)}
    z = sum(post_exact.values())
    post_2k = sum(post_exact[i] for i, (w, _) in enumerate(exact) if kings(w[1]) >= 2) / z
    post_0k = sum(post_exact[i] for i, (w, _) in enumerate(exact) if kings(w[1]) == 0) / z
    assert post_2k > prior_2k  # envidar a grande hace más probable que tenga reyes…
    assert post_0k > 0  # …pero no descarta que vaya de farol
    # Monte Carlo ponderado con la misma verosimilitud converge a la posterior exacta.
    worlds, weights = sample_worlds(sampler, random.Random(9), 6000)
    pw = posterior_weights(worlds, weights, bet, model)
    est = weighted_proportion(
        [1.0 if kings(w[1]) >= 2 else 0.0 for w in worlds], pw, Method.POSTERIOR
    )
    assert abs(est.value - post_2k) <= 4 * est.se


def test_todas_las_verosimilitudes_tienen_suelo():
    model = BehaviourModel()
    hands = [parse_hand("4O 5C 6E 7B"), parse_hand("12O 12C 3E 3B"), parse_hand("1O 1C 2E 2B")]
    for kind in ("bet", "ordago", "pass", "accept", "reject", "mus", "cut"):
        for lance in ("grande", "chica", "pares", "juego", "punto"):
            for h in hands:
                p = model.likelihood(Evidence(1, kind, lance), h)
                assert 0 < p <= 1


def _game_until(predicate, seed=0, limit=4000):
    game = MusGame(seed=seed)
    bots = [MediumBot(seed * 10 + i) for i in range(4)]
    for _ in range(limit):
        if game.finished:
            return None
        if predicate(game):
            return game
        seat = game.turn
        game.apply(seat, bots[seat].decide(build_observation(game, seat)))
    return None


def test_evidencias_salen_del_historial_publico():
    for seed in range(30):
        game = _game_until(
            lambda g: any(
                e.kind.value == "BetPlaced" and e.actor in (1, 3)
                for e in g.events
                if e.round_no == g.round_no
            ),
            seed,
        )
        if game is not None:
            break
    assert game is not None
    obs = build_observation(game, 0)
    evidence = evidence_from(obs)
    assert any(e.kind == "bet" and e.seat in (1, 3) for e in evidence)
    assert all(e.seat != 0 for e in evidence)  # lo que hago yo no es evidencia


# ------------------------------------------------------------------ equidad
def test_equidad_simetrica_monotona_y_en_rango():
    total = sum(p for _, _, p in equity.round_distribution())
    assert total == pytest.approx(1.0)
    assert sum(COUNTS.values()) == ROUNDS
    for a in (1, 5, 20, 40):
        for b in (1, 5, 20, 40):
            e = equity.win_probability(a, b)
            assert 0 <= e <= 1
            assert e + equity.win_probability(b, a) == pytest.approx(1.0)
    assert equity.win_probability(40, 40) == pytest.approx(0.5)
    assert (
        equity.win_probability(1, 40)
        > equity.win_probability(10, 40)
        > equity.win_probability(30, 40)
    )
    assert equity.win_probability(0, 5) == 1.0 and equity.win_probability(5, 0) == 0.0


def test_la_tabla_de_tantos_es_reproducible():
    path = Path(__file__).resolve().parents[2] / "scripts" / "round_points.py"
    spec = importlib.util.spec_from_file_location("round_points", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.rounds_of(3) == module.rounds_of(3)


# ------------------------------------------------------------------ valor esperado
def _facing_ordago():
    for seed in range(50):
        game = MusGame(seed=seed)
        while game.phase.value in ("mus",):
            game.apply(game.turn, CutMusAction())
        if game.phase.value != "grande":
            continue
        game.apply(game.turn, OrdagoAction())
        obs = build_observation(game, game.turn)
        if "accept" in obs.legal_types():
            return obs
    raise AssertionError("no se llegó a un órdago")


def test_querer_un_ordago_vale_la_probabilidad_de_ganar_el_lance():
    obs = _facing_ordago()
    sampler = WorldSampler.from_observation(obs)
    worlds, weights = sample_worlds(sampler, random.Random(3), 500)
    values = {
        v.action.type: v for v in DecisionModel(obs, worlds, weights, BehaviourModel()).evaluate()
    }
    p_win = (
        analyze(worlds, weights, obs.mano, obs.team, Method.MONTE_CARLO, ["grande"])
        .lances["grande"]
        .win
    )
    assert values["accept"].ev == pytest.approx(p_win.value)
    assert values["accept"].points_mean is None  # en un órdago no se juegan tantos, sino la partida
    for v in values.values():
        assert 0 <= v.ev <= 1 and v.var >= 0


def test_valor_esperado_de_un_envite_coincide_con_la_formula():
    obs = _facing_ordago()  # cualquier observación sirve para el modelo; se evalúa a mano
    sampler = WorldSampler.from_observation(obs)
    worlds, weights = sample_worlds(sampler, random.Random(8), 200)
    model = DecisionModel(obs, worlds, weights, BehaviourModel())
    opps = [s for s in range(4) if s % 2 != obs.team]
    acc = [model.p_team_accepts(opps, w, 4) for w in worlds]
    # EV = Σ w·[(1 − a)·U(no quieren) + a·U(quieren)] / Σ w
    manual = sum(
        w
        * (
            (1 - a) * model.utility(*model.rejected(i, 1, True))
            + a * model.utility(*model.accepted(i, 4))
        )
        for i, (w, a) in enumerate(zip(weights, acc, strict=True))
    ) / sum(weights)
    from musst.engine.actions import BetAction

    value = model._bet(BetAction(4), 4, ordago=False)
    assert value.ev == pytest.approx(manual)


# ------------------------------------------------------------------ agentes y bot
def test_el_bot_matematico_juega_una_partida_legal_y_explica_sus_decisiones():
    bots = [MathBot(1), MediumBot(2), MathBot(3), MediumBot(4)]
    match = play_game(bots, seed=21)
    assert match.result.reason in ("points", "ordago")
    assert match.errors == []  # ni excepciones, ni jugadas ilegales, ni tiempos excedidos
    explained = [d for d in bots[0].decisions if d.math]
    assert explained
    expl = explained[-1].explanation()
    json.dumps(expl)  # serializable
    m = expl["matematica"]
    for key in (
        "estado",
        "informacion_conocida",
        "informacion_desconocida",
        "metodo",
        "acciones",
        "justificacion",
    ):
        assert key in m
    for lance in m.get("probabilidades", {}).values():
        post = lance["a_posteriori"]
        assert sum(post[k]["p"] for k in ("gana", "pierde", "nadie")) == pytest.approx(
            1.0, abs=2e-4
        )


@pytest.mark.parametrize(
    "level", ["mat_exacto", "mat_bayes", "mat_mc", "mat_utilidad", "matematico"]
)
def test_todas_las_variantes_juegan_sin_errores(level):
    bots = [AgentBot(level, 5), MediumBot(6), AgentBot(level, 7), MediumBot(8)]
    match = play_game(bots, seed=33)
    assert match.result.winner in (0, 1)
    assert match.errors == []


def test_el_juez_matematico_rechaza_calculos_invalidos():
    obs = _facing_ordago()
    from musst.agents.base import AgentContext
    from musst.agents.mathematical import Belief
    from musst.engine.actions import AcceptAction

    sampler = WorldSampler.from_observation(obs)
    ctx = AgentContext(obs, random.Random(0), {})
    ctx.shared["belief"] = Belief(
        sampler, [], [], [], [], BehaviourModel(), Method.MONTE_CARLO, False, 1.0
    )
    bad = [ActionValue(AcceptAction(), math.nan, 0.0, None, None)]
    problems = MathJudge().validate(ctx, bad)
    assert any("EV no válido" in p for p in problems)
    assert any("sin repartos" in p for p in problems)
    decision = MathJudge().decide(ctx, bad)
    assert decision.action.type in obs.legal_types()
    assert decision.narrative.startswith("validación")


def test_las_cartas_ocultas_nunca_se_usan():
    """Dos partidas idénticas salvo en las cartas de los rivales: misma observación y misma
    decisión del bot matemático (con la misma semilla)."""
    game = MusGame(seed=5)
    while game.phase.value == "mus":
        game.apply(game.turn, CutMusAction())
    seat = game.turn
    other = game.clone()
    a, b = [s for s in range(4) if s != seat][:2]
    other.hands[a], other.hands[b] = other.hands[b], other.hands[a]
    obs1, obs2 = build_observation(game, seat), build_observation(other, seat)
    assert obs1 == obs2
    d1 = MathBot(seed=7)
    d2 = MathBot(seed=7)
    from musst.bots.api import GameStartInfo

    for bot in (d1, d2):
        bot.on_game_start(
            GameStartInfo(seat, (seat + 2) % 4, seat % 2, 40, ("a", "b", "c", "d"), {})
        )
    assert d1.decide(obs1) == d2.decide(obs2)
    assert d1.last_decision.explanation() == d2.last_decision.explanation()


def test_la_restriccion_de_declaraciones_se_respeta():
    sampler = WorldSampler(
        0, MINE, tuple(POOL), {1: SeatConstraint(pares=False), 3: SeatConstraint(juego=True)}
    )
    rng = random.Random(1)
    for _ in range(200):
        w = sampler.sample(rng).world
        assert not ev.pairs(w[1]).has_pairs
        assert ev.has_juego(w[3])
