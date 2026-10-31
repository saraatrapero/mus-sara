"""Experimentos reproducibles del motor probabilístico (docs/probabilidad.md).

Parte 1 — Partidas. Cada variante juega en pareja contra dos bots de nivel *medio* (rival de
referencia común). Cada semilla se juega **dos veces cambiando a las parejas de asiento**
(mus duplicado: las dos parejas reciben las mismas cartas), así que las variantes se comparan
de forma **pareada** sobre los mismos repartos.

    A_medio  bot actual, nivel medio (control: debe salir ≈ 50 %)
    A_pro    bot actual, nivel profesional
    B        marginales exactas + independencia (mat_exacto)
    C        Monte Carlo exacto + Bayes (mat_bayes)
    D        Monte Carlo exacto sin Bayes (mat_mc)
    E        Monte Carlo + utilidad esperada de P(ganar la partida) (mat_utilidad)
    F        completo multiagente (matematico)

Se mide: % de victorias (IC de Wilson), diferencia de tantos por partida (IC t), comparación
pareada con A_pro (prueba t pareada sobre victorias por semilla, con corrección de Holm),
calibración de P(ganar el lance) en cada decisión frente al resultado real (Brier y log-loss,
con error estándar por conglomerados de partida) y tiempo por decisión.

Parte 2 — Error de estimación. En situaciones reales de partida (con declaraciones), compara
cada estimador de P(ganar el lance) con una referencia de alta precisión (Monte Carlo exacto,
20 000 repartos): sesgo, RMSE y cobertura del IC95.

Uso::

    python -m experiments.probability partidas 200      # 200 semillas → 400 partidas/variante
    python -m experiments.probability estimacion 300    # 300 situaciones de partida

Resultados (JSON) en ``experiments/results/``.
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
import time
from multiprocessing import Pool
from typing import Any

from experiments.common import RESULTS, wilson
from musst.agents.orchestrator import AgentBot, MediumBot
from musst.bots.api import Bot, GameEndInfo, GameStartInfo, Observation
from musst.bots.toolkit import estimate_lance_win
from musst.engine.actions import Action
from musst.engine.events import EventKind
from musst.engine.game import MusGame
from musst.engine.observation import build_observation
from musst.probability.estimators import Method, weighted_proportion
from musst.probability.lances import analytic_win_probability, lance_outcome
from musst.probability.sampler import WorldSampler, constraints_from, sample_worlds
from musst.runtime.runner import play_game

FIRST_SEED = 500_000
VARIANTS = {
    "A_medio": "medio",
    "A_pro": "profesional",
    "B": "mat_exacto",
    "C": "mat_bayes",
    "D": "mat_mc",
    "E": "mat_utilidad",
    "F": "matematico",
}
LANCES = ("grande", "chica", "pares", "juego", "punto")


class Recorder(Bot):
    """Envuelve un bot y apunta, en cada decisión de un lance, la P(ganar el lance) que usó."""

    def __init__(self, inner: AgentBot) -> None:
        self.inner = inner
        self.name = inner.name
        self.predictions: list[tuple[int, str, float]] = []

    def on_game_start(self, info: GameStartInfo) -> None:
        self.inner.on_game_start(info)

    def decide(self, observation: Observation) -> Action:
        action = self.inner.decide(observation)
        d = self.inner.last_decision
        if observation.phase in LANCES and d is not None and "p_win" in d.evidence:
            self.predictions.append((observation.round_no, observation.phase, d.evidence["p_win"]))
        return action

    def signal(self, observation: Observation) -> str | None:
        return self.inner.signal(observation)

    def on_game_end(self, info: GameEndInfo) -> None:
        self.inner.on_game_end(info)


def one_game(args: tuple[str, int, int]) -> dict[str, Any]:
    variant, seed, side = args
    level = VARIANTS[variant]
    base = seed * 8
    ours = [Recorder(AgentBot(level, base + i)) for i in (0, 2)]
    refs = [MediumBot(base + i) for i in (1, 3)]
    bots: list[Bot] = (
        [ours[0], refs[0], ours[1], refs[1]] if side == 0 else [refs[0], ours[0], refs[1], ours[1]]
    )
    start = time.perf_counter()
    match = play_game(bots, seed=seed, time_limit_s=60)
    elapsed = time.perf_counter() - start
    team = side
    resolved: dict[tuple[int, str], int | None] = {}
    for e in match.events:
        if e.kind is EventKind.LANCE_RESOLVED:
            resolved[(e.round_no, e.payload["lance"])] = e.payload.get("winner_seat")
    brier, logloss = [], []
    for bot in ours:
        for round_no, lance, p in bot.predictions:
            if (round_no, lance) not in resolved:
                continue  # la partida acabó antes de resolver el lance
            w = resolved[(round_no, lance)]
            y = 1.0 if w is not None and w % 2 == team else 0.0
            q = min(1 - 1e-6, max(1e-6, p))
            brier.append((p - y) ** 2)
            logloss.append(-(y * math.log(q) + (1 - y) * math.log(1 - q)))
    seats = (0, 2) if side == 0 else (1, 3)
    times = [t for s in seats for t in match.decision_times.get(s, [])]
    score = match.result.score
    return {
        "variant": variant,
        "seed": seed,
        "side": side,
        "win": int(match.result.winner == team),
        "diff": score[team] - score[1 - team],
        "errors": len(match.errors),
        "brier": brier,
        "logloss": logloss,
        "times": times,
        "seconds": elapsed,
    }


def mean_ci(values: list[float]) -> tuple[float, float, float]:
    m = statistics.fmean(values)
    se = statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return m, m - 1.96 * se, m + 1.96 * se


def normal_p_two_sided(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def cluster_mean(per_game: list[list[float]]) -> tuple[float, float]:
    """Media de todas las predicciones y su SE por conglomerados (partidas)."""
    games = [g for g in per_game if g]
    n = sum(len(g) for g in games)
    if not n:
        return float("nan"), float("nan")
    mean = sum(sum(g) for g in games) / n
    k = len(games)
    resid = [sum(x - mean for x in g) for g in games]
    se = math.sqrt(k / (k - 1) * sum(r * r for r in resid)) / n if k > 1 else float("nan")
    return mean, se


def games_experiment(n_seeds: int) -> dict[str, Any]:
    tasks = [(v, FIRST_SEED + s, side) for v in VARIANTS for s in range(n_seeds) for side in (0, 1)]
    with Pool() as pool:
        rows = pool.map(one_game, tasks, chunksize=2)
    by_variant: dict[str, list[dict[str, Any]]] = {v: [] for v in VARIANTS}
    for r in rows:
        by_variant[r["variant"]].append(r)
    summary: dict[str, Any] = {}
    per_seed: dict[str, dict[int, int]] = {}
    for v, rs in by_variant.items():
        n = len(rs)
        wins = sum(r["win"] for r in rs)
        low, high = wilson(wins, n)
        dmean, dlow, dhigh = mean_ci([r["diff"] for r in rs])
        brier, brier_se = cluster_mean([r["brier"] for r in rs])
        logloss, logloss_se = cluster_mean([r["logloss"] for r in rs])
        times = sorted(t for r in rs for t in r["times"])
        per_seed[v] = {}
        for r in rs:
            per_seed[v][r["seed"]] = per_seed[v].get(r["seed"], 0) + r["win"]
        summary[v] = {
            "nivel": VARIANTS[v],
            "partidas": n,
            "victorias": wins,
            "pct_victorias": wins / n,
            "ic95_victorias": [low, high],
            "dif_tantos_media": dmean,
            "ic95_dif_tantos": [dlow, dhigh],
            "brier": brier,
            "brier_se": brier_se,
            "logloss": logloss,
            "logloss_se": logloss_se,
            "predicciones": sum(len(r["brier"]) for r in rs),
            "ms_decision_media": 1000 * statistics.fmean(times) if times else 0.0,
            "ms_decision_p95": 1000 * times[int(0.95 * (len(times) - 1))] if times else 0.0,
            "segundos_por_partida": statistics.fmean(r["seconds"] for r in rs),
            "errores_de_bot": sum(r["errors"] for r in rs),
        }
    # Comparaciones pareadas con A_pro (mismas semillas): t pareada sobre victorias por semilla.
    tests = []
    base = per_seed["A_pro"]
    for v in VARIANTS:
        if v == "A_pro":
            continue
        d = [per_seed[v][s] - base[s] for s in base]
        m = statistics.fmean(d)
        se = statistics.stdev(d) / math.sqrt(len(d))
        z = m / se if se else 0.0
        tests.append(
            {
                "variante": v,
                "dif_victorias_por_partida": m / 2,
                "ic95": [(m - 1.96 * se) / 2, (m + 1.96 * se) / 2],
                "p_valor": normal_p_two_sided(z),
            }
        )
    # Corrección de Holm-Bonferroni.
    order = sorted(range(len(tests)), key=lambda i: tests[i]["p_valor"])
    running = 0.0
    for rank, i in enumerate(order):
        adj = min(1.0, (len(tests) - rank) * tests[i]["p_valor"])
        running = max(running, adj)
        tests[i]["p_holm"] = running
        tests[i]["significativo_5pct"] = running < 0.05
    return {
        "semillas": n_seeds,
        "primera_semilla": FIRST_SEED,
        "resumen": summary,
        "frente_a_A_pro": tests,
    }


# ------------------------------------------------------------------ parte 2
def situations(n: int) -> list[Observation]:
    """Decisiones reales en lances (asiento al que le toca) de partidas entre bots medios."""
    rng = random.Random(77)
    out: list[Observation] = []
    seed = 900_000
    while len(out) < n:
        game = MusGame(seed=seed)
        bots = [MediumBot(seed + i) for i in range(4)]
        steps = 0
        while not game.finished and steps < 2000:
            steps += 1
            seat = game.turn
            obs = build_observation(game, seat)
            if obs.phase in LANCES and rng.random() < 0.05 and len(out) < n:
                out.append(obs)
            game.apply(seat, bots[seat].decide(obs))
        seed += 1
    return out


def one_situation(args: tuple[int, Observation]) -> dict[str, Any]:
    i, obs = args
    lance = obs.phase
    sampler = WorldSampler.from_observation(obs)

    def win_values(worlds: list[dict[int, Any]]) -> list[float]:
        return [
            1.0 if lance_outcome(lance, w, obs.mano, obs.team)[0] == "gana" else 0.0 for w in worlds
        ]

    worlds, weights = sample_worlds(sampler, random.Random(10_000 + i), 20_000)
    ref = weighted_proportion(win_values(worlds), weights, Method.MONTE_CARLO)
    worlds, weights = sample_worlds(sampler, random.Random(20_000 + i), 200)
    new = weighted_proportion(win_values(worlds), weights, Method.MONTE_CARLO)
    old = estimate_lance_win(obs, lance, random.Random(30_000 + i), samples=200)
    analytic = analytic_win_probability(
        obs.hand, obs.seat, obs.mano, lance, sampler.pool, constraints_from(obs)
    )
    low, high = new.interval
    constrained = any(not c.empty for c in sampler.constraints.values())
    return {
        "lance": lance,
        "restricciones": constrained,
        "ref": ref.value,
        "ref_se": ref.se,
        "mc_nuevo": new.value,
        "mc_nuevo_cubre": low <= ref.value <= high,
        "mc_antiguo": old.p_win,
        "analitica": analytic.value,
    }


def estimation_experiment(n: int) -> dict[str, Any]:
    obs = situations(n)
    with Pool() as pool:
        rows = pool.map(one_situation, list(enumerate(obs)))

    def stats(key: str, subset: list[dict[str, Any]]) -> dict[str, float]:
        errs = [r[key] - r["ref"] for r in subset]
        return {
            "sesgo": statistics.fmean(errs),
            "sesgo_se": statistics.stdev(errs) / math.sqrt(len(errs)) if len(errs) > 1 else 0.0,
            "rmse": math.sqrt(statistics.fmean(e * e for e in errs)),
            "n": len(errs),
        }

    out: dict[str, Any] = {"situaciones": n, "referencia": "Monte Carlo exacto, 20 000 repartos"}
    for name, subset in (
        ("todas", rows),
        ("con_restricciones", [r for r in rows if r["restricciones"]]),
        ("sin_restricciones", [r for r in rows if not r["restricciones"]]),
    ):
        if not subset:
            continue
        out[name] = {
            "mc_nuevo_200": stats("mc_nuevo", subset),
            "mc_antiguo_200": stats("mc_antiguo", subset),
            "analitica": stats("analitica", subset),
            "cobertura_ic95_mc_nuevo": statistics.fmean(
                1.0 if r["mc_nuevo_cubre"] else 0.0 for r in subset
            ),
        }
    out["max_se_referencia"] = max(r["ref_se"] for r in rows)
    return out


def main() -> None:
    what = sys.argv[1] if len(sys.argv) > 1 else "partidas"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    RESULTS.mkdir(parents=True, exist_ok=True)
    start = time.time()
    result = games_experiment(n) if what == "partidas" else estimation_experiment(n)
    result["duracion_s"] = round(time.time() - start, 1)
    path = RESULTS / f"probabilidad_{what}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
