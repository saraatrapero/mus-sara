"""Bot aleatorio: el nivel más bajo, útil como rival de referencia."""

from __future__ import annotations

from collections.abc import Sequence

from musst.compat.musarena.actions import Action
from musst.compat.musarena.observation import Observation
from musst.compat.musarena.player import Bot


class RandomBot(Bot):
    """Elige al azar una acción legal.

    Primero elige al azar el **tipo** de acción (paso, envido, órdago…) y luego una concreta.
    Si eligiera directamente de la lista, casi siempre envidaría o reenvidaría, porque hay
    39 cantidades distintas frente a un solo "paso".
    """

    tipo = "random"
    descripcion = "Elige una jugada legal al azar"

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        tipos = self._tipos(legal_actions)
        tipo = self.rng.choice(tipos)
        return self.rng.choice([a for a in legal_actions if type(a) is tipo])

    @staticmethod
    def _tipos(legal_actions: Sequence[Action]) -> list[type]:
        """Tipos de acción distintos, en el orden en que aparecen (para ser reproducible)."""
        return list(dict.fromkeys(type(a) for a in legal_actions))
