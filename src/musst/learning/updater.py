"""Actualización post-partida del PlayerModel, detección de cambios y resumen privado."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from musst.learning.extract import WEAK, Decision, extract_decisions
from musst.learning.player_model import (
    PRIORS,
    PlayerModel,
    js_divergence,
)

RECENT_DECAY = 0.6
"""Factor de olvido del modelo reciente por partida (memoria de sesión)."""
LONG_DECAY = 0.98
"""Factor de olvido del modelo largo por partida."""
DRIFT_THRESHOLD = 0.03
"""Divergencia JS (bits) a partir de la cual se sospecha un cambio de estrategia."""
DRIFT_MIN_TRIALS = 6.0
DRIFT_CONFIDENCE_FACTOR = 0.5
DRIFT_METRICS = ("aggression", "bluff_frequency", "acceptance_rate")


def apply_decisions(model: PlayerModel, decisions: Iterable[Decision]) -> None:
    """Convierte decisiones observadas en actualizaciones de tasas contextuales."""
    for d in decisions:
        lance, ctx = d.lance, d.score_ctx
        if d.kind in ("mus", "cut"):
            model.record("mus_rate", d.kind == "mus", "mus", ctx)
            continue
        is_bet = d.kind in ("bet", "raise", "ordago")
        if not d.responding:
            model.record("aggression", is_bet, lance, ctx)
            model.record("ordago_rate", d.kind == "ordago", lance, ctx)
        else:
            model.record("acceptance_rate", d.kind == "accept", lance, ctx)
            model.record("rejection_rate", d.kind == "reject", lance, ctx)
            model.record("raise_rate", d.kind in ("raise", "ordago"), lance, ctx)
            model.record("ordago_rate", d.kind == "ordago", lance, ctx)
        if d.strength is None:
            continue
        if is_bet:
            model.record("bluff_frequency", d.strength < WEAK, lance, ctx)
        if d.kind == "accept":
            model.record("risk_tolerance", d.strength < 0.5, lance, ctx)


@dataclass
class DriftReport:
    metric: str
    long_value: float
    recent_value: float
    divergence: float


@dataclass
class LearningUpdate:
    """Resultado de aprender de una partida para un jugador."""

    player_id: str
    decisions: int
    drift: list[DriftReport] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)


def detect_drift(long: PlayerModel, recent: PlayerModel) -> list[DriftReport]:
    reports = []
    for metric in DRIFT_METRICS:
        r = recent.estimate(metric)
        if r.n < DRIFT_MIN_TRIALS:
            continue
        lv = long.estimate(metric).value
        div = js_divergence(lv, r.value)
        if div > DRIFT_THRESHOLD:
            reports.append(DriftReport(metric, lv, r.value, div))
    return reports


def summarize(decisions: Sequence[Decision], model: PlayerModel) -> list[str]:
    """Resumen privado del bot sobre un jugador (sin cartas privadas no reveladas)."""
    lines: list[str] = []
    responses = [d for d in decisions if d.responding and d.kind in ("accept", "reject")]
    if responses:
        accepted = sum(1 for d in responses if d.kind == "accept")
        lines.append(f"Aceptó {accepted} de {len(responses)} envites.")
    bets = [d for d in decisions if d.kind in ("bet", "raise", "ordago") and d.strength is not None]
    if bets:
        by_lance: dict[str, list[Decision]] = {}
        for d in bets:
            by_lance.setdefault(d.lance, []).append(d)
        for lance, items in by_lance.items():
            bluffs = sum(1 for d in items if d.strength is not None and d.strength < WEAK)
            if len(items) >= 2 and bluffs / len(items) >= 0.5:
                lines.append(
                    f"Mostró tendencia a farolear en {lance} ({bluffs}/{len(items)} envites con mano débil)."
                )
    behind = model.estimate("aggression", score="behind")
    overall = model.estimate("aggression")
    if behind.n >= 4 and behind.value - overall.value > 0.1:
        lines.append(
            f"Aumenta su agresividad cuando va por detrás ({behind.value:.0%} frente a {overall.value:.0%})."
        )
    return lines


class ModelStore(Protocol):
    def load(self, player_id: str) -> PlayerModel | None: ...
    def save(self, model: PlayerModel) -> None: ...


class MemoryStore:
    """Almacén en memoria (por defecto en bots y tests)."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def load(self, player_id: str) -> PlayerModel | None:
        data = self._data.get(player_id)
        return PlayerModel.from_dict(data) if data else None

    def save(self, model: PlayerModel) -> None:
        self._data[model.player_id] = model.to_dict()


class JsonFileStore:
    """Almacén en un fichero JSON (memoria a largo plazo sin base de datos)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        data: dict[str, Any] = json.loads(self.path.read_text())
        return data

    def load(self, player_id: str) -> PlayerModel | None:
        data = self._read().get(player_id)
        return PlayerModel.from_dict(data) if data else None

    def save(self, model: PlayerModel) -> None:
        data = self._read()
        data[model.player_id] = model.to_dict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data))


class Learner:
    """Mantiene memoria larga (``store``) y de sesión (``recent``) por jugador."""

    def __init__(self, store: ModelStore | None = None) -> None:
        self.store: ModelStore = store or MemoryStore()
        self.recent: dict[str, PlayerModel] = {}

    def long_model(self, player_id: str) -> PlayerModel:
        return self.store.load(player_id) or PlayerModel(player_id)

    def recent_model(self, player_id: str) -> PlayerModel:
        return self.recent.setdefault(player_id, PlayerModel(player_id))

    def learn_game(
        self,
        history: Sequence[dict[str, Any]],
        seat_players: dict[int, str],
        target: int = 40,
    ) -> list[LearningUpdate]:
        decisions = extract_decisions(history, target)
        updates = []
        for seat, player_id in seat_players.items():
            mine = [d for d in decisions if d.seat == seat]
            long = self.long_model(player_id)
            recent = self.recent_model(player_id)
            long.decay(LONG_DECAY)
            recent.decay(RECENT_DECAY)
            apply_decisions(long, mine)
            apply_decisions(recent, mine)
            long.games += 1
            recent.games += 1
            drift = detect_drift(long, recent)
            if drift:
                long.scale_confidence(DRIFT_CONFIDENCE_FACTOR)
            self.store.save(long)
            update = LearningUpdate(player_id, len(mine), drift, summarize(mine, long))
            for d in drift:
                update.summary.append(
                    f"Posible cambio de estrategia en {d.metric}: "
                    f"{d.long_value:.0%} histórico → {d.recent_value:.0%} reciente. "
                    "Se reduce la confianza del modelo."
                )
            updates.append(update)
        return updates

    def blended(
        self, player_id: str, metric: str, lance: str = "*", score: str = "*"
    ) -> tuple[float, float]:
        """Combina memoria larga y reciente. Devuelve (valor, confianza)."""
        long = self.long_model(player_id).estimate(metric, lance, score)
        recent = self.recent_model(player_id).estimate(metric, lance, score)
        w_recent = recent.confidence * 0.5
        value = (1 - w_recent) * long.value + w_recent * recent.value
        confidence = max(long.confidence, recent.confidence)
        if long.n == 0 and recent.n == 0:
            return PRIORS[metric], 0.0
        return value, confidence
