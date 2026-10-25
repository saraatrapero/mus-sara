"""Naipes de la baraja española de 40 cartas (FEM Cap. II Art. 3).

Modalidad *ocho reyes y ocho ases*: el 3 vale como rey y el 2 como as.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

RANKS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 10, 11, 12)
"""Números de la baraja española de 40 naipes (sin 8 ni 9). 10 = sota, 11 = caballo, 12 = rey."""

RANK_NAMES: dict[int, str] = {
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


class Suit(str, Enum):
    """Palos de la baraja española."""

    OROS = "O"
    COPAS = "C"
    ESPADAS = "E"
    BASTOS = "B"

    @property
    def label(self) -> str:
        return self.name.capitalize()


@dataclass(frozen=True, order=True)
class Card:
    """Un naipe. Inmutable y serializable como ``"12O"`` (rey de oros)."""

    rank: int
    suit: Suit

    def __post_init__(self) -> None:
        if self.rank not in RANKS:
            raise ValueError(f"Número de naipe inválido: {self.rank}")

    @property
    def code(self) -> str:
        return f"{self.rank}{self.suit.value}"

    @classmethod
    def parse(cls, code: str) -> Card:
        """Crea un naipe desde su código, p. ej. ``"3E"`` o ``"12o"``."""
        code = code.strip().upper()
        if len(code) < 2:
            raise ValueError(f"Código de naipe inválido: {code!r}")
        return cls(int(code[:-1]), Suit(code[-1]))

    def __str__(self) -> str:
        return self.code

    def __repr__(self) -> str:
        return f"Card({self.code})"


def normalized_rank(card: Card, eight_kings: bool = True) -> int:
    """Rango usado para comparar en grande, chica y pares.

    Con ocho reyes y ocho ases el 3 se normaliza a 12 (rey) y el 2 a 1 (as).
    """
    if eight_kings:
        if card.rank == 3:
            return 12
        if card.rank == 2:
            return 1
    return card.rank


def point_value(card: Card, eight_kings: bool = True) -> int:
    """Valor para juego y punto [CONVENCIÓN]: figuras 10, ases 1, resto su número."""
    rank = normalized_rank(card, eight_kings)
    return 10 if rank >= 10 else rank


def full_deck() -> list[Card]:
    """Las 40 cartas en orden canónico."""
    return [Card(rank, suit) for suit in Suit for rank in RANKS]


def shuffled_deck(rng: random.Random) -> list[Card]:
    """Baraja mezclada con el generador indicado (reproducible con seed)."""
    deck = full_deck()
    rng.shuffle(deck)
    return deck


def parse_hand(codes: str) -> tuple[Card, ...]:
    """Utilidad para tests y tutoriales: ``parse_hand("12O 3C 1E 7B")``."""
    return tuple(Card.parse(c) for c in codes.split())
