"""PlayerModel: modelo estadístico, interpretable y contextual de un jugador.

Cada métrica es una tasa con distribución Beta(α, β). Se guarda por contexto
(lance × situación del marcador) y se consulta con *back-off jerárquico*: si el contexto
concreto tiene poca muestra, su estimación se encoge hacia la del contexto padre.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

METRICS: tuple[str, ...] = (
    "aggression",
    "risk_tolerance",
    "bluff_frequency",
    "acceptance_rate",
    "rejection_rate",
    "raise_rate",
    "ordago_rate",
    "mus_rate",
)

PRIORS: dict[str, float] = {
    "aggression": 0.3,
    "risk_tolerance": 0.3,
    "bluff_frequency": 0.15,
    "acceptance_rate": 0.45,
    "rejection_rate": 0.5,
    "raise_rate": 0.1,
    "ordago_rate": 0.03,
    "mus_rate": 0.5,
}
"""Media a priori de cada métrica (jugador "típico"). Configurable."""

PRIOR_STRENGTH = 2.0
"""Peso del prior en observaciones equivalentes."""

SHRINK_K = 6.0
"""Cuántas observaciones del contexto hacen falta para fiarse de él tanto como del padre."""

ANY = "*"
SCORE_CONTEXTS: tuple[str, ...] = ("ahead", "behind", "close", "even")
LANCE_CONTEXTS: tuple[str, ...] = ("mus", "grande", "chica", "pares", "juego", "punto")


def score_context(my_score: int, their_score: int, target: int) -> str:
    """Situación del marcador desde el punto de vista del jugador."""
    if max(my_score, their_score) >= target - 8:
        return "close"
    diff = my_score - their_score
    if diff > 5:
        return "ahead"
    if diff < -5:
        return "behind"
    return "even"


def confidence_label(confidence: float) -> str:
    if confidence >= 0.7:
        return "Alta"
    if confidence >= 0.4:
        return "Media"
    return "Baja"


@dataclass
class Rate:
    """Tasa con posterior Beta. ``successes`` y ``trials`` son ponderados (admiten olvido)."""

    successes: float = 0.0
    trials: float = 0.0

    def update(self, success: bool, weight: float = 1.0) -> None:
        self.trials += weight
        if success:
            self.successes += weight

    def decay(self, factor: float) -> None:
        self.successes *= factor
        self.trials *= factor

    def mean(self, prior: float, strength: float = PRIOR_STRENGTH) -> float:
        return (self.successes + prior * strength) / (self.trials + strength)

    def to_list(self) -> list[float]:
        return [round(self.successes, 4), round(self.trials, 4)]


@dataclass(frozen=True)
class Estimate:
    """Estimación con su incertidumbre. Nunca una certeza."""

    value: float
    confidence: float
    n: float

    @property
    def label(self) -> str:
        return confidence_label(self.confidence)

    def describe(self) -> str:
        return f"{self.value:.0%} (confianza {self.label.lower()}, n={self.n:.0f})"


@dataclass
class PlayerModel:
    """Modelo de un jugador: tasas por (métrica, lance, marcador)."""

    player_id: str
    rates: dict[tuple[str, str, str], Rate] = field(default_factory=dict)
    games: int = 0

    def _rate(self, metric: str, lance: str, score: str) -> Rate:
        key = (metric, lance, score)
        if key not in self.rates:
            self.rates[key] = Rate()
        return self.rates[key]

    def record(self, metric: str, success: bool, lance: str = ANY, score: str = ANY) -> None:
        """Registra una observación en el contexto concreto y en todos sus padres."""
        if metric not in METRICS:
            raise ValueError(f"Métrica desconocida: {metric}")
        for lance_key in {lance, ANY}:
            for score_key in {score, ANY}:
                self._rate(metric, lance_key, score_key).update(success)

    def estimate(self, metric: str, lance: str = ANY, score: str = ANY) -> Estimate:
        """Estimación con back-off: contexto → (lance, *) → (*, *) → prior."""
        prior = PRIORS[metric]
        chain = [(ANY, ANY)]
        if lance != ANY:
            chain.append((lance, ANY))
        if score != ANY:
            chain.append((lance, score))
        mean = prior
        n = 0.0
        for lance_key, score_key in chain:
            rate = self.rates.get((metric, lance_key, score_key))
            if rate is None:
                continue
            mean = (rate.successes + SHRINK_K * mean) / (rate.trials + SHRINK_K)
            n = rate.trials
        confidence = n / (n + SHRINK_K) if n > 0 else 0.0
        return Estimate(min(1.0, max(0.0, mean)), confidence, n)

    def decay(self, factor: float) -> None:
        for rate in self.rates.values():
            rate.decay(factor)

    def sample_size(self, metric: str = "aggression") -> float:
        rate = self.rates.get((metric, ANY, ANY))
        return rate.trials if rate else 0.0

    def scale_confidence(self, factor: float) -> None:
        """Reduce la confianza conservando las medias (tras detectar un cambio de estrategia)."""
        self.decay(factor)

    # ----------------------------------------------------------- serialización
    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "games": self.games,
            "rates": {"|".join(k): r.to_list() for k, r in self.rates.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlayerModel:
        model = cls(data["player_id"], games=data.get("games", 0))
        for key, (s, t) in data.get("rates", {}).items():
            metric, lance, score = key.split("|")
            model.rates[(metric, lance, score)] = Rate(s, t)
        return model

    def profile(self) -> dict[str, dict[str, Any]]:
        """Vista agregada (PlayerProfile) para la pantalla de estilo de juego."""
        out: dict[str, dict[str, Any]] = {}
        for metric in METRICS:
            est = self.estimate(metric)
            out[metric] = {"value": est.value, "confidence": est.label, "n": est.n}
        return out


def js_divergence(p: float, q: float) -> float:
    """Divergencia de Jensen-Shannon entre dos Bernoulli (en bits)."""

    def h(x: float) -> float:
        if x <= 0 or x >= 1:
            return 0.0
        return -(x * math.log2(x) + (1 - x) * math.log2(1 - x))

    m = (p + q) / 2
    return h(m) - (h(p) + h(q)) / 2
