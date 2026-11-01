"""Acciones que un jugador puede elegir en su turno.

Todas son dataclasses inmutables y comparables: el motor comprueba la legalidad de una acción
viendo si está en la lista de :func:`musst.compat.musarena.engine.legal_actions`. Un bot solo tiene que devolver
uno de los elementos de esa lista.
"""

from __future__ import annotations

from dataclasses import dataclass

from musst.compat.musarena.cards import Carta

#: Apuesta por defecto de "Envido" y límites de las apuestas con cantidad.
ENVIDO_POR_DEFECTO = 2
ENVIDO_MIN = 3
ENVIDO_MAX = 40
REENVIDO_MIN = 2
REENVIDO_MAX = 40
#: Máximo del total de una apuesta (envite más reenvidos).
APUESTA_MAX = 40


class IllegalActionError(Exception):
    """Se intentó aplicar una acción que no es legal en el estado actual."""


@dataclass(frozen=True)
class Action:
    """Clase base de todas las acciones."""


@dataclass(frozen=True)
class Mus(Action):
    """Pedir mus: descartarse si los cuatro lo piden."""

    def __str__(self) -> str:
        return "Mus"


@dataclass(frozen=True)
class NoHayMus(Action):
    """Cortar el mus: empiezan los lances."""

    def __str__(self) -> str:
        return "No hay mus"


@dataclass(frozen=True)
class Descarte(Action):
    """Descartar de 1 a 4 cartas propias y robar otras tantas."""

    cartas: frozenset[Carta]

    def __str__(self) -> str:
        nombres = ", ".join(sorted(str(c) for c in self.cartas))
        return f"Descartar {nombres}"


@dataclass(frozen=True)
class Paso(Action):
    """No apostar cuando nadie ha envidado."""

    def __str__(self) -> str:
        return "Paso"


@dataclass(frozen=True)
class Envido(Action):
    """Primera apuesta del lance: ``Envido`` (2 tantos) o ``Envido N`` (N entre 3 y 40)."""

    tantos: int = ENVIDO_POR_DEFECTO

    def __str__(self) -> str:
        if self.tantos == ENVIDO_POR_DEFECTO:
            return "Envido"
        return f"Envido {self.tantos}"


@dataclass(frozen=True)
class Reenvido(Action):
    """Subir la apuesta del rival ``tantos`` más (al menos 2, sin que el total pase de 40)."""

    tantos: int

    def __str__(self) -> str:
        return f"Reenvido {self.tantos}"


@dataclass(frozen=True)
class Ordago(Action):
    """Apostar la vaca entera."""

    def __str__(self) -> str:
        return "Órdago"


@dataclass(frozen=True)
class Quiero(Action):
    """Aceptar la apuesta del rival."""

    def __str__(self) -> str:
        return "Quiero"


@dataclass(frozen=True)
class NoQuiero(Action):
    """Rechazar la apuesta del rival."""

    def __str__(self) -> str:
        return "No quiero"
