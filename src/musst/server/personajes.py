"""Personajes de parodia que encarnan a los bots en la mesa.

Apodos inventados que recuerdan a tipos de la tele y del corazón, sin nombrar a nadie real.
Las caricaturas y las frases de cada uno están en ``static/personajes.js``; aquí solo se
reparten: en cada partida, cada bot recibe un personaje distinto.
"""

from __future__ import annotations

import random

PERSONAJES: dict[str, str] = {
    "marquesa": "La Marquesa",
    "tentador": "El Tentador",
    "superviviente": "La Superviviente",
    "tronista": "El Tronista",
    "abuela": "La Abuela del Mus",
    "verbena": "El de la Verbena",
    "presentador": "El Presentador",
    "influencer": "La Influencer",
}
"""id → apodo (el id es el que usan las caricaturas del frontend)."""

AVISO = (
    "Personajes de parodia con apodos inventados. Cualquier parecido con personas reales es "
    "una caricatura humorística sin relación con ellas."
)


def reparto(seed: int, asientos: int) -> list[str]:
    """Personajes distintos para ``asientos`` bots, reproducibles con la semilla de la partida."""
    ids = list(PERSONAJES)
    random.Random(seed).shuffle(ids)
    return ids[:asientos]
