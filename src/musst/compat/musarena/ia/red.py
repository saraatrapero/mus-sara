"""La red neuronal del bot inteligente, en numpy (para jugar no hace falta PyTorch).

Es un perceptrón multicapa: la entrada (el vector de :mod:`~musst.compat.musarena.ia.codificacion`) pasa por
varias capas ocultas con activación ReLU y termina en dos "cabezas":

- **política**: una puntuación para cada acción del catálogo (:mod:`~musst.compat.musarena.ia.acciones`).
  Se tapan las ilegales y se convierten en probabilidades con softmax;
- **valor**: un número entre -1 y 1 que estima si la pareja del jugador va a ganar la vaca
  (lo usará el aprendizaje por refuerzo).

Los pesos se guardan en un archivo ``.npz``. PyTorch solo se usa para entrenar; al terminar,
los pesos se exportan a este formato.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Red:
    """Pesos de la red: ``capas`` es una lista de pares (W, b) de las capas ocultas."""

    capas: list[tuple[np.ndarray, np.ndarray]]
    politica: tuple[np.ndarray, np.ndarray]
    valor: tuple[np.ndarray, np.ndarray]
    info: dict

    @property
    def n_entradas(self) -> int:
        return self.capas[0][0].shape[0]

    def _oculta(self, x: np.ndarray) -> np.ndarray:
        for w, b in self.capas:
            x = np.maximum(x @ w + b, 0.0)
        return x

    def evaluar(self, x: np.ndarray, mascara: np.ndarray) -> tuple[np.ndarray, float]:
        """Probabilidad de cada acción (0 en las ilegales) y valor estimado de la posición."""
        h = self._oculta(x.astype(np.float32))
        logits = h @ self.politica[0] + self.politica[1]
        logits = np.where(mascara, logits, -np.inf)
        logits -= logits.max()
        p = np.exp(logits)
        p /= p.sum()
        v = float(np.tanh(h @ self.valor[0] + self.valor[1])[0])
        return p, v

    # --- Archivo -------------------------------------------------------------------------

    def guardar(self, ruta: str | Path) -> None:
        arrays = {}
        for i, (w, b) in enumerate(self.capas):
            arrays[f"capa{i}_w"], arrays[f"capa{i}_b"] = w, b
        arrays["politica_w"], arrays["politica_b"] = self.politica
        arrays["valor_w"], arrays["valor_b"] = self.valor
        arrays["info"] = np.frombuffer(json.dumps(self.info).encode(), dtype=np.uint8)
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(ruta, **arrays)

    @classmethod
    def cargar(cls, ruta: str | Path) -> Red:
        with np.load(ruta) as datos:
            n = sum(1 for k in datos.files if k.endswith("_w") and k.startswith("capa"))
            capas = [(datos[f"capa{i}_w"], datos[f"capa{i}_b"]) for i in range(n)]
            politica = (datos["politica_w"], datos["politica_b"])
            valor = (datos["valor_w"], datos["valor_b"])
            info = json.loads(bytes(datos["info"]).decode())
        return cls(capas, politica, valor, info)

    @classmethod
    def aleatoria(cls, n_entradas: int, n_acciones: int, ocultas: tuple[int, ...] = (256, 256),
                  seed: int = 0) -> Red:
        """Red con pesos al azar (para tests y como punto de partida)."""
        rng = np.random.default_rng(seed)
        tamanos = (n_entradas, *ocultas)
        capas = [
            (rng.normal(0, np.sqrt(2 / a), (a, b)).astype(np.float32), np.zeros(b, np.float32))
            for a, b in zip(tamanos[:-1], tamanos[1:], strict=True)
        ]
        ultima = tamanos[-1]
        politica = (rng.normal(0, 0.01, (ultima, n_acciones)).astype(np.float32),
                    np.zeros(n_acciones, np.float32))
        valor = (rng.normal(0, 0.01, (ultima, 1)).astype(np.float32), np.zeros(1, np.float32))
        return cls(capas, politica, valor, {"origen": "aleatoria"})
