"""Estima el modelo de decisiones P(acción | mano) por máxima verosimilitud.

Al final de cada jugada se enseñan las cartas (FEM VII.9), así que de cada decisión de un
lance se conoce la mano de quien la tomó. Para cada lance y tipo de decisión se ajusta una
regresión logística sobre la fuerza de la mano s = ``hand_strength(mano, lance)``::

    P(y = 1 | s) = σ(a + b·s)

por Newton-Raphson (máxima verosimilitud con una penalización L2 pequeña). Decisiones:

* ``envida``         — en un lance abierto: envida u órdago (1) frente a paso (0);
* ``ordago_abre``    — en un lance abierto: órdago (1) frente a paso o envite (0);
* ``quiere``         — ante un envite: quiere, sube u órdago (1) frente a no quiero (0);
* ``ordago_responde``— ante un envite: órdago (1) frente al resto (0);
* ``quiere_ordago``  — ante un órdago: lo quiere (1) frente a no (0).

Datos: partidas entre cuatro bots de nivel *medio* (rival de referencia), semillas distintas
de las de los experimentos. Escribe ``src/musst/probability/behaviour_data.py``.

    python scripts/behaviour_fit.py 1000 0
"""

from __future__ import annotations

import math
import sys
from multiprocessing import Pool
from pathlib import Path

from musst.agents.orchestrator import MediumBot
from musst.bots.toolkit import hand_strength
from musst.engine.cards import Card
from musst.engine.events import EventKind
from musst.runtime.runner import play_game

OUT = Path(__file__).resolve().parents[1] / "src" / "musst" / "probability" / "behaviour_data.py"
KINDS = ("envida", "ordago_abre", "quiere", "ordago_responde", "quiere_ordago")
L2 = 1e-3


def samples_of(seed: int) -> list[tuple[str, str, float, int]]:
    """(lance, decisión, fuerza, y) de todas las decisiones de lance de una partida."""
    bots = [MediumBot(seed * 4 + i) for i in range(4)]
    match = play_game(bots, seed=seed)
    by_round: dict[int, list] = {}
    hands: dict[int, dict[int, tuple[Card, ...]]] = {}
    for e in match.events:
        by_round.setdefault(e.round_no, []).append(e)
        if e.kind is EventKind.HANDS_REVEALED:
            hands[e.round_no] = {
                int(s): tuple(Card.parse(c) for c in cards)
                for s, cards in e.payload["hands"].items()
            }
    out: list[tuple[str, str, float, int]] = []
    for round_no, events in by_round.items():
        if round_no not in hands:
            continue
        pending: str | None = None
        for e in events:
            k = e.kind
            if k is EventKind.LANCE_STARTED:
                pending = None
                continue
            if e.actor is None or "lance" not in e.payload:
                continue
            lance = e.payload["lance"]
            s = hand_strength(hands[round_no][e.actor], lance)

            def add(kind: str, y: int, lance: str = lance, s: float = s) -> None:
                out.append((lance, kind, s, y))

            if k is EventKind.PASSED:
                add("envida", 0)
                add("ordago_abre", 0)
            elif k is EventKind.BET_PLACED:
                add("envida", 1)
                add("ordago_abre", 0)
                pending = "bet"
            elif k is EventKind.ORDAGO_DECLARED:
                if pending is None:
                    add("envida", 1)
                    add("ordago_abre", 1)
                else:
                    add("quiere", 1)
                    add("ordago_responde", 1)
                pending = "ordago"
            elif k is EventKind.BET_RAISED:
                add("quiere", 1)
                add("ordago_responde", 0)
                pending = "bet"
            elif k is EventKind.BET_ACCEPTED:
                add("quiere", 1)
                add("ordago_responde", 0)
            elif k is EventKind.BET_REJECTED:
                if pending == "ordago":
                    add("quiere_ordago", 0)
                else:
                    add("quiere", 0)
                    add("ordago_responde", 0)
            elif k is EventKind.ORDAGO_ACCEPTED:
                add("quiere_ordago", 1)
    return out


def fit_logistic(xs: list[float], ys: list[int]) -> tuple[float, float, float]:
    """Máxima verosimilitud de σ(a + b·x) por Newton-Raphson. Devuelve (a, b, log-verosimilitud)."""
    a = b = 0.0
    for _ in range(50):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(xs, ys, strict=True):
            p = 1 / (1 + math.exp(-(a + b * x)))
            r = y - p
            w = p * (1 - p)
            ga += r
            gb += r * x
            haa += w
            hab += w * x
            hbb += w * x * x
        ga -= L2 * a
        gb -= L2 * b
        haa += L2
        hbb += L2
        det = haa * hbb - hab * hab
        if det <= 0:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a + da, b + db
        if abs(da) + abs(db) < 1e-10:
            break
    ll = 0.0
    for x, y in zip(xs, ys, strict=True):
        p = min(1 - 1e-12, max(1e-12, 1 / (1 + math.exp(-(a + b * x)))))
        ll += y * math.log(p) + (1 - y) * math.log(1 - p)
    return a, b, ll


def main(n: int, first_seed: int) -> None:
    with Pool() as pool:
        rows = [r for rs in pool.map(samples_of, range(first_seed, first_seed + n)) for r in rs]
    fits: dict[tuple[str, str], tuple[float, float, int, int]] = {}
    for lance in ("grande", "chica", "pares", "juego", "punto", "*"):
        for kind in KINDS:
            data = [(s, y) for lc, kd, s, y in rows if kd == kind and lance in ("*", lc)]
            pos = sum(y for _, y in data)
            if len(data) < 30 or pos < 5 or pos > len(data) - 5:
                continue  # muy pocos casos: se usa el ajuste conjunto ("*")
            a, b, _ = fit_logistic([s for s, _ in data], [y for _, y in data])
            fits[(lance, kind)] = (round(a, 4), round(b, 4), len(data), pos)
    lines = [
        '"""Modelo de decisiones P(acción | fuerza de la mano) = σ(a + b·s), ajustado por máxima',
        "verosimilitud con ``scripts/behaviour_fit.py``. Generado automáticamente: no editar a mano.",
        "",
        "Claves: (lance o ``*`` para todos, decisión) → (a, b, casos, casos positivos).",
        '"""',
        "",
        f"GAMES = {n}",
        f"FIRST_SEED = {first_seed}",
        'BOTS = "medio"',
        "FITS: dict[tuple[str, str], tuple[float, float, int, int]] = {",
        *(f"    {k!r}: {v}," for k, v in sorted(fits.items())),
        "}",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} decisiones de {n} partidas → {OUT}")
    for k, v in sorted(fits.items()):
        print(k, v)


if __name__ == "__main__":
    main(
        int(sys.argv[1]) if len(sys.argv) > 1 else 1000,
        int(sys.argv[2]) if len(sys.argv) > 2 else 0,
    )
