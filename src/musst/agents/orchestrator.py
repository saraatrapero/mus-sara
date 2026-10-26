"""Agente orquestador y bots basados en agentes (niveles Medio y Profesional)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from musst.agents.base import Agent, AgentContext, Decision
from musst.agents.specialists import (
    BehaviourAgent,
    BluffAgent,
    CardAgent,
    PartnerAgent,
    ProbabilityAgent,
    ScoreAgent,
)
from musst.agents.strategy import Judge, MusPlanner, StrategyAgent
from musst.bots.api import Action, Bot, GameEndInfo, GameStartInfo, Observation
from musst.learning.updater import Learner, LearningUpdate


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
    extra: dict[str, Any] = field(default_factory=dict)


LEVELS: dict[str, LevelConfig] = {
    "medio": LevelConfig(
        "medio",
        ("cartas", "probabilidad", "marcador"),
        samples=150,
        samples_deep=300,
        risk_aversion=0.35,
        noise=0.05,
        learn=False,
    ),
    "profesional": LevelConfig(
        "profesional",
        ("cartas", "comportamiento", "probabilidad", "farol", "marcador", "pareja"),
        samples=300,
        samples_deep=800,
        risk_aversion=0.25,
        noise=0.0,
        learn=True,
    ),
}

AGENT_FACTORIES: dict[str, type[Agent]] = {
    "cartas": CardAgent,
    "comportamiento": BehaviourAgent,
    "probabilidad": ProbabilityAgent,
    "farol": BluffAgent,
    "marcador": ScoreAgent,
    "pareja": PartnerAgent,
}


class Orchestrator:
    """Decide qué agentes consultar, cuándo hacer análisis profundo y entrega al Juez."""

    def __init__(self, level: LevelConfig) -> None:
        self.level = level
        self.agents = {name: AGENT_FACTORIES[name]() for name in level.agents}
        self.strategy = StrategyAgent()
        self.judge = Judge(level.risk_aversion, level.noise)
        self.planner = MusPlanner(level.cut_threshold)

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
    ) -> None:
        self.level = LEVELS[level]
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

    def on_game_start(self, info: GameStartInfo) -> None:
        self.seat = info.seat
        self.target = info.target
        ids = info.context.get("player_ids") if info.context else None
        names = ids if isinstance(ids, list | tuple) else info.player_names
        self.player_ids = {s: str(names[s]) for s in range(4) if s != info.seat}
        self.decisions = []

    def decide(self, observation: Observation) -> Action:
        ctx = AgentContext(
            observation,
            self.rng,
            {"samples": self.level.samples, "samples_deep": self.level.samples_deep},
            self.learner,
            self.player_ids,
        )
        decision = self.orchestrator.decide(ctx)
        self.last_decision = decision
        self.decisions.append(decision)
        return decision.action

    def on_game_end(self, info: GameEndInfo) -> None:
        if self.learner is None or not self.level.learn:
            return
        self.last_learning = self.learner.learn_game(
            list(info.history), self.player_ids, self.target
        )


class MediumBot(AgentBot):
    """Nivel MEDIO: Monte Carlo + marcador, sin modelo del rival."""

    def __init__(self, seed: int | None = None) -> None:
        super().__init__("medio", seed)


class ProBot(AgentBot):
    """Nivel PROFESIONAL: todos los agentes + PlayerModel con aprendizaje."""

    def __init__(self, seed: int | None = None, learner: Learner | None = None) -> None:
        super().__init__("profesional", seed, learner)
