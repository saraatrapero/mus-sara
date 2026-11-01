"""Lectura de rivales: aprender durante la partida cuánto va de farol cada jugador.

Al final de cada mano se enseñan las cartas de todos, así que se puede comprobar, para cada
envite o "quiero" de un jugador, si lo hizo con buena mano o sin ella. Con eso se estima su
**tasa de farol**: con qué frecuencia apuesta o quiere con una mano floja.

La estimación es bayesiana (distribución beta): se parte de la tasa que supone el
:class:`~musst.compat.musarena.estrategia.creencias.ModeloRival` como si ya se hubieran visto unas cuantas
jugadas, y cada jugada observada la corrige un poco. Así, con pocas manos vistas se confía en
el modelo general y, con muchas, en lo observado.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from musst.compat.musarena.actions import Envido, NoQuiero, Ordago, Paso, Quiero, Reenvido
from musst.compat.musarena.estrategia.creencias import ModeloRival
from musst.compat.musarena.estrategia.tipos import FUERZA, indice_de
from musst.compat.musarena.state import ResumenMano

#: Una mano con fuerza menor que esta en un lance se considera "floja" para ese lance.
FUERZA_FLOJA = 0.45


@dataclass
class _Contador:
    ocasiones: int = 0  # veces que habló con mano floja
    faroles: int = 0  # de ellas, veces que envidó o quiso


@dataclass
class LectorRivales:
    """Lleva la cuenta, por asiento, de las jugadas con mano floja de cada jugador."""

    peso_previo: float = 10.0  # cuántas jugadas "vale" la tasa supuesta al principio
    contadores: dict[int, _Contador] = field(default_factory=dict)

    def registrar(self, resumen: ResumenMano, asiento_propio: int) -> None:
        """Aprende de una mano terminada (sus acciones y las cartas enseñadas)."""
        tipos = [indice_de(cartas) for cartas in resumen.cartas]
        for evento in resumen.historial:
            s, accion, lance = evento.asiento, evento.accion, evento.lance
            if s is None or s == asiento_propio or lance is None or accion is None:
                continue
            if FUERZA[lance][tipos[s]] >= FUERZA_FLOJA:
                continue
            if not isinstance(accion, (Paso, Envido, Reenvido, Ordago, Quiero, NoQuiero)):
                continue
            c = self.contadores.setdefault(s, _Contador())
            c.ocasiones += 1
            c.faroles += isinstance(accion, (Envido, Reenvido, Ordago, Quiero))

    def tasa_farol(self, asiento: int, previa: float) -> float:
        """Tasa de farol estimada de ``asiento`` partiendo de la tasa ``previa``."""
        c = self.contadores.get(asiento, _Contador())
        tasa = (previa * self.peso_previo + c.faroles) / (self.peso_previo + c.ocasiones)
        return min(0.6, max(0.02, tasa))

    def modelos(self, base: ModeloRival, asiento_propio: int) -> dict[int, ModeloRival]:
        """Un modelo por cada uno de los otros jugadores, con su tasa de farol estimada."""
        # Se redondea para que los modelos se repitan y la memoria de cálculos sirva.
        return {
            s: replace(base, farol=round(self.tasa_farol(s, base.farol), 2))
            for s in range(4) if s != asiento_propio
        }
