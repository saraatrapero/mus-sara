"""Análisis post-partida: estadísticas, momentos clave y simulación contrafactual.

Todo se calcula a partir del historial **público** de una partida terminada (incluye las manos
reveladas al final de cada jugada, FEM VII.9). Nunca se usa durante la partida.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from musst.bots.toolkit import lance_winner
from musst.engine.cards import Card
from musst.learning.extract import WEAK, extract_decisions

LANCES = ("grande", "chica", "pares", "juego", "punto")


def seat_statistics(
    history: Sequence[dict[str, Any]], seat: int, target: int = 40
) -> dict[str, Any]:
    """Estadísticas descriptivas de un asiento en una partida."""
    decisions = [d for d in extract_decisions(history, target) if d.seat == seat]
    kinds = Counter(d.kind for d in decisions)
    bets = [d for d in decisions if d.kind in ("bet", "raise", "ordago")]
    responses = [d for d in decisions if d.responding and d.kind in ("accept", "reject")]
    known = [d.strength for d in bets if d.strength is not None]
    by_lance: dict[str, dict[str, int]] = {}
    for lance in LANCES:
        ds = [d for d in decisions if d.lance == lance]
        by_lance[lance] = {
            "envites": sum(1 for d in ds if d.kind in ("bet", "raise", "ordago")),
            "aceptados": sum(1 for d in ds if d.kind == "accept"),
            "rechazados": sum(1 for d in ds if d.kind == "reject"),
            "pasos": sum(1 for d in ds if d.kind == "pass"),
        }
    team = seat % 2
    points_won = sum(
        e["payload"]["points"]
        for e in history
        if e["kind"] == "PointsAwarded" and e["payload"]["team"] == team
    )
    return {
        "decisiones": len(decisions),
        "envites": kinds["bet"] + kinds["raise"],
        "ordagos": kinds["ordago"],
        "aceptaciones": kinds["accept"],
        "rechazos": kinds["reject"],
        "mus": kinds["mus"],
        "cortes": kinds["cut"],
        "tasa_aceptacion": (kinds["accept"] / len(responses)) if responses else None,
        "frecuencia_farol": (sum(1 for s in known if s < WEAK) / len(known)) if known else None,
        "tantos_pareja": points_won,
        "por_lance": by_lance,
    }


@dataclass(frozen=True)
class KeyMoment:
    round_no: int
    lance: str
    description: str
    points: int
    team: int | None


def key_moments(history: Sequence[dict[str, Any]], limit: int = 5) -> list[KeyMoment]:
    """Decisiones con más tantos en juego (órdagos, envites grandes aceptados o rechazados)."""
    moments: list[KeyMoment] = []
    stake: dict[tuple[int, str], int] = {}
    for e in history:
        kind = e["kind"]
        p = e["payload"]
        key = (e["round"], p.get("lance", ""))
        if kind == "BetPlaced":
            stake[key] = p["amount"]
        elif kind == "BetRaised":
            stake[key] = p["total"]
        elif kind == "OrdagoAccepted":
            moments.append(
                KeyMoment(
                    e["round"],
                    p["lance"],
                    f"Órdago a {p['lance']} aceptado por el asiento {e['actor']}",
                    40,
                    None,
                )
            )
        elif kind == "BetAccepted":
            moments.append(
                KeyMoment(
                    e["round"],
                    p["lance"],
                    f"Envite de {p['amount']} a {p['lance']} aceptado",
                    p["amount"],
                    None,
                )
            )
        elif kind == "PointsAwarded" and p["concept"] == "envite_no_querido":
            moments.append(
                KeyMoment(
                    e["round"],
                    p["lance"],
                    f"Reenvite no querido en {p['lance']}: {p['points']} tantos",
                    p["points"],
                    p["team"],
                )
            )
        elif kind == "GameFinished":
            moments.append(
                KeyMoment(
                    e["round"],
                    "",
                    f"Fin: gana la pareja {p['winner']} ({p['reason']})",
                    40,
                    p["winner"],
                )
            )
    moments.sort(key=lambda m: m.points, reverse=True)
    return moments[:limit]


def _round_context(
    history: Sequence[dict[str, Any]], round_no: int
) -> tuple[int, dict[int, tuple[Card, ...]]] | None:
    mano = None
    hands = None
    for e in history:
        if e["round"] != round_no:
            continue
        if e["kind"] == "DealerAssigned":
            mano = e["payload"]["mano"]
        if e["kind"] == "HandsRevealed":
            hands = {
                int(s): tuple(Card.parse(c) for c in cs) for s, cs in e["payload"]["hands"].items()
            }
    if mano is None or hands is None:
        return None
    return mano, hands


def what_if(
    history: Sequence[dict[str, Any]],
    round_no: int,
    lance: str,
    seat: int,
    stake: int,
    previous: int = 1,
) -> dict[str, Any] | None:
    """¿Qué habría pasado si ``seat`` hubiera aceptado o rechazado un envite de ``stake``?

    Solo para partidas terminadas: usa las manos reveladas de esa jugada.
    """
    ctx = _round_context(history, round_no)
    if ctx is None:
        return None
    mano, hands = ctx
    winner_seat = lance_winner(lance, dict(hands), mano)
    if winner_seat is None:
        return None
    my_team = seat % 2
    won = winner_seat % 2 == my_team
    return {
        "lance": lance,
        "ganador_del_lance": winner_seat,
        "si_aceptas": stake if won else -stake,
        "si_rechazas": -previous,
        "mejor_opcion": "aceptar" if (stake if won else -stake) > -previous else "rechazar",
    }


ORDAGO_POINTS = 40  # un órdago decide la partida: se cuenta como el juego entero


def decision_counterfactuals(
    history: Sequence[dict[str, Any]], seat: int, limit: int = 5
) -> list[dict[str, Any]]:
    """Contrafactual de cada envite que ``seat`` aceptó o rechazó (solo partidas terminadas).

    Compara lo que pasó con la alternativa usando las manos reveladas. Cuenta solo la apuesta
    del lance (no los tantos de pares o juego, que se cobran igual en ambos casos). Un órdago
    aceptado vale la partida entera (``ORDAGO_POINTS``).
    """
    stake: dict[tuple[int, str], tuple[int, int]] = {}  # (jugada, lance) -> (total, anterior)
    out: list[dict[str, Any]] = []
    for e in history:
        p = e["payload"]
        key = (e["round"], p.get("lance", ""))
        if e["kind"] == "BetPlaced":
            stake[key] = (p["amount"], 1)
        elif e["kind"] == "BetRaised":
            stake[key] = (p["total"], stake.get(key, (1, 1))[0])
        elif e["kind"] == "OrdagoDeclared":
            stake[key] = (ORDAGO_POINTS, stake.get(key, (1, 1))[0])
        elif e["kind"] in ("BetAccepted", "BetRejected", "OrdagoAccepted") and e["actor"] == seat:
            if e["kind"] == "BetRejected" and not p.get("final", True):
                continue
            total, previous = stake.get(key, (p.get("amount", 2), 1))
            result = what_if(history, e["round"], p["lance"], seat, total, previous)
            if result is None:
                continue
            chose = "rechazar" if e["kind"] == "BetRejected" else "aceptar"
            got = result["si_aceptas"] if chose == "aceptar" else result["si_rechazas"]
            alt = result["si_rechazas"] if chose == "aceptar" else result["si_aceptas"]
            out.append(
                {
                    "jugada": e["round"],
                    "lance": p["lance"],
                    "envite": total,
                    "ordago": total == ORDAGO_POINTS,
                    "elegiste": chose,
                    "tantos": got,
                    "alternativa": alt,
                    "acierto": got >= alt,
                }
            )
    out.sort(key=lambda d: abs(d["tantos"] - d["alternativa"]), reverse=True)
    return out[:limit]
