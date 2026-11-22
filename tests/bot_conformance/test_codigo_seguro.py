"""Filtro estático del código de los bots de ``bots/`` (análisis del AST, no un grep).

Se ejecuta en la CI de cada PR (no solo cuando cambia ``bots/**``). Un bot solo puede importar
una lista cerrada de módulos: la biblioteca estándar «de cálculo» y el API público de
``musst``. Se rechazan además las funciones que ejecutan código o abren ficheros y los
atributos «privados» que permiten saltarse la ``Observation`` (``__dict__``, ``f_back``…).

No es un sandbox perfecto (Python no lo permite dentro del lenguaje): es la primera barrera,
y la segunda es revisar el código en la PR.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RAIZ_BOTS = Path(__file__).resolve().parents[2] / "bots"
BOTS = sorted(p for p in RAIZ_BOTS.iterdir() if p.is_dir() and any(p.rglob("*.py")))

#: Módulos que un bot no necesita y que le permitirían salir de su Observation.
MODULOS_PROHIBIDOS = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "shutil",
    "ctypes",
    "importlib",
    "multiprocessing",
    "threading",
    "pickle",
    "marshal",
    "builtins",
    "io",
    "pathlib",
    "urllib",
    "http",
    "requests",
    "inspect",
    "gc",
    "posix",
    "nt",
    "signal",
    "resource",
}

#: Biblioteca estándar (y numpy) que sí se puede importar: solo cálculo, nada de E/S.
MODULOS_PERMITIDOS = {
    "random",
    "math",
    "statistics",
    "itertools",
    "functools",
    "collections",
    "dataclasses",
    "typing",
    "enum",
    "heapq",
    "bisect",
    "copy",
    "__future__",
    "abc",
    "numpy",
}

#: Partes de ``musst`` que un bot puede usar: el API público y funciones puras de cartas y
#: evaluación de manos. ``musst.engine.game`` o ``musst.bots.sandbox`` quedan fuera: con ellos
#: un bot podría rehacer la partida con la semilla y ver las cartas ajenas.
MUSST_PERMITIDOS = {
    "musst.bots.api",
    "musst.bots.toolkit",
    "musst.engine.evaluation",
    "musst.engine.cards",
    "musst.engine.config",
}

#: Funciones que ejecutan código, abren ficheros o dan acceso a los espacios de nombres.
FUNCIONES_PROHIBIDAS = {
    "eval",
    "exec",
    "compile",
    "open",
    "__import__",
    "globals",
    "locals",
    "vars",
    "breakpoint",
    "__builtins__",
}

#: Funciones de atributos que solo se permiten con un nombre literal y público.
FUNCIONES_DE_ATRIBUTOS = {"getattr", "setattr", "delattr", "hasattr"}

#: Atributos de introspección que no empiezan por ``__`` pero abren el intérprete.
ATRIBUTOS_PROHIBIDOS = {"f_locals", "f_globals", "f_back", "f_builtins", "_getframe", "gi_frame"}


def _modulo_permitido(nombre: str) -> bool:
    """Si se puede importar ``nombre`` (con puntos: ``collections.abc``, ``musst.bots.api``)."""
    raiz = nombre.split(".")[0]
    if raiz in MODULOS_PROHIBIDOS:
        return False
    if raiz == "musst":
        return nombre in MUSST_PERMITIDOS
    return raiz in MODULOS_PERMITIDOS


def usos_prohibidos(codigo: str) -> list[str]:
    """Lista de lo que el código usa y un bot no debería usar (vacía si está limpio)."""
    malos: list[str] = []
    for nodo in ast.walk(ast.parse(codigo)):
        if isinstance(nodo, ast.Import):
            malos += [f"import {a.name}" for a in nodo.names if not _modulo_permitido(a.name)]
        elif isinstance(nodo, ast.ImportFrom):
            modulo = nodo.module or ""
            if nodo.level:
                malos.append(f"import relativo desde {'.' * nodo.level}{modulo}")
            elif modulo == "musst.engine" or modulo == "musst.bots" or modulo == "musst":
                # «from musst.engine import evaluation»: lo que cuenta es el submódulo.
                malos += [
                    f"import {modulo}.{a.name}"
                    for a in nodo.names
                    if not _modulo_permitido(f"{modulo}.{a.name}")
                ]
            elif not _modulo_permitido(modulo):
                malos.append(f"import {modulo}")
        elif isinstance(nodo, ast.Name) and nodo.id in FUNCIONES_PROHIBIDAS:
            malos.append(nodo.id)
        elif isinstance(nodo, ast.Name) and nodo.id in MODULOS_PROHIBIDOS:
            # Usar el nombre de un módulo prohibido sin importarlo (llegaría por otra vía).
            malos.append(f"uso de {nodo.id}")
        elif isinstance(nodo, ast.Attribute):
            if nodo.attr.startswith("__") or nodo.attr in ATRIBUTOS_PROHIBIDOS:
                malos.append(f".{nodo.attr}")
        elif (
            isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Name)
            and nodo.func.id in FUNCIONES_DE_ATRIBUTOS
            and len(nodo.args) > 1
        ):
            nombre = nodo.args[1]
            if not (isinstance(nombre, ast.Constant) and isinstance(nombre.value, str)):
                malos.append(f"{nodo.func.id} con un nombre calculado")
            elif nombre.value.startswith("_"):
                malos.append(f"{nodo.func.id} con un nombre privado")
    return malos


@pytest.mark.parametrize("bot", BOTS, ids=[b.name for b in BOTS])
def test_el_bot_no_usa_nada_peligroso(bot: Path) -> None:
    for fichero in sorted(bot.rglob("*.py")):
        malos = usos_prohibidos(fichero.read_text(encoding="utf-8"))
        assert not malos, f"{fichero} usa cosas que un bot no necesita: {', '.join(malos)}"


TRUCOS = [
    "import  os",
    "import json, os",
    "from os import path",
    "import os.path",
    "import sys; sys.modules['os']",
    "importlib.import_module('o'+'s')",
    "getattr(__builtins__, '__imp'+'ort__')",
    "eval ('1')",
    "open ('x')",
    "import pathlib",
    "import io",
    "from musst.engine.game import MusGame",
    "from musst.engine import game",
    "from musst.bots import sandbox",
    "import musst.bots.sandbox",
    "import inspect",
    "x.__dict__",
    "f.__globals__",
    "().__class__.__base__.__subclasses__()",
    "marco.f_back.f_locals",
    "getattr(o, nombre)",
    "getattr(o, '_privado')",
    "from . import vecino",
    "exec('x = 1')",
    "compile('1', 'x', 'eval')",
    "vars(o)",
]


@pytest.mark.parametrize("truco", TRUCOS)
def test_el_filtro_detecta_los_trucos(truco: str) -> None:
    assert usos_prohibidos(truco), f"El filtro no detecta: {truco!r}"


def test_el_codigo_legitimo_pasa() -> None:
    codigo = """
from __future__ import annotations
import math
import random
from collections import Counter
from collections.abc import Sequence
from musst.bots.api import Bot
from musst.bots.toolkit import hand_value
from musst.engine import evaluation as ev
from musst.engine.cards import full_deck


class MiBot(Bot):
    def __init__(self) -> None:
        self.rng = random.Random(1)

    def decidir(self, obs, legales: Sequence) -> object:
        valor = getattr(obs, "mano", None)
        return max(legales, key=lambda a: math.log(1 + len(str(a)))) if valor else legales[0]
"""
    assert usos_prohibidos(codigo) == []
