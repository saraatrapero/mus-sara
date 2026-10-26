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
    "bet_with_strong",
    "bet_with_weak",
    "accept_with_weak",
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
    "bet_with_strong": 0.7,
    "bet_with_weak": 0.1,
    "accept_with_weak": 0.2,
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
    stakes: dict[str, list[float]] = field(default_factory=dict)
    """Piedras envidadas por tipo de mano: ``"grande|fuerte" -> [suma, veces]``."""
    drift_recent: bool = False
    """En la última partida cambió de estrategia (ver ``Learner``)."""
    extra: dict[str, Any] = field(default_factory=dict)
    """Datos de otros aprendices (p. ej. la autocrítica del bot) con la misma persistencia."""

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

    def record_stake(self, lance: str, bucket: str, amount: float) -> None:
        for key in (f"{lance}|{bucket}", f"{ANY}|{bucket}"):
            entry = self.stakes.setdefault(key, [0.0, 0.0])
            entry[0] += amount
            entry[1] += 1

    def mean_stake(self, bucket: str, lance: str = ANY) -> tuple[float | None, float]:
        """Piedras medias envidadas con ese tipo de mano y nº de veces observado."""
        total, n = self.stakes.get(f"{lance}|{bucket}", [0.0, 0.0])
        return (total / n if n else None), n

    def decay(self, factor: float) -> None:
        for rate in self.rates.values():
            rate.decay(factor)
        for entry in self.stakes.values():
            entry[0] *= factor
            entry[1] *= factor

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
            "stakes": self.stakes,
            "drift_recent": self.drift_recent,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlayerModel:
        model = cls(
            data["player_id"],
            games=data.get("games", 0),
            stakes={k: list(v) for k, v in data.get("stakes", {}).items()},
            drift_recent=bool(data.get("drift_recent", False)),
            extra=dict(data.get("extra", {})),
        )
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

    def style(self) -> dict[str, Any]:
        """Etiqueta de estilo con su confianza (para jugadores y para el panel de administración).

        Cada estilo puntúa cuánto se separa el jugador del jugador típico (``PRIORS``) en las
        métricas que lo definen, ponderado por la confianza de cada métrica.
        """

        def dev(metric: str) -> tuple[float, float]:
            est = self.estimate(metric)
            return est.value - PRIORS[metric], est.confidence

        scores: dict[str, tuple[float, float]] = {}

        def put(name: str, *parts: tuple[float, float]) -> None:
            value = sum(d for d, _ in parts) / len(parts)
            conf = min(c for _, c in parts)
            scores[name] = (value, conf)

        put("farolero", dev("bet_with_weak"), dev("bluff_frequency"))
        put("arriesgado", dev("ordago_rate"), dev("risk_tolerance"), dev("accept_with_weak"))
        a, ca = dev("aggression")
        acc, cacc = dev("acceptance_rate")
        put("conservador", (-a, ca), (-acc, cacc))
        bs, cbs = dev("bet_with_strong")
        put("de tapado", (-bs, cbs))
        bw, cbw = dev("bet_with_weak")
        put("cauto", (-bw, cbw), (-acc, cacc))
        confidence = max((c for _, c in scores.values()), default=0.0)
        if confidence < 0.2:
            return {
                "label": "sin datos aún",
                "confidence": confidence_label(confidence),
                "scores": {},
            }
        if self.drift_recent:
            label = "imprevisible"
        else:
            name, (value, conf) = max(scores.items(), key=lambda kv: kv[1][0] * kv[1][1])
            label = name if value * conf > 0.03 else "equilibrado"
        return {
            "label": label,
            "confidence": confidence_label(confidence),
            "scores": {k: round(v * c, 3) for k, (v, c) in scores.items()},
        }


def js_divergence(p: float, q: float) -> float:
    """Divergencia de Jensen-Shannon entre dos Bernoulli (en bits)."""

    def h(x: float) -> float:
        if x <= 0 or x >= 1:
            return 0.0
        return -(x * math.log2(x) + (1 - x) * math.log2(1 - x))

    m = (p + q) / 2
    return h(m) - (h(p) + h(q)) / 2
