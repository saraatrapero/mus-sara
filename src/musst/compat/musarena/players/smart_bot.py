"""Bot inteligente: juega con una red neuronal entrenada (ver :mod:`musst.compat.musarena.ia`)."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np

from musst.compat.musarena.actions import Action
from musst.compat.musarena.ia import acciones
from musst.compat.musarena.ia.codificacion import N_ENTRADAS, codificar
from musst.compat.musarena.ia.red import Red
from musst.compat.musarena.observation import Observation
from musst.compat.musarena.player import Bot

#: Modelo que se usa si no se indica otro.
MODELO_POR_DEFECTO = Path(__file__).resolve().parent.parent / "ia" / "modelos" / "inteligente.npz"


@lru_cache(maxsize=8)
def _cargar(ruta: Path) -> Red:
    """Carga un modelo una sola vez aunque se creen muchos bots (la red no se modifica)."""
    return Red.cargar(ruta)


class SmartBot(Bot):
    """Elige la acción con la red neuronal.

    - ``modelo``: ruta a un ``.npz`` o una :class:`~musst.compat.musarena.ia.red.Red` ya cargada.
    - ``temperatura``: 0 elige siempre la acción más probable; más de 0 elige al azar según las
      probabilidades de la red (más variado, más "humano"; 1 es la distribución tal cual).
    """

    tipo = "inteligente"
    descripcion = "Red neuronal entrenada: imita a los mejores y aprende jugando"

    def __init__(
        self,
        nombre: str | None = None,
        seed: int | None = None,
        modelo: str | Path | Red | None = None,
        temperatura: float = 0.0,
    ) -> None:
        super().__init__(nombre, seed)
        red = modelo if isinstance(modelo, Red) else _cargar(Path(modelo or MODELO_POR_DEFECTO))
        if red.n_entradas != N_ENTRADAS:
            raise ValueError(
                f"El modelo espera {red.n_entradas} entradas y la codificación tiene "
                f"{N_ENTRADAS}: hay que reentrenarlo"
            )
        self.red = red
        self.temperatura = temperatura
        self.razon = ""

    def probabilidades(self, observation: Observation, legal_actions: Sequence[Action]
                       ) -> tuple[np.ndarray, np.ndarray, float]:
        """(máscara de legales, probabilidad de cada acción del catálogo, valor estimado)."""
        mascara = acciones.mascara(legal_actions, observation.cartas)
        p, v = self.red.evaluar(codificar(observation), mascara)
        return mascara, p, v

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        mascara, p, v = self.probabilidades(observation, legal_actions)
        if not mascara.any():  # no debería pasar: el catálogo cubre todas las fases
            self.razon = "sin acciones del catálogo: primera legal"
            return legal_actions[0]
        if self.temperatura > 0:
            # En float64 y como números de Python: con float32, numpy redondea el número sorteado
            # al compararlo con la suma acumulada y, muy de vez en cuando, el sorteo caía en una
            # acción con probabilidad 0 (ilegal).
            q = np.where(mascara, p.astype(np.float64) ** (1 / self.temperatura), 0.0)
            i = int(self.rng.choices(range(len(q)), weights=q.tolist())[0])
        else:
            i = int(np.argmax(p))
        mejores = np.argsort(-p)[:3]
        self.razon = (f"valor {v:+.2f}; " + ", ".join(
            f"{acciones.NOMBRES[j]} {p[j]:.0%}" for j in mejores if p[j] > 0))
        return acciones.accion(i, observation.cartas)
