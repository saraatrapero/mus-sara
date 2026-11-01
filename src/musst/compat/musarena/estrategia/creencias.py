"""Creencias: qué mano puede tener cada uno de los otros tres jugadores.

Para cada jugador se guarda una **probabilidad para cada uno de los 330 tipos de mano**. Se
parte de la baraja sin las cartas propias (ni las que tiré yo y siguen en los descartes) y se va
corrigiendo con todo lo que se ve en la mesa (inferencia bayesiana: se multiplica por la
verosimilitud de lo observado y se normaliza):

1. **Declaraciones** de pares y de juego: son obligatorias y verdaderas, así que eliminan los
   tipos incompatibles.
2. **Descartes**: tras descartarse, la mano ya no es una mano al azar (cada uno se queda lo
   bueno), y cuantas menos cartas tira, mejor suele ser. Se usa la tabla medida de
   :mod:`~musst.compat.musarena.estrategia.descartes` con el último descarte de cada jugador.
3. **Mus**: en la última ronda de mus, quien corta suele tener buena mano y quien pide mus,
   mala.
4. **Apuestas**: envidar, reenvidar o echar órdago hace más probables las manos fuertes en ese
   lance; pasar o no querer, las débiles; querer, las medianas y fuertes (y más fuertes cuanto
   mayor era la apuesta).

Los pasos 3 y 4 no son seguros (hay faroles y jugadas lentas), por eso se modelan con una
**verosimilitud suave**: una curva logística de la fuerza de la mano con un suelo de farol. Los
parámetros están en :class:`ModeloRival`.

Simplificación: los tres jugadores se tratan como independientes (no se descuenta que las cartas
de uno no pueden estar en la mano de otro).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from musst.compat.musarena.actions import Envido, Mus, NoHayMus, NoQuiero, Ordago, Paso, Quiero, Reenvido
from musst.compat.musarena.estrategia.descartes import FACTOR_DESCARTE
from musst.compat.musarena.estrategia.tipos import (
    FUERZA,
    N_NIVELES,
    N_TIPOS,
    NIVEL,
    TIENE_JUEGO,
    TIENE_PARES,
    pesos_sin,
)
from musst.compat.musarena.estrategia.valor import PERCENTIL
from musst.compat.musarena.hands import Lance
from musst.compat.musarena.observation import Observation
from musst.compat.musarena.state import TANTOS_VACA, Evento


@dataclass(frozen=True)
class ModeloRival:
    """Cómo se supone que juegan los demás (para interpretar sus acciones)."""

    farol: float = 0.12  # probabilidad de envidar o querer sin mano
    centro_envite: float = 0.70  # fuerza a partir de la cual se suele envidar
    centro_ordago: float = 0.80  # fuerza a partir de la cual se suele echar órdago
    centro_quiero: float = 0.35  # fuerza a partir de la cual se suele querer un envite pequeño
    centro_quiero_ordago: float = 0.70  # para querer un órdago hace falta más
    escala: float = 0.12  # cuánto de "suave" es el umbral
    paso_con_mano: float = 0.35  # probabilidad de pasar con mano muy buena (para querer)
    centro_corte: float = 0.62  # percentil de mano a partir del cual se suele cortar el mus
    escala_corte: float = 0.10
    usar_descartes: bool = True  # False: como antes, sin la tabla de descartes (para medir)


def _logistica(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def importancia(apuesta: int, faltan: int) -> float:
    """Cuánto decide la vaca una apuesta (0-1): 1 si quien la gane puede llegar a 40 con ella.

    ``faltan`` son los tantos que le faltan a la pareja que va más adelantada.
    """
    return min(1.0, apuesta / max(1, faltan))


def verosimilitud(
    accion: object, fuerza: float | np.ndarray, modelo: ModeloRival, ante_ordago: bool = False,
    apuesta: int = 0, faltan: int = 40,
) -> float | np.ndarray:
    """Probabilidad relativa de que alguien con esa ``fuerza`` haga esa acción de apuesta.

    ``fuerza`` puede ser un número o un array (una fuerza por tipo de mano). Para querer, cuanto
    más decide la vaca la ``apuesta`` (ver :func:`importancia`), más mano hace falta: un envite
    que da la vaca a quien lo gane se quiere como un órdago.
    """
    m = modelo
    f = np.asarray(fuerza, dtype=float)
    if isinstance(accion, Ordago):
        resultado = m.farol + (1 - m.farol) * _logistica((f - m.centro_ordago) / m.escala)
    elif isinstance(accion, (Envido, Reenvido)):
        resultado = m.farol + (1 - m.farol) * _logistica((f - m.centro_envite) / m.escala)
    elif isinstance(accion, Paso):
        resultado = 1 - (1 - m.paso_con_mano) * _logistica((f - m.centro_envite) / m.escala)
    elif isinstance(accion, (Quiero, NoQuiero)):
        peso_vaca = 1.0 if ante_ordago else importancia(apuesta, faltan)
        centro = m.centro_quiero + (m.centro_quiero_ordago - m.centro_quiero) * peso_vaca
        quiere = m.farol + (1 - m.farol) * _logistica((f - centro) / m.escala)
        resultado = quiere if isinstance(accion, Quiero) else 1 - quiere
    else:
        resultado = np.ones_like(f)
    return float(resultado) if np.ndim(resultado) == 0 else resultado


@lru_cache(maxsize=8192)
def verosimilitud_por_tipo(
    accion: object, lance: Lance, modelo: ModeloRival, ante_ordago: bool = False,
    apuesta: int = 0, faltan: int = 40,
) -> np.ndarray:
    """Verosimilitud de la acción para cada uno de los 330 tipos de mano (memorizada)."""
    v = verosimilitud(accion, FUERZA[lance], modelo, ante_ordago, apuesta, faltan)
    v.setflags(write=False)
    return v


@lru_cache(maxsize=16)
def verosimilitud_mus(corta: bool, modelo: ModeloRival) -> np.ndarray:
    """Probabilidad relativa de cortar (o de pedir mus) con cada tipo de mano."""
    p = modelo.farol + (1 - 2 * modelo.farol) * _logistica(
        (PERCENTIL - modelo.centro_corte) / modelo.escala_corte
    )
    v = p if corta else 1 - p
    v.setflags(write=False)
    return v


def ronda_de_mus(historial: Sequence[Evento]) -> list[Evento]:
    """Acciones de la ronda de mus en curso o de la última (la que se hizo con las manos actuales).

    Una ronda termina cuando los cuatro piden mus: la siguiente acción de mus abre otra ronda.
    """
    ronda: list[Evento] = []
    for evento in historial:
        if isinstance(evento.accion, (Mus, NoHayMus)):
            if len(ronda) == 4:
                ronda = []
            ronda.append(evento)
    return ronda


def ultimos_descartes(historial: Sequence[Evento]) -> dict[int, int]:
    """De cuántas cartas se descartó cada jugador la última vez en esta mano."""
    ultimos: dict[int, int] = {}
    for evento in historial:
        if evento.asiento is not None and evento.accion is None \
                and evento.texto.startswith("Se descarta de "):
            ultimos[evento.asiento] = int(evento.texto.split()[3])
    return ultimos


class Creencias:
    """Distribución de probabilidad sobre el tipo de mano de cada uno de los otros jugadores."""

    def __init__(self, asiento: int, pesos_por_asiento: dict[int, np.ndarray]) -> None:
        self.asiento = asiento
        self._p: dict[int, np.ndarray] = {}
        for otro, w in pesos_por_asiento.items():
            total = w.sum()
            self._p[otro] = w / total if total > 0 else np.full(N_TIPOS, 1 / N_TIPOS)

    @classmethod
    def desde_observacion(
        cls,
        obs: Observation,
        modelo: ModeloRival | None = None,
        modelos: dict[int, ModeloRival] | None = None,
    ) -> Creencias:
        """Creencias de ``obs.asiento`` a partir de todo lo que ha visto en la mano.

        ``modelos`` permite usar un modelo distinto para cada jugador (por ejemplo, con la tasa
        de farol aprendida de cada rival); los que falten usan ``modelo``.
        """
        modelo = modelo or ModeloRival()
        modelos = modelos or {}
        conocidas = (*obs.cartas, *obs.mis_descartes) if modelo.usar_descartes else obs.cartas
        base = pesos_sin(conocidas)
        otros = [a for a in range(4) if a != obs.asiento]
        w = {a: base.copy() for a in otros}

        # 1. Declaraciones (restricción dura).
        for lance, tiene in ((Lance.PARES, TIENE_PARES), (Lance.JUEGO, TIENE_JUEGO)):
            declaracion = obs.declaracion(lance)
            if declaracion is not None:
                for a in otros:
                    w[a] *= tiene == declaracion[a]

        # 2. Último descarte de cada jugador (medido).
        for a, n in ultimos_descartes(obs.historial).items():
            if a in w and modelo.usar_descartes:
                w[a] *= FACTOR_DESCARTE[n]

        # 3. Última ronda de mus (restricción suave).
        for evento in ronda_de_mus(obs.historial):
            if evento.asiento in w:
                m = modelos.get(evento.asiento, modelo)
                w[evento.asiento] *= verosimilitud_mus(isinstance(evento.accion, NoHayMus), m)

        # 4. Apuestas de cada lance (restricción suave).
        faltan = TANTOS_VACA - max(obs.tantos)
        ordago_en: set[Lance] = set()
        apostado: dict[Lance, int] = {}
        for evento in obs.historial:
            lance, accion = evento.lance, evento.accion
            if lance is None or accion is None:
                continue
            if evento.asiento in w:
                ante_ordago = lance in ordago_en and not isinstance(accion, Ordago)
                w[evento.asiento] *= verosimilitud_por_tipo(
                    accion, lance, modelos.get(evento.asiento, modelo), ante_ordago,
                    apostado.get(lance, 0), faltan,
                )
            if isinstance(accion, Ordago):
                ordago_en.add(lance)
            elif isinstance(accion, Envido):
                apostado[lance] = accion.tantos
            elif isinstance(accion, Reenvido):
                apostado[lance] = apostado.get(lance, 0) + accion.tantos
        return cls(obs.asiento, w)

    def condicionar(self, factores: dict[int, np.ndarray]) -> Creencias:
        """Nuevas creencias multiplicando los pesos de algunos jugadores por ``factores``.

        Sirve para preguntar "¿y si este rival me quiere?": se multiplica su distribución por la
        verosimilitud de querer con cada tipo de mano.
        """
        nuevos = {otro: p * factores[otro] if otro in factores else p
                  for otro, p in self._p.items()}
        return Creencias(self.asiento, nuevos)

    def probabilidades(self, asiento: int) -> np.ndarray:
        """Probabilidad de cada tipo de mano para ``asiento`` (suma 1)."""
        return self._p[asiento]

    def distribucion_nivel(self, asiento: int, lance: Lance) -> np.ndarray:
        """Probabilidad de cada nivel de ``lance`` para ``asiento``."""
        return np.bincount(NIVEL[lance], weights=self._p[asiento], minlength=N_NIVELES[lance])

    def esperanza(self, asiento: int, valores: np.ndarray) -> float:
        """Valor esperado de una tabla por tipo (por ejemplo, el bonus de pares)."""
        return float(self._p[asiento] @ valores)
