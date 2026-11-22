"""La base de datos sigue funcionando después de un error a mitad de una transacción."""

import sqlite3
import threading

import pytest

from musst.persistence.db import Repository


def test_un_usuario_repetido_no_bloquea_la_base_de_datos(tmp_path) -> None:
    # En un archivo (como en el servidor): antes, la transacción del INSERT fallido se quedaba
    # abierta y la siguiente escritura desde otro hilo esperaba hasta «database is locked».
    repo = Repository(tmp_path / "musst.sqlite3")
    repo.create_user("alice", "contraseña-larga")
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_user("alice", "otra-contraseña")

    errores: list[BaseException] = []

    def registrar_otro() -> None:
        try:
            repo.create_user("bob", "contraseña-larga")
        except BaseException as exc:  # pragma: no cover - solo si falla el test
            errores.append(exc)

    hilo = threading.Thread(target=registrar_otro)
    hilo.start()
    hilo.join(timeout=10)
    assert not errores, errores
    assert repo.user_by_name("bob") is not None
