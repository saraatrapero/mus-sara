"""Baraja española de 40 cartas (estilo Fournier) jugando a 8 reyes."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum


class Palo(Enum):
    """Los cuatro palos de la baraja española."""

    OROS = "oros"
    COPAS = "copas"
    ESPADAS = "espadas"
    BASTOS = "bastos"


#: Números de carta de cada palo (no hay 8 ni 9).
NUMEROS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 10, 11, 12)

_NOMBRES: dict[int, str] = {
    1: "As",
    2: "Dos",
    3: "Tres",
    4: "Cuatro",
    5: "Cinco",
    6: "Seis",
    7: "Siete",
    10: "Sota",
    11: "Caballo",
    12: "Rey",
}


@dataclass(frozen=True)
class Carta:
    """Una carta: número (1-7, 10, 11, 12) y palo. Es inmutable y se puede usar en conjuntos."""

    numero: int
    palo: Palo

    def __post_init__(self) -> None:
        if self.numero not in NUMEROS:
            raise ValueError(f"Número de carta no válido: {self.numero}")

    @property
    def rango(self) -> int:
        """Valor para grande, chica y pares a 8 reyes: el 3 es rey (12) y el 2 es as (1)."""
        if self.numero == 3:
            return 12
        if self.numero == 2:
            return 1
        return self.numero

    @property
    def valor_juego(self) -> int:
        """Valor para el juego y el punto: figuras y treses 10, doses 1, el resto su número."""
        if self.numero >= 10 or self.numero == 3:
            return 10
        if self.numero == 2:
            return 1
        return self.numero

    @property
    def nombre(self) -> str:
        """Nombre de la carta sin el palo, por ejemplo "Rey"."""
        return _NOMBRES[self.numero]

    def __str__(self) -> str:
        return f"{self.nombre} de {self.palo.value}"


_ORDEN_PALOS = {palo: i for i, palo in enumerate(Palo)}


def ordenar_cartas(cartas: list[Carta]) -> list[Carta]:
    """Ordena de mayor a menor según la grande.

    Con el mismo valor va primero el número mayor: el 12 antes que el 3 (ambos reyes) y el 2 antes
    que el as. Si coincide también el número, se ordena por palo para que el orden sea fijo.
    """
    return sorted(cartas, key=lambda c: (-c.rango, -c.numero, _ORDEN_PALOS[c.palo]))


def todas_las_cartas() -> list[Carta]:
    """Las 40 cartas de la baraja, en orden fijo (palo y número)."""
    return [Carta(numero, palo) for palo in Palo for numero in NUMEROS]


class Baraja:
    """Mazo del que se roba, más la pila de descartes.

    La aleatoriedad llega desde fuera (``rng``) para que las partidas sean reproducibles.
    Si el mazo se acaba al robar, se barajan los descartes (nunca las cartas en mano) y se sigue.
    """

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self.mazo: list[Carta] = todas_las_cartas()
        self.descartes: list[Carta] = []
        self._rng.shuffle(self.mazo)

    def robar(self, n: int) -> list[Carta]:
        """Roba ``n`` cartas del mazo, rebarajando los descartes si hace falta."""
        robadas: list[Carta] = []
        for _ in range(n):
            if not self.mazo:
                if not self.descartes:
                    raise RuntimeError("No quedan cartas en el mazo ni en los descartes")
                self.mazo = self.descartes
                self.descartes = []
                self._rng.shuffle(self.mazo)
            robadas.append(self.mazo.pop())
        return robadas

    def descartar(self, cartas: list[Carta]) -> None:
        """Añade cartas a la pila de descartes."""
        self.descartes.extend(cartas)

    def copiar(self, rng: random.Random) -> Baraja:
        """Copia independiente de la baraja que usa el generador ``rng``."""
        nueva = Baraja.__new__(Baraja)
        nueva._rng = rng
        nueva.mazo = list(self.mazo)
        nueva.descartes = list(self.descartes)
        return nueva
