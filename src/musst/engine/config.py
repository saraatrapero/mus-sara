"""Configuración de reglas. Ningún número del tanteo está escrito a fuego en el motor.

Los valores marcados como [CONVENCIÓN] no aparecen en el Reglamento FEM; ver
``docs/game-rules.md``.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RulesConfig:
    """Parámetros de una partida."""

    target_points: int = 40
    """Tantos para ganar el juego (FEM Intro E: entre 40 y 60)."""
    eight_kings: bool = True
    """Modalidad ocho reyes y ocho ases (FEM II.3)."""
    min_bet: int = 2
    """Envido = dos tantos (FEM VIII.8)."""
    max_bet: int = 99
    """Tope técnico de una apuesta; la FEM permite cualquier cantidad (VI.6, VI.8)."""
    negada_points: int = 1
    """Tanto por no aceptar la primera apuesta de un lance (FEM VIII.8)."""
    paso_points: int = 1
    """[CONVENCIÓN] Valor de grande y chica en paso (FEM VII.2 lo menciona, no lo cuantifica)."""
    par_points: int = 1
    """[CONVENCIÓN]"""
    medias_points: int = 2
    """[CONVENCIÓN]"""
    duples_points: int = 3
    """[CONVENCIÓN]"""
    juego_31_points: int = 3
    """[CONVENCIÓN]"""
    juego_points: int = 2
    """[CONVENCIÓN] Valor de cualquier juego que no sea 31."""
    punto_points: int = 1
    """[CONVENCIÓN]"""
    min_discard: int = 1
    """[CONVENCIÓN] Cartas mínimas a descartar tras dar mus."""
    max_mus_rounds: int = 10
    """Salvaguarda técnica: tras N rondas de mus se obliga a cortar (evita bucles infinitos)."""
    end_on_immediate_points: bool = True
    """Si una negada en el acto alcanza el objetivo, el juego termina inmediatamente (P8a)."""
    team_in_threshold: int = 4
    """Faltan ≤ N tantos ⇒ "estamos dentro" (FEM VII.7)."""
    signals_enabled: bool = False
    """Señas oficiales (FEM VIII) con miradas. Desactivadas, el juego es idéntico."""
    gaze_min_ticks: int = 1
    """Duración mínima de una mirada, en pasos de tiempo (acciones o ``tick()``)."""
    gaze_max_ticks: int = 3
    """Duración máxima de una mirada."""
    gaze_weights: tuple[float, float, float] = (0.4, 0.4, 0.2)
    """Probabilidad de mirar al compañero, a uno de los rivales (repartida entre los dos) o a la mesa."""

    def __post_init__(self) -> None:
        if not 1 <= self.target_points <= 200:
            raise ValueError("target_points fuera de rango")
        if self.min_bet < 1 or self.max_bet < self.min_bet:
            raise ValueError("min_bet/max_bet inválidos")
        if not 1 <= self.min_discard <= 4:
            raise ValueError("min_discard debe estar entre 1 y 4")
        if not 1 <= self.gaze_min_ticks <= self.gaze_max_ticks:
            raise ValueError("gaze_min_ticks/gaze_max_ticks inválidos")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RulesConfig:
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Claves de configuración desconocidas: {sorted(unknown)}")
        if "gaze_weights" in data:
            data = {**data, "gaze_weights": tuple(data["gaze_weights"])}
        return cls(**data)

    @classmethod
    def from_toml(cls, path: str | Path) -> RulesConfig:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        return cls.from_dict(data.get("rules", data))
