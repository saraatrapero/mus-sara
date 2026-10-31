"""Agentes matemáticos: bayesiano, analista, evaluador de decisiones y juez matemático.

Comparten una representación probabilística común en ``ctx.shared``:

* ``belief`` (:class:`Belief`) — repartos posibles de las cartas desconocidas con sus pesos a
  priori (combinatoria) y a posteriori (Bayes con las acciones observadas). Lo crea el agente
  bayesiano y lo usan todos los demás: nadie vuelve a muestrear por su cuenta.
* ``analysis`` — probabilidades de cada lance y distribución de tantos (agente analista).
* ``values`` — valor esperado de cada acción legal (agente evaluador).

Ninguno ve más que la :class:`~musst.engine.observation.Observation` del bot.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from musst.agents.base import Agent, AgentContext, AgentReport, Decision, Estimate, ScoredAction
from musst.engine.actions import PassAction, RejectAction
from musst.engine.cards import Card
from musst.engine.evaluation import LANCES
from musst.learning.player_model import PRIORS
from musst.probability.bayes import (
    BehaviourModel,
    Evidence,
    SeatBehaviour,
    evidence_from,
)
from musst.probability.decision import ActionValue, DecisionModel, best_action, label
from musst.probability.equity import win_probability
from musst.probability.estimators import Method, effective_sample_size, weighted_proportion
from musst.probability.lances import (
    RoundAnalysis,
    analytic_win_probability,
    analyze,
    lance_outcome,
)
from musst.probability.sampler import WorldSampler, constraints_from

BATCH = 100
TOLERANCE = 0.025
"""Criterio de convergencia: error estándar de P(ganar el lance actual) ≤ 0.025."""
AGGRESSION_THRESHOLD_SHIFT = 0.8


@dataclass
class Belief:
    sampler: WorldSampler
    worlds: list[dict[int, tuple[Any, ...]]]
    prior: list[float]
    posterior: list[float]
    evidence: list[Evidence]
    behaviour: BehaviourModel
    method: Method
    converged: bool
    se: float

    @property
    def n(self) -> int:
        return len(self.worlds)


def behaviour_from(ctx: AgentContext) -> BehaviourModel:
    """Parámetros del modelo de decisiones de cada rival, aprendidos por el PlayerModel
    (agente de comportamiento) si se ha consultado; si no, los valores a priori."""
    seats: dict[int, SeatBehaviour] = {}
    if "comportamiento" not in ctx.reports:
        return BehaviourModel(seats)
    for seat in ctx.obs.opponents:
        bluff = ctx.estimate("comportamiento", f"bluff_frequency_{seat}", PRIORS["bluff_frequency"])
        aggr = ctx.estimate("comportamiento", f"aggression_{seat}", PRIORS["aggression"])
        acc = ctx.estimate("comportamiento", f"acceptance_rate_{seat}", PRIORS["acceptance_rate"])
        shift = (aggr.value - PRIORS["aggression"]) * AGGRESSION_THRESHOLD_SHIFT * aggr.confidence
        accept_tau = 0.55 - 0.6 * (acc.value - PRIORS["acceptance_rate"]) * acc.confidence
        seats[seat] = SeatBehaviour(
            bluff=bluff.value,
            bet_threshold=max(0.35, min(0.9, 0.7 - shift)),
            accept_threshold=max(0.3, min(0.85, accept_tau)),
        )
    return BehaviourModel(seats)


def _win_indicator(
    ctx: AgentContext, belief_worlds: list[dict[int, tuple[Any, ...]]]
) -> list[float]:
    lance = ctx.lance if ctx.lance in LANCES else "grande"
    return [
        1.0 if lance_outcome(lance, w, ctx.obs.mano, ctx.obs.team)[0] == "gana" else 0.0
        for w in belief_worlds
    ]


class BayesianAgent(Agent):
    """Construye la creencia sobre las manos ajenas: Monte Carlo exacto + Bayes.

    Número adaptativo de repartos: lotes de ``BATCH`` hasta que el error estándar de P(ganar
    el lance actual) baja de ``TOLERANCE`` (con un mínimo y un máximo por nivel)."""

    name = "bayesiano"

    def __init__(self, use_evidence: bool = True) -> None:
        self.use_evidence = use_evidence

    def analyze(self, ctx: AgentContext) -> AgentReport:
        obs = ctx.obs
        report = AgentReport(self.name)
        sampler = WorldSampler.from_observation(obs)
        behaviour = behaviour_from(ctx)
        evidence = evidence_from(obs) if self.use_evidence else []
        # Mínimo ``samples``; si no converge (p. ej. porque la evidencia concentra el peso en
        # pocos repartos y baja el ESS), se sigue hasta ``samples_deep``.
        n_min = int(ctx.config.get("samples", 200))
        n_max = max(n_min, int(ctx.config.get("samples_deep", n_min)))
        worlds: list[dict[int, tuple[Any, ...]]] = []
        prior: list[float] = []
        post: list[float] = []
        se = 1.0
        converged = False
        while len(worlds) < n_max:
            for _ in range(BATCH):
                s = sampler.sample(ctx.rng)
                worlds.append(s.world)
                prior.append(s.weight)
                post.append(
                    s.weight * behaviour.world_likelihood(evidence, s.world) if s.weight else 0.0
                )
            est = weighted_proportion(_win_indicator(ctx, worlds), post, Method.POSTERIOR)
            se = est.se
            if len(worlds) >= n_min and se <= TOLERANCE:
                converged = True
                break
        method = Method.POSTERIOR if evidence else Method.MONTE_CARLO
        ctx.shared["belief"] = Belief(
            sampler, worlds, prior, post, evidence, behaviour, method, converged, se
        )
        report.estimates["n"] = Estimate(float(len(worlds)), 1.0)
        report.estimates["ess_prior"] = Estimate(effective_sample_size(prior), 1.0)
        report.estimates["ess_posterior"] = Estimate(effective_sample_size(post), 1.0)
        report.notes.append(
            f"{len(worlds)} repartos; ESS a posteriori {effective_sample_size(post):.0f}; "
            + ("converge" if converged else "sin converger (máximo de muestras)")
        )
        for e in evidence:
            report.notes.append("Evidencia: " + e.describe())
        return report


class MathAnalystAgent(Agent):
    """Probabilidades de cada lance (a priori y a posteriori) y distribución de tantos."""

    name = "analista"

    def analyze(self, ctx: AgentContext) -> AgentReport:
        report = AgentReport(self.name)
        belief: Belief = ctx.shared["belief"]
        obs = ctx.obs
        post = analyze(belief.worlds, belief.posterior, obs.mano, obs.team, belief.method)
        prior = analyze(belief.worlds, belief.prior, obs.mano, obs.team, Method.MONTE_CARLO)
        ctx.shared["analysis"] = post
        ctx.shared["analysis_prior"] = prior
        if ctx.lance in post.lances:
            p = post.lances[ctx.lance].win
            report.estimates["p_win"] = Estimate(p.value, max(0.0, 1 - 4 * p.se), p.n)
            report.notes.append(
                f"P(ganar {ctx.lance}) = {p.value:.3f} ± {1.96 * p.se:.3f} "
                f"(a priori {prior.lances[ctx.lance].win.value:.3f})"
            )
        return report


class DecisionEvaluatorAgent(Agent):
    """EV(a) = Σ_s P(s | E)·U(a, s) para cada acción legal del lance."""

    name = "evaluador"

    def analyze(self, ctx: AgentContext) -> AgentReport:
        report = AgentReport(self.name)
        belief: Belief = ctx.shared["belief"]
        model = DecisionModel(ctx.obs, belief.worlds, belief.posterior, belief.behaviour)
        values = model.evaluate()
        ctx.shared["values"] = values
        for v in values:
            report.estimates[f"ev_{label(v.action)}"] = Estimate(v.ev, 1.0)
        return report


class MathProbabilityAgent(Agent):
    """Sustituto del agente de probabilidad para los experimentos B, C y D: mismas claves que
    :class:`~musst.agents.specialists.ProbabilityAgent` (para la estrategia y el juez de
    siempre), calculadas con el motor nuevo.

    * ``analitica`` — marginales exactas + independencia (B);
    * ``mc`` — Monte Carlo exacto sin usar las acciones observadas (D);
    * ``bayes`` — Monte Carlo + Bayes con las acciones observadas (C).
    """

    name = "probabilidad"

    def __init__(self, mode: str) -> None:
        self.mode = mode

    def analyze(self, ctx: AgentContext) -> AgentReport:
        obs = ctx.obs
        report = AgentReport(self.name)
        if ctx.lance not in LANCES:
            return report
        behaviour = behaviour_from(ctx)
        if self.mode == "analitica":
            return self._analytic(ctx, behaviour)
        BayesianAgent(use_evidence=self.mode == "bayes").analyze(ctx)
        belief: Belief = ctx.shared["belief"]
        model = DecisionModel(obs, belief.worlds, belief.posterior, behaviour)
        win = [1.0 if o == "gana" else 0.0 for o in model.outcome]
        p = weighted_proportion(win, belief.posterior, belief.method)
        conf = max(0.0, 1 - 4 * p.se)
        opps = [s for s in model.players_of_lance() if s % 2 != obs.team]
        bet = [model.p_team_accepts(opps, w, 2) for w in belief.worlds]
        ordago = [model.p_team_accepts(opps, w, 0, ordago=True) for w in belief.worlds]
        d_bet = model._acceptance_details(bet)
        d_ord = model._acceptance_details(ordago)
        w_total = sum(belief.posterior) or 1.0
        wins_w = sum(w * x for w, x in zip(belief.posterior, win, strict=True))
        bonus = sum(
            w * x * pv for w, x, pv in zip(belief.posterior, win, model.pv_mine, strict=True)
        )
        report.estimates["p_win"] = Estimate(p.value, conf, p.n)
        report.estimates["team_bonus"] = Estimate(bonus / wins_w if wins_w else 0.0, conf, p.n)
        report.estimates["p_accept_bet"] = Estimate(d_bet["p_quieren"], conf, p.n)
        report.estimates["p_win_if_accept_bet"] = Estimate(d_bet["p_gano_si_quieren"], conf, p.n)
        report.estimates["p_accept_ordago"] = Estimate(d_ord["p_quieren"], conf, p.n)
        report.estimates["p_win_if_accept_ordago"] = Estimate(d_ord["p_gano_si_quieren"], conf, p.n)
        report.notes.append(
            f"P(ganar {ctx.lance}) = {p.value:.3f} ± {1.96 * p.se:.3f} ({p.method.value}, "
            f"n={p.n}, w_total={w_total:.2f})"
        )
        return report

    def _analytic(self, ctx: AgentContext, behaviour: BehaviourModel) -> AgentReport:
        obs = ctx.obs
        report = AgentReport(self.name)
        sampler = WorldSampler.from_observation(obs)
        constraints = constraints_from(obs)
        args = (obs.hand, obs.seat, obs.mano, ctx.lance, sampler.pool, constraints)
        p = analytic_win_probability(*args)
        probe = DecisionModel(obs, [], [], behaviour)

        def accepts(ordago: bool) -> Callable[[int, tuple[Card, ...]], float]:
            # verosimilitud de «quiere» de cada rival
            return lambda seat, hand: probe.p_accept(seat, {seat: hand}, 2, ordago)

        p_bet = analytic_win_probability(*args, opponent_weight=accepts(False))
        p_ord = analytic_win_probability(*args, opponent_weight=accepts(True))
        report.estimates["p_win"] = Estimate(p.value, 1.0)
        report.estimates["p_win_if_accept_bet"] = Estimate(p_bet.value, 1.0)
        report.estimates["p_win_if_accept_ordago"] = Estimate(p_ord.value, 1.0)
        report.notes.append(f"P(ganar {ctx.lance}) ≈ {p.value:.3f} ({p.method.value})")
        return report


class MathJudge:
    """Juez matemático: valida los cálculos y elige argmax E[P(ganar la partida)]."""

    name = "juez_matematico"

    def validate(self, ctx: AgentContext, values: list[ActionValue]) -> list[str]:
        problems: list[str] = []
        belief: Belief = ctx.shared["belief"]
        if not belief.posterior or sum(belief.posterior) <= 0:
            problems.append("sin repartos con peso a posteriori")
        analysis: RoundAnalysis | None = ctx.shared.get("analysis")
        if analysis is not None:
            for lance, lp in analysis.lances.items():
                parts = (lp.win.value, lp.lose.value, lp.nobody.value)
                if any(not 0.0 <= x <= 1.0 for x in (*parts, lp.tie_cards.value)):
                    problems.append(f"probabilidad fuera de [0, 1] en {lance}")
                if abs(sum(parts) - 1.0) > 1e-6:
                    problems.append(f"P(gana)+P(pierde)+P(nadie) ≠ 1 en {lance}")
        legal = ctx.obs.legal_types()
        for v in values:
            if not (math.isfinite(v.ev) and 0.0 <= v.ev <= 1.0):
                problems.append(f"EV no válido en {label(v.action)}")
            if v.action.type not in legal:
                problems.append(f"acción ilegal propuesta: {label(v.action)}")
        if not values:
            problems.append("ninguna acción evaluada")
        return problems

    def decide(self, ctx: AgentContext, values: list[ActionValue]) -> Decision:
        obs = ctx.obs
        problems = self.validate(ctx, values)
        if problems:
            legal = obs.legal_types()
            fallback = PassAction() if "pass" in legal else RejectAction()
            if fallback.type not in legal:
                fallback = obs.legal_actions[0].default()  # type: ignore[assignment]
            return Decision(
                fallback,
                0.0,
                {},
                tuple(ctx.reports),
                narrative="validación: " + "; ".join(problems),
            )
        belief: Belief = ctx.shared["belief"]
        ess = max(1.0, effective_sample_size(belief.posterior))
        ranked = sorted(values, key=lambda v: v.ev, reverse=True)
        chosen = best_action(values)
        second = next((v for v in ranked if v is not chosen), None)
        if second is None:
            confidence = 0.99
        else:
            # P(la elegida es de verdad mejor) ≈ Φ(Δ / √(SE₁² + SE₂²)), SE ≈ √(Var/ESS).
            se = math.sqrt((chosen.var + second.var) / ess) or 1e-9
            confidence = 0.5 * (1 + math.erf((chosen.ev - second.ev) / se / math.sqrt(2)))
        narrative = "; ".join(f"EV({label(v.action)})={v.ev:.4f}" for v in ranked[:3])
        math_expl = self.explanation(ctx, values, chosen, second, confidence)
        alternatives = tuple(
            ScoredAction(v.action, v.ev, math.sqrt(v.var), {"ev_tantos": v.points_mean or 0.0})
            for v in ranked
        )
        p_win = ctx.estimate("analista", "p_win", 0.5).value
        return Decision(
            chosen.action,
            max(0.01, min(0.99, confidence)),
            {"p_win": p_win, "ev": chosen.ev, "risk": math.sqrt(chosen.var)},
            tuple(ctx.reports),
            alternatives,
            narrative,
            math_expl,
        )

    def explanation(
        self,
        ctx: AgentContext,
        values: list[ActionValue],
        chosen: ActionValue,
        second: ActionValue | None,
        confidence: float,
    ) -> dict[str, Any]:
        obs = ctx.obs
        belief: Belief = ctx.shared["belief"]
        analysis: RoundAnalysis | None = ctx.shared.get("analysis")
        prior: RoundAnalysis | None = ctx.shared.get("analysis_prior")
        mine, theirs = obs.score[obs.team], obs.score[1 - obs.team]
        known_out = sorted(c.code for c in set(belief.sampler.hand))
        out: dict[str, Any] = {
            "estado": {
                "lance": obs.phase,
                "marcador": {"mi_pareja": mine, "rivales": theirs, "objetivo": obs.target},
                "asiento": obs.seat,
                "mano": obs.mano,
                "p_ganar_partida_ahora": round(
                    win_probability(obs.target - mine, obs.target - theirs), 4
                ),
            },
            "informacion_conocida": {
                "mis_cartas": known_out,
                "cartas_que_no_tienen_los_demas": 40 - len(belief.sampler.pool),
                "declaraciones": {
                    k: {str(s): v for s, v in d.items()} for k, d in obs.declarations.items()
                },
                "senas_vistas": {
                    str(s): list(v) for s, v in obs.signals_seen.items() if s != obs.seat
                },
                "acciones_observadas": [e.describe() for e in belief.evidence],
            },
            "informacion_desconocida": {
                "cartas_desconocidas": len(belief.sampler.pool),
                "asientos": list(belief.sampler.others),
            },
            "metodo": {
                "cartas": "muestreo exacto condicionado (hipergeométrica multivariante) con pesos de importancia",
                "decisiones_rivales": "Bayes: P(H|E) ∝ P(E|H)·P(H)"
                if belief.evidence
                else "sin evidencia: a priori",
                "repartos": belief.n,
                "ess_a_priori": round(effective_sample_size(belief.prior), 1),
                "ess_a_posteriori": round(effective_sample_size(belief.posterior), 1),
                "converge": belief.converged,
                "se_p_ganar_lance": round(belief.se, 4),
                "utilidad": "P(ganar la partida) tras el lance (cadena de Markov sobre el marcador)",
            },
            "acciones": [v.to_dict() for v in sorted(values, key=lambda v: v.ev, reverse=True)],
            "accion_elegida": label(chosen.action),
        }
        if analysis is not None:
            out["probabilidades"] = {
                lance: {
                    "a_posteriori": lp.to_dict(),
                    **(
                        {"a_priori": prior.lances[lance].win.to_dict()} if prior is not None else {}
                    ),
                }
                for lance, lp in analysis.lances.items()
            }
            out["tantos_de_la_jugada_en_paso"] = analysis.points.to_dict()
        if second is not None:
            out["justificacion"] = (
                f"{label(chosen.action)} maximiza la probabilidad esperada de ganar la partida: "
                f"{chosen.ev:.4f} frente a {second.ev:.4f} de {label(second.action)} "
                f"(diferencia {chosen.ev - second.ev:+.4f}; P(que de verdad sea mejor) ≈ {confidence:.2f})."
            )
        else:
            out["justificacion"] = f"{label(chosen.action)} es la única acción evaluada."
        return out
