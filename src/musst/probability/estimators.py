"""Estimaciones con su incertidumbre: exacta, Monte Carlo o posterior bayesiana.

Cada probabilidad que produce el motor lleva **cómo se ha calculado**. Una estimación de
Monte Carlo nunca se presenta como exacta: lleva su error estándar y su intervalo de confianza.

Monte Carlo ponderado (muestreo de importancia autonormalizado). Con mundos ``x_i`` y pesos
``w_i`` (prior × verosimilitud de la evidencia, ver :mod:`musst.probability.bayes`)::

    p̂  = Σ w_i·f(x_i) / Σ w_i
    ESS = (Σ w_i)² / Σ w_i²                      (tamaño efectivo de la muestra)
    SE  = √( Σ w_i²·(f(x_i) − p̂)² ) / Σ w_i      (método delta)

Con pesos iguales, ESS = n y SE = √(p̂(1 − p̂)/n), el error estándar binomial habitual.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

Z95 = 1.959963984540054
"""Cuantil 0.975 de la normal estándar (intervalos al 95 %)."""


class Method(str, Enum):
    EXACT = "exacta"
    """Enumeración completa del espacio muestral (hipergeométrica multivariante)."""
    ANALYTIC = "analitica_aproximada"
    """Marginales exactas de cada asiento combinadas como si fueran independientes."""
    MONTE_CARLO = "monte_carlo"
    """Frecuencia sobre repartos simulados (a priori: sin usar las acciones observadas)."""
    POSTERIOR = "posterior_bayesiana"
    """P(· | evidencia) por Bayes, estimada con Monte Carlo ponderado (o exacta, ver ``exact``)."""


@dataclass(frozen=True)
class ProbabilityEstimate:
    value: float
    method: Method
    se: float = 0.0
    low: float | None = None
    high: float | None = None
    n: int = 0
    ess: float = 0.0
    exact: bool = False
    """``True`` si no hay error de muestreo (enumeración completa)."""

    @property
    def interval(self) -> tuple[float, float]:
        return (
            self.value if self.low is None else self.low,
            self.value if self.high is None else self.high,
        )

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {"p": round(self.value, 4), "metodo": self.method.value}
        if self.exact:
            out["exacta"] = True
        else:
            low, high = self.interval
            out.update(
                {
                    "se": round(self.se, 4),
                    "ic95": [round(low, 4), round(high, 4)],
                    "n": self.n,
                    "ess": round(self.ess, 1),
                }
            )
        return out


def wilson_interval(p: float, n: float, z: float = Z95) -> tuple[float, float]:
    """Intervalo de Wilson para una proporción (bien comportado cerca de 0 y 1)."""
    if n <= 0:
        return (0.0, 1.0)
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(max(0.0, p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def effective_sample_size(weights: Sequence[float]) -> float:
    s = sum(weights)
    s2 = sum(w * w for w in weights)
    return s * s / s2 if s2 > 0 else 0.0


def weighted_proportion(
    values: Sequence[float], weights: Sequence[float], method: Method
) -> ProbabilityEstimate:
    """p̂, SE (método delta) e IC95 de Wilson con n = ESS."""
    total = sum(weights)
    n = len(values)
    if total <= 0 or n == 0:
        return ProbabilityEstimate(0.0, method, 1.0, 0.0, 1.0, n, 0.0)
    p = sum(w * v for w, v in zip(weights, values, strict=True)) / total
    p = min(1.0, max(0.0, p))
    var = sum(w * w * (v - p) ** 2 for w, v in zip(weights, values, strict=True)) / (total * total)
    ess = effective_sample_size(weights)
    low, high = wilson_interval(p, ess)
    return ProbabilityEstimate(p, method, math.sqrt(var), low, high, n, ess)


def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> tuple[float, float, float]:
    """Media, varianza (de la variable) y error estándar de la media, ponderados."""
    total = sum(weights)
    if total <= 0 or not values:
        return 0.0, 0.0, 0.0
    mean = sum(w * v for w, v in zip(weights, values, strict=True)) / total
    var = sum(w * (v - mean) ** 2 for w, v in zip(weights, values, strict=True)) / total
    se = (
        math.sqrt(sum(w * w * (v - mean) ** 2 for w, v in zip(weights, values, strict=True)))
        / total
    )
    return mean, var, se


def exact(value: float) -> ProbabilityEstimate:
    return ProbabilityEstimate(value, Method.EXACT, exact=True)
