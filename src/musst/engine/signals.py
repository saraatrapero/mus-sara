"""SignalSystem: señas oficiales de la FEM (Cap. VIII). Preparado y **desactivado en v1**.

Una seña solo puede transmitir la jugada propia y real (FEM VIII.4), por eso se valida
contra las cartas del emisor. El motor aún no acepta ``SignalAction``: activar las señas
exige validar con el profesor el modelo de información (ver docs/design/11).
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from musst.engine import evaluation as ev
from musst.engine.cards import Card


class Signal(str, Enum):
    DOS_REYES = "dos_reyes"
    DOS_ASES = "dos_ases"
    PARES = "pares"
    MEDIAS_REYES = "medias_reyes"
    MEDIAS_ASES = "medias_ases"
    MEDIAS = "medias"
    DUPLES = "duples"
    JUEGO = "juego"
    TREINTA_Y_UNA = "treinta_y_una"
    TREINTA = "treinta"
    VEINTINUEVE = "veintinueve"
    CIEGO = "ciego"
    CORTAR_MUS = "cortar_mus"
    ENVIDAR_MAS = "envidar_mas"


SIGNAL_GESTURES: dict[Signal, str] = {
    Signal.DOS_REYES: "Morderse el labio inferior",
    Signal.DOS_ASES: "Sacar la lengua de frente",
    Signal.PARES: "Girar la cabeza a un lado",
    Signal.MEDIAS_REYES: "Mover los labios cerrados hacia un lado",
    Signal.MEDIAS_ASES: "Sacar la lengua hacia un lado",
    Signal.MEDIAS: "Mover los labios cerrados hacia un lado",
    Signal.DUPLES: "Levantar las cejas",
    Signal.JUEGO: "Sacar los labios cerrados hacia afuera",
    Signal.TREINTA_Y_UNA: "Guiñar un ojo",
    Signal.TREINTA: "Alzar los dos hombros",
    Signal.VEINTINUEVE: "Alzar un hombro",
    Signal.CIEGO: "Cerrar los dos ojos",
    Signal.CORTAR_MUS: "Inclinar la cabeza hacia un lado",
    Signal.ENVIDAR_MAS: "Levantar la cabeza",
}
"""Gestos oficiales (FEM VIII.2)."""


def truthful_signals(hand: Sequence[Card], eight_kings: bool = True) -> set[Signal]:
    """Señas de *jugada* que la mano permite pasar honestamente (FEM VIII.4, VIII.6)."""
    result: set[Signal] = set()
    p = ev.pairs(hand, eight_kings)
    if p.kind is ev.PairsKind.DUPLES:
        result.add(Signal.DUPLES)
    elif p.kind is ev.PairsKind.MEDIAS:
        rank = p.ranks[0]
        result.add(
            Signal.MEDIAS_REYES
            if rank == 12
            else Signal.MEDIAS_ASES
            if rank == 1
            else Signal.MEDIAS
        )
    elif p.kind is ev.PairsKind.PAR:
        rank = p.ranks[0]
        result.add(
            Signal.DOS_REYES if rank == 12 else Signal.DOS_ASES if rank == 1 else Signal.PARES
        )
    total = ev.total_points(hand, eight_kings)
    if total == 31:
        result.add(Signal.TREINTA_Y_UNA)
    elif total > 31:
        result.add(Signal.JUEGO)
    elif total == 30:
        result.add(Signal.TREINTA)
    elif total == 29:
        result.add(Signal.VEINTINUEVE)
    if not result:
        result.add(Signal.CIEGO)
    return result
