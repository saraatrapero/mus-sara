"""Autocrítica del bot: aprender de sus errores sin aprender supersticiones.

En el Mus se puede perder jugando bien. Si el bot castigara todo lo que acaba en derrota,
aprendería supersticiones. En su lugar, al terminar cada partida revisa **sus propias
decisiones** con las manos que se enseñaron al final de cada jugada (FEM VII.9):

* compara la probabilidad que estimó de ganar el lance con lo que de verdad ocurrió
  (calibración por tramos de probabilidad y por lance);
* marca como **error** solo lo que con las cartas reales era peor que la alternativa
  (aceptar un envite que perdía, rechazar uno que ganaba, envidar sin ganar el lance).

Después corrige sus estimaciones con esa calibración: si en pares cree ganar el 70 % de las
veces que acepta pero solo gana el 50 %, a partir de ahí estimará cerca del 50 %. La corrección
se encoge hacia la estimación original mientras hay pocos datos (``SHRINK``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from musst.bots.toolkit import lance_winner
from musst.engine.cards import Card

SHRINK = 8.0
"""Observaciones de un tramo necesarias para fiarse de él tanto como de la estimación."""
BUCKETS = 10


@dataclass
class ReviewedDecision:
    round_no: int
    lance: str
    kind: str  # bet | raise | ordago | accept | reject | pass
    p_win: float
    seat: int
    mano: int


@dataclass
class SelfReview:
    """Memoria de calibración y de errores del propio bot (serializable)."""

    calibration: dict[str, list[float]] = field(
        default_factory=dict
    )  # "lance|tramo" -> [aciertos, n]
    mistakes: dict[str, list[float]] = field(default_factory=dict)  # "lance|tipo" -> [errores, n]
    games: int = 0
    lost_games: int = 0

    # ------------------------------------------------------------------ uso
    def correct(self, lance: str, p: float) -> float:
        """Probabilidad corregida con lo aprendido (igual a ``p`` si no hay datos)."""
        bucket = min(BUCKETS - 1, int(p * BUCKETS))
        wins, n = self.calibration.get(f"{lance}|{bucket}", [0.0, 0.0])
        if n == 0:
            return p
        return (wins + SHRINK * p) / (n + SHRINK)

    def error_rate(self, lance: str, kind: str) -> tuple[float, float]:
        errors, n = self.mistakes.get(f"{lance}|{kind}", [0.0, 0.0])
        return (errors / n if n else 0.0), n

    # ------------------------------------------------------------------ aprendizaje
    def review(
        self, decisions: Sequence[ReviewedDecision], history: Sequence[dict[str, Any]], lost: bool
    ) -> list[str]:
        """Revisa las decisiones de una partida terminada. Devuelve un resumen legible."""
        hands = _revealed(history)
        errors: list[str] = []
        reviewed = 0
        for d in decisions:
            world = hands.get(d.round_no)
            if world is None:
                continue  # jugada sin manos enseñadas: no se puede juzgar
            winner = lance_winner(d.lance, world, d.mano)
            if winner is None:
                continue
            won = winner % 2 == d.seat % 2
            reviewed += 1
            bucket = min(BUCKETS - 1, int(d.p_win * BUCKETS))
            entry = self.calibration.setdefault(f"{d.lance}|{bucket}", [0.0, 0.0])
            entry[0] += won
            entry[1] += 1
            wrong = (d.kind in ("bet", "raise", "ordago", "accept") and not won) or (
                d.kind == "reject" and won
            )
            stats = self.mistakes.setdefault(f"{d.lance}|{d.kind}", [0.0, 0.0])
            stats[0] += wrong
            stats[1] += 1
            if wrong and d.kind != "pass":
                errors.append(
                    f"Jugada {d.round_no}, {d.lance}: {_verb(d.kind)} creyendo ganar el "
                    f"{d.p_win:.0%} y con las cartas reales {'ganaba' if won else 'perdía'}."
                )
        self.games += 1
        self.lost_games += lost
        summary = [f"Autocrítica: {reviewed} decisiones revisadas con las cartas enseñadas."]
        summary += errors[:5]
        if not errors and reviewed:
            summary.append("Ninguna decisión fue peor que su alternativa con las cartas reales.")
        return summary

    # ------------------------------------------------------------------ serialización
    def to_dict(self) -> dict[str, Any]:
        return {
            "calibration": self.calibration,
            "mistakes": self.mistakes,
            "games": self.games,
            "lost_games": self.lost_games,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SelfReview:
        data = data or {}
        return cls(
            {k: list(v) for k, v in data.get("calibration", {}).items()},
            {k: list(v) for k, v in data.get("mistakes", {}).items()},
            int(data.get("games", 0)),
            int(data.get("lost_games", 0)),
        )


def _verb(kind: str) -> str:
    return {
        "bet": "envidé",
        "raise": "subí",
        "ordago": "eché órdago",
        "accept": "acepté",
        "reject": "rechacé",
    }.get(kind, kind)


def _revealed(history: Sequence[dict[str, Any]]) -> dict[int, dict[int, tuple[Card, ...]]]:
    out: dict[int, dict[int, tuple[Card, ...]]] = {}
    for e in history:
        if e["kind"] == "HandsRevealed":
            out[e["round"]] = {
                int(s): tuple(Card.parse(c) for c in cs) for s, cs in e["payload"]["hands"].items()
            }
    return out
