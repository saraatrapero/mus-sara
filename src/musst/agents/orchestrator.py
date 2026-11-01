"""Agente orquestador y bots basados en agentes (niveles Medio y Profesional)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from musst.agents.base import Agent, AgentContext, Decision
from musst.agents.mathematical import (
    BayesianAgent,
    DecisionEvaluatorAgent,
    MathAnalystAgent,
    MathJudge,
    MathProbabilityAgent,
)
from musst.agents.specialists import (
    BehaviourAgent,
    BluffAgent,
    CardAgent,
    CountingAgent,
    PartnerAgent,
    ProbabilityAgent,
    ScoreAgent,
)
from musst.agents.strategy import Judge, MusPlanner, StrategyAgent
from musst.bots.api import Action, Bot, GameEndInfo, GameStartInfo, Observation
from musst.engine.signals import Signal
from musst.learning.self_review import ReviewedDecision, SelfReview
from musst.learning.updater import Learner, LearningUpdate

SIGNAL_PRIORITY: tuple[str, ...] = (
    Signal.DUPLES.value,
    Signal.TREINTA_Y_UNA.value,
    Signal.MEDIAS_REYES.value,
    Signal.DOS_REYES.value,
    Signal.MEDIAS_ASES.value,
    Signal.MEDIAS.value,
    Signal.JUEGO.value,
    Signal.DOS_ASES.value,
    Signal.PARES.value,
    Signal.TREINTA.value,
    Signal.VEINTINUEVE.value,
    Signal.CIEGO.value,
)
"""Qué seña interesa más pasar al compañero si hay varias verdaderas."""
LANCE_KINDS = {"pass", "bet", "raise", "ordago", "accept", "reject", "accept_no_lose"}


@dataclass(frozen=True)
class LevelConfig:
    """Qué agentes consulta cada nivel y con qué parámetros (ver config/agents.toml)."""

    name: str
    agents: tuple[str, ...]
    samples: int
    samples_deep: int
    risk_aversion: float
    noise: float
    learn: bool
    cut_threshold: float = 0.42
    signal_policy: str = "cuidadoso"
    """``cuidadoso``: solo si le mira el compañero y ningún rival. ``descuidado``: le basta
    con que le mire el compañero."""
    self_review: bool = False
    """Revisa sus decisiones al acabar cada partida y corrige sus estimaciones."""
    read_bets: bool = True
    """Lee los envites del rival en el lance actual."""
    read_all: bool = False
    """Lee toda la jugada: pasos, envites, aceptaciones y rechazos de los otros tres, en todos
    los lances (quien pasa en grande suele llevar la grande floja; si mi compañero envida, mi
    pareja es más fuerte)."""
    team_bonus: bool = False
    """Cuenta los tantos de la jugada de toda la pareja (pares/juego), no solo los propios."""
    discard_draws: int = 10
    """Reposiciones simuladas por cada descarte posible (0 = descarte heurístico clásico)."""
    bluff_rate: float = 0.1
    """Frecuencia de farol deliberado cuando la mano no da para envidar."""
    ordago_sure: float = 0.8
    """P(ganar si lo quieren) a partir de la cual echa órdago sin estar desesperado."""
    math: str = ""
    """Motor probabilístico (``musst.probability``): ``""`` ninguno (niveles de siempre);
    ``analitica``/``mc``/``bayes`` sustituyen al agente de probabilidad y mantienen la
    estrategia y el juez de siempre; ``utilidad`` y ``completo`` deciden por valor esperado
    de P(ganar la partida) con el juez matemático (``completo`` usa además Bayes con las
    acciones observadas y el PlayerModel)."""
    extra: dict[str, Any] = field(default_factory=dict)


LEVELS: dict[str, LevelConfig] = {
    # Medio: calcula con sus cartas y lee el envite del lance actual, pero no conoce a los
    # rivales, simula pocas manos, descarta "de manual" y se equivoca a menudo en las
    # decisiones ajustadas (no por farolear: los faroles están limitados en todos los niveles).
    "medio": LevelConfig(
        "medio",
        ("cartas", "probabilidad", "marcador"),
        samples=90,
        samples_deep=90,
        risk_aversion=0.35,
        noise=0.3,
        learn=False,
        signal_policy="descuidado",
        discard_draws=0,
        bluff_rate=0.1,
    ),
    # Profesional: todos los agentes, más simulaciones, análisis profundo en jugadas críticas,
    # modelo de cada rival, conteo, jugada de toda la pareja, descarte simulado, señas
    # cuidadosas y autocrítica entre partidas.
    "profesional": LevelConfig(
        "profesional",
        ("cartas", "conteo", "comportamiento", "probabilidad", "farol", "marcador", "pareja"),
        samples=300,
        samples_deep=800,
        risk_aversion=0.25,
        noise=0.0,
        learn=True,
        self_review=True,
        team_bonus=True,
        discard_draws=30,
        bluff_rate=0.07,
    ),
}


def _math_level(name: str, agents: tuple[str, ...], math: str, learn: bool = False) -> LevelConfig:
    """Variantes del motor probabilístico: mismas decisiones de mus y descarte que el
    profesional; cambia solo cómo se calculan las probabilidades y cómo se decide."""
    return LevelConfig(
        name,
        agents,
        samples=200,
        samples_deep=600,
        risk_aversion=0.25,
        noise=0.0,
        learn=learn,
        discard_draws=30,
        bluff_rate=0.07,
        math=math,
    )


_PRO_AGENTS = ("cartas", "comportamiento", "probabilidad", "farol", "marcador", "pareja")
# Variantes del experimento académico (docs/probabilidad.md).
LEVELS.update(
    {
        # B: marginales exactas (hipergeométrica) combinadas con independencia.
        "mat_exacto": _math_level("mat_exacto", _PRO_AGENTS, "analitica"),
        # C: Monte Carlo exacto + Bayes con las acciones observadas.
        "mat_bayes": _math_level("mat_bayes", _PRO_AGENTS, "bayes"),
        # D: Monte Carlo exacto, sin usar las acciones observadas.
        "mat_mc": _math_level("mat_mc", _PRO_AGENTS, "mc"),
        # E: Monte Carlo + valor esperado de P(ganar la partida), sin Bayes.
        "mat_utilidad": _math_level(
            "mat_utilidad", ("bayesiano", "analista", "evaluador"), "utilidad"
        ),
        # F: completo: PlayerModel + Bayes + Monte Carlo + utilidad esperada + juez matemático.
        "matematico": _math_level(
            "matematico", ("comportamiento", "bayesiano", "analista", "evaluador"), "completo", True
        ),
    }
)

AGENT_FACTORIES: dict[str, type[Agent]] = {
    "cartas": CardAgent,
    "conteo": CountingAgent,
    "comportamiento": BehaviourAgent,
    "probabilidad": ProbabilityAgent,
    "farol": BluffAgent,
    "marcador": ScoreAgent,
    "pareja": PartnerAgent,
    "bayesiano": BayesianAgent,
    "analista": MathAnalystAgent,
    "evaluador": DecisionEvaluatorAgent,
}


class Orchestrator:
    """Decide qué agentes consultar, cuándo hacer análisis profundo y entrega al Juez."""

    def __init__(self, level: LevelConfig) -> None:
        self.level = level
        self.agents = {name: AGENT_FACTORIES[name]() for name in level.agents}
        if level.math in ("analitica", "mc", "bayes"):
            self.agents["probabilidad"] = MathProbabilityAgent(level.math)
        if level.math in ("utilidad", "completo"):
            self.agents["bayesiano"] = BayesianAgent(use_evidence=level.math == "completo")
        self.math_judge = MathJudge()
        self.strategy = StrategyAgent()
        self.judge = Judge(level.risk_aversion, level.noise)
        self.planner = MusPlanner(level.cut_threshold, level.discard_draws)

    def needs_deep_analysis(self, obs: Observation) -> bool:
        bet = obs.current_bet
        near_end = max(obs.score) >= obs.target - 8
        return bool((bet is not None and (bet.is_ordago or bet.stake >= 8)) or near_end)

    def decide(self, ctx: AgentContext) -> Decision:
        obs = ctx.obs
        types = obs.legal_types()
        if "mus" in types or "cut" in types:
            action = self.planner.mus(ctx)
            return Decision(
                action, 0.6, {}, ("cartas",), narrative="decisión de mus por valor de mano"
            )
        if "discard" in types:
            action = self.planner.discard(ctx)
            return Decision(action, 0.6, {}, ("cartas",), narrative="descarte por valor esperado")
        ctx.deep = self.needs_deep_analysis(obs)
        for name in self.level.agents:
            if name == "farol" and obs.current_bet is None:
                continue  # solo tiene sentido ante un envite rival
            ctx.reports[name] = self.agents[name].analyze(ctx)
        if self.level.math in ("utilidad", "completo"):
            return self.math_judge.decide(ctx, ctx.shared.get("values", []))
        candidates = self.strategy.candidates(ctx)
        return self.judge.decide(ctx, candidates)


class AgentBot(Bot):
    """Bot cuya decisión sale del orquestador de agentes."""

    author = "MUS.ST"
    version = "1.0"

    def __init__(
        self,
        level: str = "profesional",
        seed: int | None = None,
        learner: Learner | None = None,
        learn_opponents: bool = True,
    ) -> None:
        self.level = LEVELS[level]
        self.learn_opponents = learn_opponents
        """``False`` cuando otro (el servidor) ya aprende de los jugadores con la misma memoria."""
        self.name = level
        self.rng = random.Random(seed)
        self.orchestrator = Orchestrator(self.level)
        self.learner = learner if learner is not None else (Learner() if self.level.learn else None)
        self.player_ids: dict[int, str] = {}
        self.seat = 0
        self.target = 40
        self.last_decision: Decision | None = None
        self.decisions: list[Decision] = []
        self.last_learning: list[LearningUpdate] = []
        self.review_log: list[ReviewedDecision] = []
        self.self_review_summary: list[str] = []
        self._review: SelfReview | None = None

    @property
    def self_key(self) -> str:
        return f"self:{self.level.name}"

    def review_memory(self) -> SelfReview | None:
        """Autocrítica persistente (en el mismo almacén que los modelos de jugador)."""
        if not self.level.self_review or self.learner is None:
            return None
        if self._review is None:
            model = self.learner.long_model(self.self_key)
            self._review = SelfReview.from_dict(model.extra.get("self_review"))
        return self._review

    def on_game_start(self, info: GameStartInfo) -> None:
        self.seat = info.seat
        self.target = info.target
        ids = info.context.get("player_ids") if info.context else None
        names = ids if isinstance(ids, list | tuple) else info.player_names
        self.player_ids = {s: str(names[s]) for s in range(4) if s != info.seat}
        self.decisions = []
        self.review_log = []

    def decide(self, observation: Observation) -> Action:
        ctx = AgentContext(
            observation,
            self.rng,
            {
                "samples": self.level.samples,
                "samples_deep": self.level.samples_deep,
                "self_review": self.review_memory(),
                "read_bets": self.level.read_bets,
                "read_all": self.level.read_all,
                "bluff_rate": self.level.bluff_rate,
                "ordago_sure": self.level.ordago_sure,
                "team_bonus": self.level.team_bonus,
            },
            self.learner,
            self.player_ids,
        )
        decision = self.orchestrator.decide(ctx)
        self.last_decision = decision
        self.decisions.append(decision)
        kind = decision.action.type
        if kind in LANCE_KINDS and "probabilidad" in ctx.reports:
            self.review_log.append(
                ReviewedDecision(
                    observation.round_no,
                    observation.phase,
                    "accept" if kind == "accept_no_lose" else kind,
                    ctx.estimate("probabilidad", "p_win").value,
                    observation.seat,
                    observation.mano,
                )
            )
        return decision.action

    def signal(self, observation: Observation) -> str | None:
        """Pasa la mejor seña verdadera cuando le mira su compañero (y, si es cuidadoso,
        cuando no le mira ningún rival)."""
        available = set(observation.available_signals)
        if not available or not observation.gazes:
            return None
        gazes = observation.gazes
        partner_looks = gazes[observation.partner] == observation.seat
        rival_looks = any(gazes[r] == observation.seat for r in observation.opponents)
        if not partner_looks or (self.level.signal_policy == "cuidadoso" and rival_looks):
            return None
        if observation.signals_seen.get(observation.seat):
            return None  # una seña por jugada basta: más gestos, más riesgo de que la vean
        return next((s for s in SIGNAL_PRIORITY if s in available), None)

    def on_game_end(self, info: GameEndInfo) -> None:
        if self.learner is None or not self.level.learn:
            return
        if self.learn_opponents:
            self.last_learning = self.learner.learn_game(
                list(info.history), self.player_ids, self.target
            )
        self._review = None  # recarga: otro bot del mismo nivel puede haber guardado ya
        review = self.review_memory()
        if review is not None:
            lost = info.winner != self.seat % 2
            self.self_review_summary = review.review(self.review_log, info.history, lost)
            model = self.learner.long_model(self.self_key)
            model.extra["self_review"] = review.to_dict()
            self.learner.store.save(model)


class MediumBot(AgentBot):
    """Nivel MEDIO: Monte Carlo + marcador, sin modelo del rival."""

    def __init__(self, seed: int | None = None) -> None:
        super().__init__("medio", seed)


class MathBot(AgentBot):
    """Nivel MATEMÁTICO: Bayes + Monte Carlo exacto + valor esperado de P(ganar la partida)."""

    def __init__(
        self, seed: int | None = None, learner: Learner | None = None, learn_opponents: bool = True
    ) -> None:
        super().__init__("matematico", seed, learner, learn_opponents)


class ProBot(AgentBot):
    """Nivel PROFESIONAL: todos los agentes + PlayerModel con aprendizaje."""

    def __init__(
        self, seed: int | None = None, learner: Learner | None = None, learn_opponents: bool = True
    ) -> None:
        super().__init__("profesional", seed, learner, learn_opponents)
