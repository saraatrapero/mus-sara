"""Tipos comunes de la arquitectura de agentes.

Los agentes **solo leen** la observación y la memoria de su propio bot. No ejecutan acciones:
producen informes que el Juez combina en una :class:`Decision`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from musst.engine.actions import Action, action_to_dict
from musst.engine.observation import Observation
from musst.learning.player_model import confidence_label
from musst.learning.updater import Learner


@dataclass(frozen=True)
class Estimate:
    value: float
    confidence: float
    n: float = 0.0

    def describe(self) -> str:
        return f"{self.value:.0%} (confianza {confidence_label(self.confidence).lower()})"


@dataclass
class AgentReport:
    agent: str
    estimates: dict[str, Estimate] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class AgentContext:
    """Todo lo que los agentes pueden consultar para una decisión."""

    obs: Observation
    rng: random.Random
    config: dict[str, Any]
    learner: Learner | None = None
    player_ids: dict[int, str] = field(default_factory=dict)
    reports: dict[str, AgentReport] = field(default_factory=dict)
    deep: bool = False

    def estimate(self, agent: str, key: str, default: float = 0.5) -> Estimate:
        report = self.reports.get(agent)
        if report is None or key not in report.estimates:
            return Estimate(default, 0.0)
        return report.estimates[key]

    @property
    def lance(self) -> str:
        return self.obs.phase


@dataclass(frozen=True)
class ScoredAction:
    action: Action
    ev: float
    risk: float
    factors: dict[str, float]

    def label(self) -> str:
        data = action_to_dict(self.action)
        return data["type"].upper() + (f"_{data['amount']}" if "amount" in data else "")


@dataclass(frozen=True)
class Decision:
    """Salida del Juez: acción, confianza, evidencia y agentes consultados."""

    action: Action
    confidence: float
    evidence: dict[str, float]
    agents_consulted: tuple[str, ...]
    alternatives: tuple[ScoredAction, ...] = ()
    narrative: str = ""

    def explanation(self) -> dict[str, Any]:
        """DecisionExplanation: para depuración, modo desarrollo y la defensa."""
        chosen = action_to_dict(self.action)
        return {
            "decision": chosen["type"].upper()
            + (f"_{chosen['amount']}" if "amount" in chosen else ""),
            "factors": {k: round(v, 3) for k, v in self.evidence.items()},
            "confidence": round(self.confidence, 3),
            "agents_consulted": list(self.agents_consulted),
            "alternatives": [
                {"action": a.label(), "ev": round(a.ev, 3), "risk": round(a.risk, 3)}
                for a in self.alternatives
            ],
            "narrative": self.narrative,
        }


class Agent:
    """Agente especializado: ``analyze`` añade su informe al contexto."""

    name = "agent"

    def analyze(self, ctx: AgentContext) -> AgentReport:
        raise NotImplementedError
