"""Codificación de la observación: de lo que ve un jugador a un vector de números.

La red neuronal necesita un vector de tamaño fijo. Todo se expresa **respecto al jugador** que
decide (asiento relativo 0 = yo, 1 = rival de la derecha, que habla después de mí, 2 =
compañero, 3 = rival de la izquierda), así que la red aprende lo mismo sea cual sea su asiento.

Bloques del vector (ver :data:`NOMBRES` para el detalle de cada posición):

1. Mis cartas: el rango de cada carta en su posición (la mano llega ordenada) y cuántas hay de
   cada rango.
2. Mi mano: fuerza en cada lance, percentil, puntos, pares y juego.
3. Fase, lance y mi posición respecto a la mano.
4. Marcador: tantos, vacas y probabilidad de ganar la vaca.
5. Apuesta en curso: tantos, deje, órdago, quién apuesta y quién falta por hablar.
6. Declaraciones de pares y de juego de los demás.
7. Mus y descartes: quién ha pedido mus o cortado en la ronda actual y cuántas cartas se
   descartó cada uno en la última.
8. Lances ya jugados en la mano: cómo terminaron y por cuánto.
9. Última acción de cada jugador en el lance en curso.
10. Análisis de :mod:`musst.compat.musarena.estrategia`: probabilidad de ganar el lance (con y sin
    compañero), bonus en juego y fuerza esperada de la mano de cada uno de los demás.

Solo usa la :class:`~musst.compat.musarena.observation.Observation`: nunca información oculta.
"""

from __future__ import annotations

import re

import numpy as np

from musst.compat.musarena.actions import (
    Envido,
    Mus,
    NoHayMus,
    NoQuiero,
    Ordago,
    Paso,
    Quiero,
    Reenvido,
)
from musst.compat.musarena.estrategia.creencias import Creencias, ronda_de_mus
from musst.compat.musarena.estrategia.evaluacion import bonus_pareja, prob_ganar_lance, prob_vaca
from musst.compat.musarena.estrategia.tipos import (
    BONUS_JUEGO,
    BONUS_PARES,
    FUERZA,
    PUNTOS,
    RANGOS,
    TIENE_JUEGO,
    TIENE_PARES,
    indice_de,
)
from musst.compat.musarena.estrategia.valor import PERCENTIL
from musst.compat.musarena.hands import Lance
from musst.compat.musarena.observation import Observation
from musst.compat.musarena.state import TANTOS_VACA, Fase, TipoResultado, pareja

_LANCES = (Lance.GRANDE, Lance.CHICA, Lance.PARES, Lance.JUEGO, Lance.PUNTO)
_TIPOS_ACCION = (Paso, Envido, Reenvido, Ordago, Quiero, NoQuiero)
_RESULTADOS = (TipoResultado.EN_PASO, TipoResultado.QUERIDO, TipoResultado.NO_QUERIDO,
               TipoResultado.SIN_APUESTA)
_OTROS = (1, 2, 3)  # asientos relativos: rival derecha, compañero, rival izquierda
_NOMBRE_RELATIVO = {0: "yo", 1: "rival_der", 2: "companero", 3: "rival_izq"}
_DESCARTE_N = re.compile(r"(\d+)")


class _Vector:
    """Acumula valores con nombre (los nombres solo se guardan la primera vez)."""

    def __init__(self, con_nombres: bool) -> None:
        self.valores: list[float] = []
        self.nombres: list[str] | None = [] if con_nombres else None

    def add(self, nombre: str, valor: float) -> None:
        self.valores.append(float(valor))
        if self.nombres is not None:
            self.nombres.append(nombre)

    def one_hot(self, nombre: str, opciones: tuple, valor: object) -> None:
        for o in opciones:
            self.add(f"{nombre}={getattr(o, '__name__', o)}", valor == o)


def _relativo(asiento: int, yo: int) -> int:
    return (asiento - yo) % 4


def _codificar(obs: Observation, v: _Vector, creencias: Creencias | None) -> None:
    yo = obs.asiento
    tipo = indice_de(obs.cartas)

    # 1. Cartas.
    for posicion in range(4):
        rango = obs.cartas[posicion].rango
        for r in RANGOS:
            v.add(f"carta{posicion + 1}_rango{r}", rango == r)
    for r in RANGOS:
        v.add(f"cuantas_rango{r}", sum(c.rango == r for c in obs.cartas) / 4)

    # 2. Mano.
    for lance in _LANCES:
        v.add(f"fuerza_{lance.value}", FUERZA[lance][tipo])
    v.add("percentil", PERCENTIL[tipo])
    v.add("puntos", PUNTOS[tipo] / 40)
    v.add("tiene_pares", TIENE_PARES[tipo])
    v.add("bonus_pares", BONUS_PARES[tipo] / 3)
    v.add("tiene_juego", TIENE_JUEGO[tipo])
    v.add("bonus_juego", BONUS_JUEGO[tipo] / 3)

    # 3. Fase, lance y posición.
    v.one_hot("fase", (Fase.MUS, Fase.DESCARTE, Fase.LANCE), obs.fase)
    v.one_hot("lance", _LANCES, obs.lance)
    v.one_hot("posicion_desde_mano", (0, 1, 2, 3), (yo - obs.mano) % 4)

    # 4. Marcador.
    propios, rivales = obs.tantos[obs.pareja], obs.tantos[1 - obs.pareja]
    v.add("tantos_propios", propios / TANTOS_VACA)
    v.add("tantos_rivales", rivales / TANTOS_VACA)
    v.add("vacas_propias", obs.vacas[obs.pareja] / obs.vacas_para_ganar)
    v.add("vacas_rivales", obs.vacas[1 - obs.pareja] / obs.vacas_para_ganar)
    v.add("prob_vaca", prob_vaca(propios, rivales))
    v.add("mejor_de_5", obs.vacas_para_ganar == 3)

    # 5. Apuesta en curso.
    ap = obs.apuesta
    hay = ap is not None
    v.add("apuesta_tantos", ap.tantos / TANTOS_VACA if hay else 0)
    v.add("apuesta_deje", ap.deje / TANTOS_VACA if hay else 0)
    v.add("apuesta_ordago", hay and ap.ordago)
    v.add("apuesta_mia", hay and ap.pareja_apostadora == obs.pareja)
    v.add("apuesta_rival", hay and ap.pareja_apostadora == 1 - obs.pareja)
    v.add("por_hablar", len(ap.por_hablar) / 4 if hay else 0)
    v.add("companero_habla_despues", hay and obs.companero in ap.por_hablar[1:])
    v.add("companero_participa", hay and obs.companero in ap.participantes)
    rivales_part = sum(pareja(s) != obs.pareja for s in ap.participantes) if hay else 0
    v.add("rivales_participan", rivales_part / 2)
    v.add("hablo_el_ultimo", hay and len(ap.por_hablar) == 1)

    # 6. Declaraciones.
    for lance in (Lance.PARES, Lance.JUEGO):
        declaracion = obs.declaracion(lance)
        for rel in _OTROS:
            s = (yo + rel) % 4
            v.add(f"{_NOMBRE_RELATIVO[rel]}_{lance.value}_si",
                  declaracion is not None and declaracion[s])
            v.add(f"{_NOMBRE_RELATIVO[rel]}_{lance.value}_no",
                  declaracion is not None and not declaracion[s])

    # 7. Mus y descartes.
    ronda = ronda_de_mus(obs.historial) if obs.fase is Fase.MUS else []
    for rel in _OTROS:
        s = (yo + rel) % 4
        acciones = [e.accion for e in ronda if e.asiento == s]
        v.add(f"{_NOMBRE_RELATIVO[rel]}_pide_mus", any(isinstance(a, Mus) for a in acciones))
        v.add(f"{_NOMBRE_RELATIVO[rel]}_corta", any(isinstance(a, NoHayMus) for a in acciones))
    descartes = {}
    rondas = 0
    for e in obs.historial:
        if e.asiento is not None and e.accion is None and e.texto.startswith("Se descarta"):
            if e.asiento == obs.mano:
                rondas += 1
            descartes[e.asiento] = int(_DESCARTE_N.search(e.texto).group(1))
    for rel in _OTROS:
        v.add(f"{_NOMBRE_RELATIVO[rel]}_descarto", descartes.get((yo + rel) % 4, 0) / 4)
    v.add("rondas_de_descarte", min(rondas, 3) / 3)

    # 8. Lances ya jugados.
    resultados = {r.lance: r for r in obs.resultados}
    for lance in (Lance.GRANDE, Lance.CHICA, Lance.PARES, Lance.JUEGO):
        r = resultados.get(lance) or (resultados.get(Lance.PUNTO) if lance is Lance.JUEGO else None)
        v.one_hot(f"resultado_{lance.value}", _RESULTADOS, r.tipo if r else None)
        v.add(f"resultado_{lance.value}_tantos", r.apuesta / TANTOS_VACA if r else 0)
        v.add(f"resultado_{lance.value}_lo_gano_yo",
              r is not None and r.pareja == obs.pareja)
        v.add(f"resultado_{lance.value}_lo_gano_rival",
              r is not None and r.pareja == 1 - obs.pareja)

    # 9. Última acción de cada jugador en el lance en curso.
    ultima: dict[int, object] = {}
    for e in obs.historial:
        if e.lance is not None and e.lance is obs.lance and e.asiento is not None and e.accion:
            ultima[e.asiento] = type(e.accion)
    for rel in (0, *_OTROS):
        v.one_hot(f"ultima_{_NOMBRE_RELATIVO[rel]}", _TIPOS_ACCION, ultima.get((yo + rel) % 4))

    # 10. Análisis de la estrategia.
    if creencias is None:
        creencias = Creencias.desde_observacion(obs)
    if hay:
        args = (obs.lance, yo, obs.cartas, obs.mano, ap.participantes, creencias)
        v.add("p_ganar_lance", prob_ganar_lance(*args))
        v.add("p_ganar_lance_solo", prob_ganar_lance(*args, incluir_companero=False))
        bonus = (obs.lance, obs.pareja, yo, obs.cartas, ap.participantes, creencias)
        v.add("bonus_propio", bonus_pareja(*bonus) / 6)
        bonus_r = (obs.lance, 1 - obs.pareja, yo, obs.cartas, ap.participantes, creencias)
        v.add("bonus_rival", bonus_pareja(*bonus_r) / 6)
    else:
        for nombre in ("p_ganar_lance", "p_ganar_lance_solo", "bonus_propio", "bonus_rival"):
            v.add(nombre, 0)
    lance_ref = obs.lance or Lance.GRANDE
    for rel in _OTROS:
        s = (yo + rel) % 4
        v.add(f"{_NOMBRE_RELATIVO[rel]}_fuerza_esperada",
              creencias.esperanza(s, FUERZA[lance_ref]))
        v.add(f"{_NOMBRE_RELATIVO[rel]}_percentil_esperado", creencias.esperanza(s, PERCENTIL))


def codificar(obs: Observation, creencias: Creencias | None = None) -> np.ndarray:
    """Vector de números (float32) que describe la observación para la red."""
    v = _Vector(con_nombres=False)
    _codificar(obs, v, creencias)
    return np.asarray(v.valores, dtype=np.float32)


def _nombres() -> tuple[str, ...]:
    # ADAPTADO para MUS.ST: el original sacaba la observación de ejemplo del motor de musarena,
    # que no se ha copiado. Aquí sale del motor FEM traducida por el adaptador; solo se usa para
    # saber el nombre (y el número) de las posiciones del vector, que no cambian.
    from musst.bots.adaptador import traducir_observacion
    from musst.engine.game import MusGame
    from musst.engine.observation import build_observation

    game = MusGame(seed=0)
    v = _Vector(con_nombres=True)
    _codificar(traducir_observacion(build_observation(game, game.turn)), v, None)
    return tuple(v.nombres)


#: Nombre de cada posición del vector.
NOMBRES: tuple[str, ...] = _nombres()
N_ENTRADAS = len(NOMBRES)

__all__ = ["N_ENTRADAS", "NOMBRES", "codificar"]
