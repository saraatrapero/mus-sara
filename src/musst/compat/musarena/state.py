"""Estado completo de la partida: mano en curso, marcador de la vaca y vacas ganadas.

El estado contiene información oculta (las cartas de todos, el orden del mazo, el generador
aleatorio), así que **nunca se entrega a un jugador**: los jugadores reciben una
:class:`musst.compat.musarena.observation.Observation`.

El motor trata el estado como un valor: :func:`musst.compat.musarena.engine.apply` hace una copia con
:meth:`State.copiar` y modifica solo la copia, de modo que el estado original nunca cambia.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

from musst.compat.musarena.actions import Action
from musst.compat.musarena.cards import Baraja, Carta
from musst.compat.musarena.hands import Lance

#: Tantos necesarios para ganar una vaca.
TANTOS_VACA = 40

#: Lances de una mano en orden de juego (el juego se convierte en punto si nadie tiene juego).
LANCES = (Lance.GRANDE, Lance.CHICA, Lance.PARES, Lance.JUEGO)


def pareja(asiento: int) -> int:
    """Pareja de un asiento: 0 para los asientos 0 y 2, 1 para los asientos 1 y 3."""
    return asiento % 2


def nombre_pareja(p: int) -> str:
    return "A" if p == 0 else "B"


def nombre_jugador(asiento: int) -> str:
    """Nombre que ven las personas: los asientos 0-3 se muestran como Jugador 1-4."""
    return f"Jugador {asiento + 1}"


class Fase(Enum):
    """En qué punto de la mano está la partida."""

    MUS = "mus"
    DESCARTE = "descarte"
    LANCE = "lance"
    FIN = "fin de la partida"


class TipoResultado(Enum):
    """Cómo terminó la parte de apuestas de un lance."""

    EN_PASO = "en paso"  # todos pasaron
    QUERIDO = "querido"  # se aceptó una apuesta
    NO_QUERIDO = "no querido"  # se rechazó una apuesta; ganó la pareja que apostó
    SIN_APUESTA = "sin apuesta"  # en pares/juego, menos de dos parejas con jugada


@dataclass(frozen=True)
class ResultadoLance:
    """Lo que queda pendiente de un lance para el recuento final."""

    lance: Lance
    tipo: TipoResultado
    participantes: tuple[int, ...]
    apuesta: int = 0
    pareja: int | None = None  # pareja ganadora, solo en NO_QUERIDO


@dataclass(frozen=True)
class Evento:
    """Algo público que ha pasado en la mano (lo ven todos los jugadores)."""

    asiento: int | None
    texto: str
    accion: Action | None = None
    lance: Lance | None = None


@dataclass(frozen=True)
class Cobro:
    """Tantos que cobra una pareja, en el momento (no quiero) o en el recuento."""

    pareja: int
    tantos: int
    lance: Lance | None
    motivo: str


@dataclass(frozen=True)
class ResumenMano:
    """Resumen público de una mano terminada, con las cartas de los cuatro jugadores."""

    numero: int
    mano: int
    cartas: tuple[tuple[Carta, ...], ...]
    cobros: tuple[Cobro, ...]
    tantos: tuple[int, int]
    ganador_vaca: int | None
    historial: tuple[Evento, ...] = ()  # todo lo que pasó en la mano (público)


@dataclass
class Apuesta:
    """Estado de las apuestas del lance en curso."""

    participantes: tuple[int, ...]  # asientos que pueden hablar en este lance, desde la mano
    por_hablar: list[int]  # cola de asientos a los que les falta hablar
    tantos: int = 0  # apuesta total sobre la mesa
    deje: int = 1  # lo que cobra la pareja apostadora si le dicen "no quiero"
    pareja_apostadora: int | None = None
    ordago: bool = False

    def copiar(self) -> Apuesta:
        return Apuesta(
            participantes=self.participantes,
            por_hablar=list(self.por_hablar),
            tantos=self.tantos,
            deje=self.deje,
            pareja_apostadora=self.pareja_apostadora,
            ordago=self.ordago,
        )


@dataclass
class State:
    """Estado completo (con información oculta) de una partida de mus."""

    vacas_para_ganar: int
    rng: random.Random
    baraja: Baraja
    mano: int = 0
    corrida: bool = False  # primera mano: la mano se corre hasta que alguien corta
    numero_mano: int = 1
    tantos: list[int] = field(default_factory=lambda: [0, 0])
    vacas: list[int] = field(default_factory=lambda: [0, 0])
    fase: Fase = Fase.MUS
    turno: int | None = None
    cartas: list[list[Carta]] = field(default_factory=lambda: [[], [], [], []])
    mus_pedidos: int = 0
    descartes_hechos: int = 0
    tiradas: list[list[Carta]] = field(default_factory=lambda: [[], [], [], []])  # en la mano
    lances_pendientes: list[Lance] = field(default_factory=list)
    lance: Lance | None = None
    apuesta: Apuesta | None = None
    resultados: list[ResultadoLance] = field(default_factory=list)
    cobros: list[Cobro] = field(default_factory=list)
    declaraciones: dict[Lance, dict[int, bool]] = field(default_factory=dict)
    historial: list[Evento] = field(default_factory=list)
    manos_jugadas: list[ResumenMano] = field(default_factory=list)
    ganador: int | None = None  # pareja que ha ganado la partida

    @property
    def terminada(self) -> bool:
        return self.fase is Fase.FIN

    def copiar(self) -> State:
        """Copia independiente: cambiar la copia no afecta a este estado.

        Los elementos inmutables (cartas, eventos, resúmenes) se comparten; las listas, los
        diccionarios, la baraja y el generador aleatorio se duplican.
        """
        rng = random.Random()
        rng.setstate(self.rng.getstate())
        return State(
            vacas_para_ganar=self.vacas_para_ganar,
            rng=rng,
            baraja=self.baraja.copiar(rng),
            mano=self.mano,
            corrida=self.corrida,
            numero_mano=self.numero_mano,
            tantos=list(self.tantos),
            vacas=list(self.vacas),
            fase=self.fase,
            turno=self.turno,
            cartas=[list(c) for c in self.cartas],
            mus_pedidos=self.mus_pedidos,
            descartes_hechos=self.descartes_hechos,
            tiradas=[list(t) for t in self.tiradas],
            lances_pendientes=list(self.lances_pendientes),
            lance=self.lance,
            apuesta=self.apuesta.copiar() if self.apuesta else None,
            resultados=list(self.resultados),
            cobros=list(self.cobros),
            declaraciones={k: dict(v) for k, v in self.declaraciones.items()},
            historial=list(self.historial),
            manos_jugadas=list(self.manos_jugadas),
            ganador=self.ganador,
        )
