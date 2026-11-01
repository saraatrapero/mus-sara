"""Evaluación de manos: grande, chica, pares, juego y punto.

Cada lance tiene una función ``clave_*`` que convierte una mano de 4 cartas en una tupla
comparable: **la clave mayor gana**. Así todas las comparaciones se hacen igual y los empates se
deshacen en un único sitio (:func:`ganador`), a favor del jugador más cercano a la mano.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from enum import Enum, IntEnum

from musst.compat.musarena.cards import Carta

Mano = Sequence[Carta]


class Lance(Enum):
    """Los lances de una mano, en el orden en que se juegan."""

    GRANDE = "grande"
    CHICA = "chica"
    PARES = "pares"
    JUEGO = "juego"
    PUNTO = "punto"

    def __str__(self) -> str:
        return self.value.capitalize()


class TipoPares(IntEnum):
    """Jugadas de pares. Su valor numérico es también lo que cobran en el recuento."""

    NADA = 0
    PAR = 1
    MEDIAS = 2
    DUPLES = 3

    def __str__(self) -> str:
        return {0: "sin pares", 1: "par", 2: "medias", 3: "duples"}[self.value]


#: Orden del juego de mejor a peor (38 y 39 no se pueden formar).
ORDEN_JUEGO: tuple[int, ...] = (31, 32, 40, 37, 36, 35, 34, 33)


def rangos(mano: Mano) -> list[int]:
    """Rangos de las cartas a 8 reyes (el 3 es rey y el 2 es as)."""
    return [c.rango for c in mano]


# --- Grande y chica -------------------------------------------------------------------------


def clave_grande(mano: Mano) -> tuple[int, ...]:
    """Cartas de mayor a menor: se comparan una a una."""
    return tuple(sorted(rangos(mano), reverse=True))


def clave_chica(mano: Mano) -> tuple[int, ...]:
    """Cartas de menor a mayor con el signo cambiado: la mano más baja da la clave mayor."""
    return tuple(-r for r in sorted(rangos(mano)))


# --- Pares ----------------------------------------------------------------------------------


def tipo_pares(mano: Mano) -> TipoPares:
    """Par (2 iguales), medias (3 iguales) o duples (dos pares o 4 iguales)."""
    cuentas = sorted(Counter(rangos(mano)).values(), reverse=True)
    if cuentas[0] == 4 or cuentas[:2] == [2, 2]:
        return TipoPares.DUPLES
    if cuentas[0] == 3:
        return TipoPares.MEDIAS
    if cuentas[0] == 2:
        return TipoPares.PAR
    return TipoPares.NADA


def tiene_pares(mano: Mano) -> bool:
    return tipo_pares(mano) is not TipoPares.NADA


def clave_pares(mano: Mano) -> tuple[int, ...]:
    """(tipo, rangos de las cartas emparejadas de mayor a menor). Sin pares: ``(0,)``."""
    tipo = tipo_pares(mano)
    cuentas = Counter(rangos(mano))
    if tipo is TipoPares.NADA:
        return (0,)
    if tipo is TipoPares.DUPLES:
        if len(cuentas) == 1:  # cuatro iguales: dos pares del mismo rango
            r = next(iter(cuentas))
            return (tipo, r, r)
        altos = sorted((r for r, n in cuentas.items() if n == 2), reverse=True)
        return (tipo, *altos)
    repetida = max(r for r, n in cuentas.items() if n >= 2)
    return (tipo, repetida)


# --- Juego y punto --------------------------------------------------------------------------


def puntos(mano: Mano) -> int:
    """Suma de los valores de juego de la mano."""
    return sum(c.valor_juego for c in mano)


def tiene_juego(mano: Mano) -> bool:
    return puntos(mano) >= 31


def clave_juego(mano: Mano) -> tuple[int, ...]:
    """Posición en :data:`ORDEN_JUEGO` (31 es la mejor). Sin juego: ``(0,)``."""
    p = puntos(mano)
    if p < 31:
        return (0,)
    return (len(ORDEN_JUEGO) - ORDEN_JUEGO.index(p),)


def clave_punto(mano: Mano) -> tuple[int, ...]:
    """Cuanto más cerca de 30, mejor (sin juego nunca se pasa de 30)."""
    return (puntos(mano),)


def bonus_juego(mano: Mano) -> int:
    """Lo que cobra un juego en el recuento: 3 la treinta y una, 2 cualquier otro."""
    if not tiene_juego(mano):
        return 0
    return 3 if puntos(mano) == 31 else 2


# --- Comparación ----------------------------------------------------------------------------

_CLAVES = {
    Lance.GRANDE: clave_grande,
    Lance.CHICA: clave_chica,
    Lance.PARES: clave_pares,
    Lance.JUEGO: clave_juego,
    Lance.PUNTO: clave_punto,
}


def clave(lance: Lance, mano: Mano) -> tuple[int, ...]:
    """Clave de comparación de una mano en un lance (mayor es mejor)."""
    return _CLAVES[lance](mano)


def orden_desde_mano(mano: int) -> list[int]:
    """Asientos en orden de palabra empezando por la mano."""
    return [(mano + i) % 4 for i in range(4)]


def ganador(
    lance: Lance,
    manos: Mapping[int, Mano],
    mano: int,
) -> int:
    """Asiento que gana ``lance`` entre los asientos de ``manos``.

    En caso de empate gana el más cercano a la mano: se recorren los asientos en orden de palabra
    y solo se sustituye al mejor provisional si la nueva mano es **estrictamente** mejor.
    """
    mejor: int | None = None
    mejor_clave: tuple[int, ...] = ()
    for asiento in orden_desde_mano(mano):
        if asiento not in manos:
            continue
        k = clave(lance, manos[asiento])
        if mejor is None or k > mejor_clave:
            mejor, mejor_clave = asiento, k
    if mejor is None:
        raise ValueError("No hay manos que comparar")
    return mejor
