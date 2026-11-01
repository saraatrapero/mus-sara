"""Vista parcial de la partida desde un asiento.

Una :class:`Observation` contiene **solo** las cartas del propio jugador y la información pública
(marcador, apuestas, declaraciones, historial, chat y las cartas enseñadas en manos ya terminadas).
Nunca incluye las cartas de los demás de la mano en curso, ni el mazo, ni el generador aleatorio.

Todo está en tuplas y dataclasses inmutables: un bot puede guardarla o analizarla sin riesgo de
tocar el estado real.
"""

from __future__ import annotations

from dataclasses import dataclass

from musst.compat.musarena.cards import Carta
from musst.compat.musarena.chat import MensajeChat
from musst.compat.musarena.hands import Lance
from musst.compat.musarena.state import (
    Cobro,
    Evento,
    Fase,
    ResultadoLance,
    ResumenMano,
    State,
    pareja,
)


@dataclass(frozen=True)
class ApuestaPublica:
    """Lo que se ve de las apuestas del lance en curso."""

    participantes: tuple[int, ...]
    por_hablar: tuple[int, ...]
    tantos: int
    deje: int
    pareja_apostadora: int | None
    ordago: bool


@dataclass(frozen=True)
class Observation:
    """Lo que un jugador sabe cuando le toca decidir."""

    asiento: int
    cartas: tuple[Carta, ...]
    fase: Fase
    turno: int | None
    mano: int
    numero_mano: int
    lance: Lance | None
    apuesta: ApuestaPublica | None
    tantos: tuple[int, int]
    vacas: tuple[int, int]
    vacas_para_ganar: int
    declaraciones: tuple[tuple[Lance, tuple[bool, bool, bool, bool]], ...]
    resultados: tuple[ResultadoLance, ...]
    cobros: tuple[Cobro, ...]
    historial: tuple[Evento, ...]
    manos_jugadas: tuple[ResumenMano, ...]
    chat: tuple[MensajeChat, ...]
    ganador: int | None
    #: Cartas que tiré en esta mano y siguen en la pila de descartes (nadie las tiene). Si se
    #: rebarajan vuelven al mazo y dejan de estar aquí.
    mis_descartes: tuple[Carta, ...] = ()
    #: Primera mano de la partida con la mano corrida: ``mano`` es quien empieza la ronda de mus
    #: y será la mano quien corte (``docs/reglas.md``, punto 3.6).
    corrida: bool = False

    @property
    def pareja(self) -> int:
        return pareja(self.asiento)

    @property
    def companero(self) -> int:
        return (self.asiento + 2) % 4

    @property
    def es_mi_turno(self) -> bool:
        return self.turno == self.asiento

    def declaracion(self, lance: Lance) -> tuple[bool, bool, bool, bool] | None:
        """Quién ha declarado tener pares o juego (por asiento), si ya se ha declarado."""
        for lance_declarado, valores in self.declaraciones:
            if lance_declarado is lance:
                return valores
        return None


def observe(
    state: State, asiento: int, chat: tuple[MensajeChat, ...] = ()
) -> Observation:
    """Construye la observación de ``asiento``. Es la única vía por la que un jugador ve la mesa."""
    if asiento not in range(4):
        raise ValueError(f"Asiento no válido: {asiento}")
    ap = state.apuesta
    apuesta = None
    if ap is not None:
        apuesta = ApuestaPublica(
            participantes=ap.participantes,
            por_hablar=tuple(ap.por_hablar),
            tantos=ap.tantos,
            deje=ap.deje,
            pareja_apostadora=ap.pareja_apostadora,
            ordago=ap.ordago,
        )
    declaraciones = tuple(
        (lance, tuple(d[a] for a in range(4))) for lance, d in state.declaraciones.items()
    )
    return Observation(
        asiento=asiento,
        cartas=tuple(state.cartas[asiento]),
        fase=state.fase,
        turno=state.turno,
        mano=state.mano,
        numero_mano=state.numero_mano,
        lance=state.lance,
        apuesta=apuesta,
        tantos=(state.tantos[0], state.tantos[1]),
        vacas=(state.vacas[0], state.vacas[1]),
        vacas_para_ganar=state.vacas_para_ganar,
        declaraciones=declaraciones,
        resultados=tuple(state.resultados),
        cobros=tuple(state.cobros),
        historial=tuple(state.historial),
        manos_jugadas=tuple(state.manos_jugadas),
        chat=tuple(chat),
        ganador=state.ganador,
        mis_descartes=tuple(c for c in state.tiradas[asiento] if c in state.baraja.descartes),
        corrida=state.corrida,
    )
