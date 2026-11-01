"""Probabilidad de ganar un lance, respuesta del rival, bonus esperados y probabilidad de vaca."""

from __future__ import annotations

import math
from collections.abc import Collection, Sequence

import numpy as np

from musst.compat.musarena.actions import Quiero
from musst.compat.musarena.cards import Carta
from musst.compat.musarena.estrategia.creencias import Creencias, ModeloRival, verosimilitud_por_tipo
from musst.compat.musarena.estrategia.tipos import BONUS_JUEGO, BONUS_PARES, N_NIVELES, NIVEL, indice_de
from musst.compat.musarena.hands import Lance, orden_desde_mano
from musst.compat.musarena.state import TANTOS_VACA, pareja


def prob_ganar_lance(
    lance: Lance,
    asiento: int,
    cartas: Sequence[Carta],
    mano: int,
    participantes: Collection[int],
    creencias: Creencias,
    incluir_companero: bool = True,
) -> float:
    """Probabilidad de que la pareja de ``asiento`` gane ``lance`` entre los ``participantes``.

    Es exacta dadas las creencias: gana la mejor mano y, a igualdad, el jugador más cercano a la
    mano. Para cada nivel ``v`` y cada jugador ``s``, la probabilidad de que ``s`` gane con ``v``
    es: los que hablan antes que ``s`` tienen menos de ``v``, ``s`` tiene ``v`` y los que hablan
    después tienen ``v`` o menos. Se suman los casos en que ``s`` es de la pareja propia.

    Con ``incluir_companero=False`` se calcula como si el compañero no jugase (lo que puede
    ganar uno solo con su mano), útil cuando el compañero todavía tiene que hablar.
    """
    companero = (asiento + 2) % 4
    orden = [
        s for s in orden_desde_mano(mano)
        if s in participantes and (incluir_companero or s != companero)
    ]
    n = N_NIVELES[lance]
    distribuciones = np.zeros((len(orden), n))
    for fila, s in enumerate(orden):
        if s == asiento:
            distribuciones[fila, NIVEL[lance][indice_de(cartas)]] = 1.0
        else:
            distribuciones[fila] = creencias.distribucion_nivel(s, lance)
    hasta = np.cumsum(distribuciones, axis=1)  # P(nivel <= v)
    menos = np.zeros_like(hasta)  # P(nivel < v)
    menos[:, 1:] = hasta[:, :-1]

    mia = pareja(asiento)
    resultado = 0.0
    for fila, s in enumerate(orden):
        if pareja(s) != mia:
            continue
        casos = distribuciones[fila].copy()
        if fila > 0:
            casos *= menos[:fila].prod(axis=0)  # los que hablan antes, peor
        if fila < len(orden) - 1:
            casos *= hasta[fila + 1:].prod(axis=0)  # los que hablan después, peor o igual
        resultado += casos.sum()
    return float(resultado)


def respuesta_rival(
    lance: Lance,
    asiento: int,
    cartas: Sequence[Carta],
    mano: int,
    participantes: Collection[int],
    creencias: Creencias,
    modelo: ModeloRival,
    apuesta: int,
    ordago: bool = False,
    faltan: int = TANTOS_VACA,
    modelos: dict[int, ModeloRival] | None = None,
) -> tuple[float, float]:
    """Qué pasa si la pareja de ``asiento`` apuesta: ``(prob. de que quieran, prob. de ganar si
    quieren)``.

    Responde primero el rival más cercano a la mano y, si no quiere, su compañero. Cada uno
    quiere con una probabilidad que depende de la fuerza de su mano (ver
    :func:`~musst.compat.musarena.estrategia.creencias.verosimilitud`), así que "si me quieren" es una mala
    noticia: la probabilidad de ganar se recalcula con las creencias condicionadas a que el
    rival quiere.

    ``faltan`` son los tantos que le faltan a la pareja más adelantada (un envite que decide la
    vaca se quiere como un órdago). ``modelos`` permite un modelo distinto por rival, por
    ejemplo con lo aprendido de cada uno; los que falten usan ``modelo``.
    """
    mia = pareja(asiento)
    rivales = [s for s in orden_desde_mano(mano) if s in participantes and pareja(s) != mia]
    modelos = modelos or {}

    casos: list[tuple[float, float]] = []  # (probabilidad del caso, prob. de ganar en ese caso)
    prob_llegar = 1.0  # probabilidad de que los rivales anteriores no hayan querido
    condicion: dict[int, np.ndarray] = {}
    for rival in rivales:
        m = modelos.get(rival, modelo)
        quiere = verosimilitud_por_tipo(Quiero(), lance, m, ordago, apuesta, faltan)
        no_quiere = 1 - quiere
        q = creencias.esperanza(rival, quiere)
        condicionadas = creencias.condicionar({**condicion, rival: quiere})
        ganar = prob_ganar_lance(lance, asiento, cartas, mano, participantes, condicionadas)
        casos.append((prob_llegar * q, ganar))
        prob_llegar *= 1 - q
        condicion[rival] = no_quiere
    prob_quieren = sum(p for p, _ in casos)
    if prob_quieren <= 0:
        return 0.0, 0.0
    return prob_quieren, sum(p * g for p, g in casos) / prob_quieren


def bonus_pareja(
    lance: Lance,
    p: int,
    asiento: int,
    cartas: Sequence[Carta],
    participantes: Collection[int],
    creencias: Creencias,
) -> float:
    """Bonus que cobraría la pareja ``p`` si ganase ``lance`` (valor esperado).

    En pares y juego cobran los jugadores de la pareja que tienen la jugada; en el punto se
    cobra 1; en grande y chica no hay bonus.
    """
    if lance is Lance.PUNTO:
        return 1.0
    if lance not in (Lance.PARES, Lance.JUEGO):
        return 0.0
    tabla = BONUS_PARES if lance is Lance.PARES else BONUS_JUEGO
    total = 0.0
    for s in participantes:
        if pareja(s) != p:
            continue
        total += float(tabla[indice_de(cartas)]) if s == asiento else creencias.esperanza(s, tabla)
    return total


def prob_vaca(propios: float, rivales: float, dispersion: float = 9.0) -> float:
    """Probabilidad aproximada de ganar la vaca con ``propios`` tantos frente a ``rivales``.

    Modelo sencillo: la diferencia entre lo que le falta a cada pareja, dividida por una
    incertidumbre que crece con lo que queda de vaca, pasada por la distribución normal. Da 0,5
    con el marcador igualado y se acerca a 1 (o a 0) cuanto más clara es la ventaja.
    """
    if propios >= TANTOS_VACA:
        return 1.0
    if rivales >= TANTOS_VACA:
        return 0.0
    faltan_propios = TANTOS_VACA - propios
    faltan_rivales = TANTOS_VACA - rivales
    x = (faltan_rivales - faltan_propios) / (
        dispersion * math.sqrt((faltan_propios + faltan_rivales) / 12 + 1)
    )
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))
