"""Torneo automático entre bots (Req 4.1).

* Unidad competitiva: la **pareja**. Cada participante ocupa los dos asientos de su pareja con
  dos instancias independientes (cada una ve solo sus cartas).
* Liga todos contra todos con **mus duplicado**: cada seed se juega dos veces cambiando a las
  parejas de asiento, para reducir el efecto de la suerte.
* Un bot que falla, se cuelga o juega ilegal pierde esa partida; el torneo sigue.
"""

from __future__ import annotations

import itertools
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from musst.bots.api import Bot
from musst.runtime.runner import play_game


@dataclass(frozen=True)
class Participant:
    name: str
    factory: Callable[[], Bot]
    author: str = ""
    version: str = ""


@dataclass
class Standing:
    name: str
    author: str = ""
    version: str = ""
    games: int = 0
    wins: int = 0
    losses: int = 0
    points_for: int = 0
    points_against: int = 0
    errors: int = 0
    illegal: int = 0
    timeouts: int = 0
    elo: float = 1500.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0

    def wilson(self, z: float = 1.96) -> tuple[float, float]:
        """Intervalo de confianza de Wilson al 95 % para el % de victorias."""
        n = self.games
        if n == 0:
            return (0.0, 0.0)
        p = self.wins / n
        denom = 1 + z**2 / n
        centre = (p + z**2 / (2 * n)) / denom
        half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
        return (max(0.0, centre - half), min(1.0, centre + half))

    def to_dict(self) -> dict[str, Any]:
        low, high = self.wilson()
        data = asdict(self)
        data.update(
            win_rate=round(self.win_rate, 4),
            win_rate_ci=[round(low, 4), round(high, 4)],
            point_diff_per_game=round((self.points_for - self.points_against) / self.games, 2)
            if self.games
            else 0.0,
            elo=round(self.elo, 1),
        )
        return data


@dataclass
class GameRecord:
    team0: str
    team1: str
    seed: int
    winner: str
    score: tuple[int, int]
    reason: str
    errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TournamentResult:
    seed: int
    games_per_pair: int
    standings: list[Standing]
    games: list[GameRecord]
    started_at: float
    duration_s: float

    def ranking(self) -> list[Standing]:
        return sorted(
            self.standings,
            key=lambda s: (s.win_rate, s.points_for - s.points_against, -s.errors),
            reverse=True,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "games_per_pair": self.games_per_pair,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started_at)),
            "duration_s": round(self.duration_s, 1),
            "ranking": [s.to_dict() for s in self.ranking()],
            "games": [asdict(g) for g in self.games],
        }


def _update_elo(a: Standing, b: Standing, score_a: float, k: float = 24.0) -> None:
    expected = 1 / (1 + 10 ** ((b.elo - a.elo) / 400))
    a.elo += k * (score_a - expected)
    b.elo += k * ((1 - score_a) - (1 - expected))


def run_tournament(
    participants: Sequence[Participant],
    games_per_pair: int = 10,
    seed: int = 2026,
    time_limit_s: float = 2.0,
    progress: Callable[[str], None] | None = None,
) -> TournamentResult:
    """Liga todos contra todos. ``games_per_pair`` seeds, cada una jugada en los dos sentidos."""
    start = time.time()
    table = {p.name: Standing(p.name, p.author, p.version) for p in participants}
    records: list[GameRecord] = []
    for pi, (a, b) in enumerate(itertools.combinations(participants, 2)):
        for g in range(games_per_pair):
            game_seed = seed * 1000 + pi * 100 + g
            for first, second in ((a, b), (b, a)):  # mus duplicado
                bots = [first.factory(), second.factory(), first.factory(), second.factory()]
                match = play_game(
                    bots, seed=game_seed, mode="tournament", time_limit_s=time_limit_s
                )
                for bot in bots:
                    close = getattr(bot, "close", None)
                    if callable(close):
                        close()
                res = match.result
                winner = first if res.winner == 0 else second
                loser = second if winner is first else first
                for team, part in ((0, first), (1, second)):
                    st = table[part.name]
                    st.games += 1
                    st.points_for += res.score[team]
                    st.points_against += res.score[1 - team]
                table[winner.name].wins += 1
                table[loser.name].losses += 1
                _update_elo(table[winner.name], table[loser.name], 1.0)
                errors = []
                for err in match.errors:
                    part = first if err.seat % 2 == 0 else second
                    st = table[part.name]
                    st.errors += 1
                    st.illegal += err.kind == "illegal"
                    st.timeouts += err.kind == "timeout"
                    errors.append({"bot": part.name, "kind": err.kind, "detail": err.detail[:200]})
                records.append(
                    GameRecord(
                        first.name,
                        second.name,
                        game_seed,
                        winner.name,
                        res.score,
                        res.reason,
                        errors,
                    )
                )
        if progress:
            progress(f"{a.name} vs {b.name} terminado")
    return TournamentResult(
        seed, games_per_pair, list(table.values()), records, start, time.time() - start
    )
