"""Chat abierto de la mesa: cualquiera escribe y todos leen.

El chat vive **fuera** del estado del juego (lo guarda :class:`musst.compat.musarena.match.Match`), así que
escribir no altera la partida ni gasta el turno.
"""

from __future__ import annotations

from dataclasses import dataclass

from musst.compat.musarena.state import nombre_jugador

#: Longitud máxima de un mensaje, para que nadie pueda llenar la mesa de texto.
LONGITUD_MAXIMA = 500


@dataclass(frozen=True)
class MensajeChat:
    numero: int
    asiento: int
    texto: str
    numero_mano: int

    def __str__(self) -> str:
        return f"[{nombre_jugador(self.asiento)}] {self.texto}"


class Chat:
    """Registro de mensajes de una mesa."""

    def __init__(self) -> None:
        self._mensajes: list[MensajeChat] = []
        self.numero_mano = 1

    def escribir(self, asiento: int, texto: str) -> MensajeChat | None:
        """Añade un mensaje. Los mensajes vacíos se ignoran y los largos se recortan."""
        if asiento not in range(4):
            raise ValueError(f"Asiento no válido: {asiento}")
        texto = str(texto).strip()[:LONGITUD_MAXIMA]
        if not texto:
            return None
        mensaje = MensajeChat(len(self._mensajes), asiento, texto, self.numero_mano)
        self._mensajes.append(mensaje)
        return mensaje

    @property
    def mensajes(self) -> tuple[MensajeChat, ...]:
        return tuple(self._mensajes)


class CanalChat:
    """Lo que recibe cada jugador: puede escribir **solo con su asiento** y leer todo."""

    def __init__(self, chat: Chat, asiento: int) -> None:
        self._chat = chat
        self.asiento = asiento

    def escribir(self, texto: str) -> None:
        self._chat.escribir(self.asiento, texto)

    @property
    def mensajes(self) -> tuple[MensajeChat, ...]:
        return self._chat.mensajes
