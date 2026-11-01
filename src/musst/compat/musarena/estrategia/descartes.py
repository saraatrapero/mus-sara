"""Qué dice de una mano el número de cartas que se descartó su dueño.

Después de un descarte las manos **no son manos al azar**: cada jugador tira lo que no le sirve
y se queda lo bueno. Quien se descarta de una carta casi siempre lleva pares o juego; quien se
descarta de cuatro, una mano floja que ha vuelto a probar suerte.

Calcularlo de forma exacta exigiría saber cómo descarta cada jugador, así que lo **medimos**:
se juegan muchas partidas entre bots ``reglas`` y se cuenta qué tipo de mano tiene cada jugador
justo después de descartarse de ``n`` cartas. De ahí sale, para cada ``n`` y cada uno de los
330 tipos de mano, un **factor**:

    factor[n][tipo] = P(tipo | se descartó de n) / P(tipo en una mano al azar)

Las creencias (:mod:`~musst.compat.musarena.estrategia.creencias`) multiplican por este factor, igual que
hacen con la verosimilitud de un envite (regla de Bayes). La tabla viaja con el paquete
(``tras_descarte.npz``) y se regenera con::

    python -m musst.compat.musarena.estrategia.descartes --partidas 20000
"""

from __future__ import annotations

import argparse
import os
import random
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from musst.compat.musarena.estrategia.tipos import N_TIPOS, PESOS_BASE, indice_de

#: Archivo con la tabla medida.
RUTA = Path(__file__).with_name("tras_descarte.npz")

#: Estilos que juegan las partidas de las que se mide la tabla.
JUGADORES: tuple[str, ...] = ("reglas", "reglas:agresivo", "reglas:conservador")


def contar(args: tuple[int, int]) -> np.ndarray:
    """Cuántas veces queda cada tipo de mano tras descartarse de n cartas (matriz 5 x 330)."""
    from musst.compat.musarena.match import Match
    from musst.compat.musarena.players import crear_jugador
    from musst.compat.musarena.state import Fase

    partidas, seed = args
    rng = random.Random(seed)
    cuentas = np.zeros((5, N_TIPOS))
    for _ in range(partidas):
        mesa = [crear_jugador(rng.choice(JUGADORES), seed=rng.randrange(2**32)) for _ in range(4)]
        match = Match(mesa, seed=rng.randrange(2**32))
        while not match.terminada:
            s = match.state
            if s.fase is Fase.DESCARTE:
                asiento, antes = s.turno, len(s.historial)
                match.step()
                evento = match.state.historial[antes] if len(match.state.historial) > antes \
                    else None
                if evento is not None and evento.texto.startswith("Se descarta"):
                    n = int(evento.texto.split()[3])
                    cuentas[n, indice_de(match.state.cartas[asiento])] += 1
            else:
                match.step()
    return cuentas


def factores(cuentas: np.ndarray, suavizado: float = 100.0) -> np.ndarray:
    """Factor de cada tipo para cada n, a partir de las cuentas.

    Se suaviza hacia la mano al azar con ``suavizado`` observaciones ficticias, para que los
    tipos que casi no aparecen no den factores extremos.
    """
    base = PESOS_BASE / PESOS_BASE.sum()
    resultado = np.ones((5, N_TIPOS))
    for n in range(1, 5):
        total = cuentas[n].sum()
        p = (cuentas[n] + suavizado * base) / (total + suavizado)
        resultado[n] = p / base
    return resultado


def _cargar() -> np.ndarray:
    if not RUTA.exists():  # sin tabla medida: el descarte no aporta información
        tabla = np.ones((5, N_TIPOS))
    else:
        with np.load(RUTA) as datos:
            tabla = datos["factor"].astype(float)
    tabla.setflags(write=False)
    return tabla


#: ``FACTOR_DESCARTE[n][tipo]``: cuánto más (o menos) probable es cada tipo tras descartarse
#: de ``n`` cartas (la fila 0 son unos).
FACTOR_DESCARTE: np.ndarray = _cargar()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mide cómo quedan las manos tras descartarse.")
    parser.add_argument("--partidas", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--salida", default=str(RUTA))
    args = parser.parse_args(argv)
    procesos = os.cpu_count() or 1
    trozos = procesos * 4
    tareas = [(args.partidas // trozos + (i < args.partidas % trozos), args.seed * 7919 + i)
              for i in range(trozos)]
    with ProcessPoolExecutor(procesos) as ex:
        cuentas = sum(ex.map(contar, tareas))
    np.savez_compressed(args.salida, factor=factores(cuentas).astype(np.float32),
                        cuentas=cuentas.astype(np.int32))
    for n in range(1, 5):
        print(f"descarte de {n}: {int(cuentas[n].sum())} casos")
    print(f"tabla guardada en {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
