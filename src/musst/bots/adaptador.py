"""Adaptador entre las dos APIs de bots: ``musarena.Player`` ↔ ``musst.Bot``.

Los bots ``basico``, ``reglas`` e ``inteligente`` vienen del repo hermano
https://github.com/mus-cunef/mus (paquete ``musarena``), cuya API es::

    Player.choose_action(observation_musarena, legal_actions) -> Action_musarena

MUS.ST usa ``Bot.decide(observation) -> Action``. :class:`PlayerComoBot` envuelve un ``Player``
para que juegue sobre el motor FEM de MUS.ST sin reescribirlo. En cada decisión:

1. :func:`traducir_observacion` construye la ``Observation`` de musarena **solo** a partir de la
   observación de MUS.ST (nunca del estado del motor), así que no hay fuga de información.
2. :func:`acciones_legales` convierte las ``ActionSpec`` legales en la lista de acciones de
   musarena, recortando las cantidades a lo que admiten los dos reglamentos.
3. El ``Player`` elige y :func:`a_musst` traduce su acción de vuelta. Si devuelve algo que no
   estaba en la lista, se lanza :class:`AccionNoTraducible`: el runner lo cuenta como fallo del
   bot y su pareja pierde la partida, sin romper el torneo.

Diferencias de reglamento y cómo se resuelven (ver ``docs/bots-cunef.md``):

* **Vacas**: musarena juega a vacas de 40; MUS.ST, una partida a ``target``. Se le dice al bot
  que se juega a una vaca y los tantos se escalan a 40.
* **Mano corrida**: no existe en FEM; siempre ``corrida=False``.
* **Topes**: en musarena una apuesta no pasa de 40; aquí el tope es ``max_bet``. Al bot solo se
  le ofrecen las cantidades válidas en ambos.
* **Quiero y no pierdo** (FEM VI.9) no existe en musarena: si es la única forma de querer, su
  ``Quiero`` se traduce a ella.
* **Señas**: los bots de musarena no las hacen ni las ven.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from itertools import combinations
from typing import Any

from musst.bots.api import (
    AcceptAction,
    AcceptNoLoseAction,
    Action,
    BetAction,
    Bot,
    Card,
    CutMusAction,
    DiscardAction,
    GameEndInfo,
    GameStartInfo,
    MusAction,
    Observation,
    OrdagoAction,
    PassAction,
    RaiseAction,
    RejectAction,
    Suit,
)
from musst.compat.musarena import actions as ma
from musst.compat.musarena.cards import Carta, Palo, ordenar_cartas
from musst.compat.musarena.chat import CanalChat, Chat
from musst.compat.musarena.hands import Lance
from musst.compat.musarena.observation import ApuestaPublica
from musst.compat.musarena.observation import Observation as ObsMusarena
from musst.compat.musarena.player import Player
from musst.compat.musarena.state import (
    TANTOS_VACA,
    Cobro,
    Evento,
    Fase,
    ResultadoLance,
    ResumenMano,
    TipoResultado,
    nombre_jugador,
    nombre_pareja,
)

# ----------------------------------------------------------------------------- cartas

_PALO = {
    Suit.OROS: Palo.OROS,
    Suit.COPAS: Palo.COPAS,
    Suit.ESPADAS: Palo.ESPADAS,
    Suit.BASTOS: Palo.BASTOS,
}
_SUIT = {v: k for k, v in _PALO.items()}


def a_carta(card: Card) -> Carta:
    return Carta(card.rank, _PALO[card.suit])


def a_card(carta: Carta) -> Card:
    return Card(carta.numero, _SUIT[carta.palo])


def _cartas(codes: Sequence[str] | Sequence[Card]) -> tuple[Carta, ...]:
    """Mano de musarena (ordenada de mayor a menor, como la espera el bot)."""
    cards = [Card.parse(c) if isinstance(c, str) else c for c in codes]
    return tuple(ordenar_cartas([a_carta(c) for c in cards]))


# ----------------------------------------------------------------------------- acciones

_LANCES = ("grande", "chica", "pares", "juego", "punto")


def acciones_legales(obs: Observation) -> list[ma.Action]:
    """Acciones de musarena equivalentes a las ``ActionSpec`` legales de ``obs``."""
    legales: list[ma.Action] = []
    stake = obs.current_bet.stake if obs.current_bet else 0
    for spec in obs.legal_actions:
        lo, hi = spec.min_amount or 0, spec.max_amount or 0
        if spec.type == "mus":
            legales.append(ma.Mus())
        elif spec.type == "cut":
            legales.append(ma.NoHayMus())
        elif spec.type == "discard":
            mano = _cartas(obs.hand)
            for n in range(max(1, lo), min(4, hi) + 1):
                legales += [ma.Descarte(frozenset(c)) for c in combinations(mano, n)]
        elif spec.type == "pass":
            legales.append(ma.Paso())
        elif spec.type == "bet":
            # musarena: "Envido" = 2 y "Envido N" con N de 3 a 40.
            tope = min(hi, ma.ENVIDO_MAX)
            if lo <= ma.ENVIDO_POR_DEFECTO <= tope:
                legales.append(ma.Envido())
            legales += [ma.Envido(n) for n in range(max(lo, ma.ENVIDO_MIN), tope + 1)]
        elif spec.type == "raise":
            # musarena: subida de al menos 2 y el total no pasa de 40.
            tope = min(hi, ma.APUESTA_MAX - stake)
            legales += [ma.Reenvido(n) for n in range(max(lo, ma.REENVIDO_MIN), tope + 1)]
        elif spec.type == "ordago":
            legales.append(ma.Ordago())
        elif spec.type in ("accept", "accept_no_lose"):
            legales.append(ma.Quiero())
        elif spec.type == "reject":
            legales.append(ma.NoQuiero())
    return legales


class AccionNoTraducible(ValueError):
    """El bot de musarena devolvió una acción que no estaba en su lista de legales."""


def a_musst(accion: ma.Action, obs: Observation) -> Action:
    """Traduce la acción elegida por el bot de musarena a una acción de MUS.ST."""
    tipos = obs.legal_types()
    if isinstance(accion, ma.Mus):
        return MusAction()
    if isinstance(accion, ma.NoHayMus):
        return CutMusAction()
    if isinstance(accion, ma.Descarte):
        return DiscardAction(tuple(a_card(c) for c in accion.cartas))
    if isinstance(accion, ma.Paso):
        return PassAction()
    if isinstance(accion, ma.Envido):
        return BetAction(accion.tantos)
    if isinstance(accion, ma.Reenvido):
        return RaiseAction(accion.tantos)
    if isinstance(accion, ma.Ordago):
        return OrdagoAction()
    if isinstance(accion, ma.Quiero):
        return AcceptAction() if "accept" in tipos else AcceptNoLoseAction()
    if isinstance(accion, ma.NoQuiero):
        return RejectAction()
    raise AccionNoTraducible(f"Acción desconocida: {accion!r}")


# ----------------------------------------------------------------------------- historial

_ACCION_DE: dict[str, Callable[[dict[str, Any]], ma.Action]] = {
    "MusRequested": lambda p: ma.Mus(),
    "MusCut": lambda p: ma.NoHayMus(),
    "Passed": lambda p: ma.Paso(),
    "BetPlaced": lambda p: ma.Envido(min(p["amount"], ma.ENVIDO_MAX)),
    "BetRaised": lambda p: ma.Reenvido(min(p["amount"], ma.REENVIDO_MAX)),
    "OrdagoDeclared": lambda p: ma.Ordago(),
    "BetAccepted": lambda p: ma.Quiero(),
    "OrdagoAccepted": lambda p: ma.Quiero(),
    "BetRejected": lambda p: ma.NoQuiero(),
}


def _evento(e: dict[str, Any], mano: int) -> Evento | None:
    """Un evento público de MUS.ST como ``Evento`` de musarena (con el texto que espera)."""
    kind, actor, p = e["kind"], e.get("actor"), e.get("payload", {})
    lance = Lance(p["lance"]) if p.get("lance") in _LANCES else None
    if kind in _ACCION_DE:
        accion = _ACCION_DE[kind](p)
        return Evento(actor, str(accion), accion, lance)
    if kind == "DealerAssigned":
        return Evento(None, f"Mano {e['round']}: es mano el {nombre_jugador(p['mano'])}")
    if kind == "CardsDiscarded" and "count" in p:  # el evento privado (con cartas) se ignora
        n = p["count"]
        return Evento(actor, f"Se descarta de {n} carta{'s' if n > 1 else ''}")
    if kind in ("PairsDeclared", "GameDeclared"):
        lance = Lance.PARES if kind == "PairsDeclared" else Lance.JUEGO
        return Evento(actor, f"{lance}: {'sí' if p['has'] else 'no'}", lance=lance)
    if kind == "LanceStarted" and p.get("betting"):
        return Evento(None, f"Se juega a {lance}", lance=lance)
    if kind == "PointsAwarded":
        return Evento(
            None,
            f"Pareja {nombre_pareja(p['team'])} cobra {p['points']} ({lance}: {p['concept']})",
            lance=lance,
        )
    return None


def _cobro(e: dict[str, Any]) -> Cobro:
    p = e["payload"]
    return Cobro(
        p["team"],
        p["points"],
        Lance(p["lance"]) if p.get("lance") in _LANCES else None,
        p["concept"],
    )


# ----------------------------------------------------------------------------- observación

_FASE = {"mus": Fase.MUS, "discard": Fase.DESCARTE, "game_over": Fase.FIN}
_TIPO = {
    "passed": TipoResultado.EN_PASO,
    "accepted": TipoResultado.QUERIDO,
    "rejected": TipoResultado.NO_QUERIDO,
    "no_bet": TipoResultado.SIN_APUESTA,
}


def _a_40(puntos: int, objetivo: int) -> int:
    """Tantos en la escala de una vaca de 40 (la que entiende la estrategia de musarena)."""
    return min(TANTOS_VACA - 1, round(puntos * TANTOS_VACA / objetivo)) if objetivo else puntos


def _orden(mano: int) -> tuple[int, ...]:
    return tuple((mano + i) % 4 for i in range(4))


def _resultados(
    eventos: list[dict[str, Any]], statuses: dict[str, str]
) -> tuple[ResultadoLance, ...]:
    """Cómo han terminado los lances ya jugados de la jugada en curso."""
    salida = []
    for e in eventos:
        if e["kind"] != "LanceStarted":
            continue
        p = e["payload"]
        nombre = p["lance"]
        tipo = _TIPO.get(statuses.get(nombre, ""))
        if tipo is None:  # lance en curso o sin cerrar
            continue
        if not p.get("betting"):
            tipo = TipoResultado.SIN_APUESTA
        apuesta, pareja = 0, None
        if tipo is TipoResultado.QUERIDO:
            apuesta = next(
                (
                    x["payload"]["amount"]
                    for x in reversed(eventos)
                    if x["kind"] == "BetAccepted" and x["payload"]["lance"] == nombre
                ),
                0,
            )
        if tipo is TipoResultado.NO_QUERIDO:
            apostador = next(
                x["actor"]
                for x in reversed(eventos)
                if x["kind"] in ("BetPlaced", "BetRaised", "OrdagoDeclared")
                and x["payload"]["lance"] == nombre
            )
            pareja = apostador % 2
        salida.append(
            ResultadoLance(
                Lance(nombre), tipo, tuple(p["participants"]), apuesta=apuesta, pareja=pareja
            )
        )
    return tuple(salida)


def _apuesta(obs: Observation) -> ApuestaPublica | None:
    if obs.phase not in _LANCES or obs.turn is None:
        return None
    participantes = tuple(obs.lance_participants)
    bet = obs.current_bet
    if bet is None:
        i = participantes.index(obs.turn) if obs.turn in participantes else 0
        return ApuestaPublica(participantes, participantes[i:], 0, 1, None, False)
    return ApuestaPublica(
        participantes,
        tuple(bet.responders),
        bet.stake,
        max(1, bet.previous),
        bet.bettor_team,
        bet.is_ordago,
    )


def _mano_de(eventos: list[dict[str, Any]], defecto: int) -> int:
    for e in eventos:
        if e["kind"] == "DealerAssigned":
            return int(e["payload"]["mano"])
        if e["kind"] == "LanceStarted":
            return int(e["payload"].get("lance_mano", defecto))
    return defecto


def _mis_descartes(obs: Observation, actuales: list[dict[str, Any]]) -> tuple[Carta, ...]:
    """Cartas que he tirado en esta jugada y siguen en la pila (si se rebarajan, vuelven al mazo).

    Salen del evento privado ``CardsDiscarded`` que solo ve quien se descarta.
    """
    tiradas: list[Carta] = []
    for e in actuales:
        if e["kind"] == "DeckReshuffled":
            tiradas = []
        elif (
            e["kind"] == "CardsDiscarded" and e.get("actor") == obs.seat and "cards" in e["payload"]
        ):
            tiradas += [a_carta(Card.parse(c)) for c in e["payload"]["cards"]]
    return tuple(tiradas)


def traducir_observacion(obs: Observation) -> ObsMusarena:
    """La ``Observation`` de musarena equivalente a ``obs`` (solo información pública y propia)."""
    por_jugada: dict[int, list[dict[str, Any]]] = {}
    for e in obs.history:
        por_jugada.setdefault(e["round"], []).append(e)
    actuales = por_jugada.get(obs.round_no, [])

    # Jugadas ya terminadas: las cartas se enseñan al final (HandsRevealed).
    manos_jugadas = []
    for n in sorted(r for r in por_jugada if r < obs.round_no):
        ev = por_jugada[n]
        manos = next((e["payload"]["hands"] for e in ev if e["kind"] == "HandsRevealed"), None)
        if manos is None:
            continue
        mano = _mano_de(ev, 0)
        fin = next((e["payload"]["score"] for e in ev if e["kind"] == "RoundFinished"), [0, 0])
        manos_jugadas.append(
            ResumenMano(
                numero=n,
                mano=mano,
                cartas=tuple(_cartas(manos[str(s)]) for s in range(4)),
                cobros=tuple(_cobro(e) for e in ev if e["kind"] == "PointsAwarded"),
                tantos=(_a_40(fin[0], obs.target), _a_40(fin[1], obs.target)),
                ganador_vaca=None,
                historial=tuple(x for x in (_evento(e, mano) for e in ev) if x is not None),
            )
        )

    declaraciones = tuple(
        (Lance(k), (bool(d[0]), bool(d[1]), bool(d[2]), bool(d[3])))
        for k, d in obs.declarations.items()
        if len(d) == 4 and k in ("pares", "juego")
    )
    lance = Lance(obs.phase) if obs.phase in _LANCES else None
    return ObsMusarena(
        asiento=obs.seat,
        cartas=_cartas(obs.hand),
        fase=_FASE.get(obs.phase, Fase.LANCE),
        turno=obs.turn,
        mano=obs.mano,
        numero_mano=obs.round_no,
        lance=lance,
        apuesta=_apuesta(obs),
        tantos=(_a_40(obs.score[0], obs.target), _a_40(obs.score[1], obs.target)),
        vacas=(0, 0),
        vacas_para_ganar=1,
        declaraciones=declaraciones,
        resultados=_resultados(actuales, obs.lance_statuses),
        cobros=tuple(_cobro(e) for e in actuales if e["kind"] == "PointsAwarded"),
        historial=tuple(x for x in (_evento(e, obs.mano) for e in actuales) if x is not None),
        manos_jugadas=tuple(manos_jugadas),
        chat=(),
        ganador=obs.winner,
        mis_descartes=_mis_descartes(obs, actuales),
        corrida=False,
    )


# ----------------------------------------------------------------------------- el bot


class PlayerComoBot(Bot):
    """Un ``Player`` de musarena jugando como ``Bot`` de MUS.ST."""

    def __init__(self, player: Player, name: str | None = None, author: str = "mus-cunef") -> None:
        self.player = player
        self.name = name or str(getattr(player, "tipo", type(player).__name__))
        self.author = author
        self._avisadas = 0  # jugadas ya comunicadas con ``on_hand_end``

    def on_game_start(self, info: GameStartInfo) -> None:
        self.player.sit(info.seat, CanalChat(Chat(), info.seat))

    def decide(self, observation: Observation) -> Action:
        mobs = traducir_observacion(observation)
        while self._avisadas < len(mobs.manos_jugadas):  # aviso de las jugadas terminadas
            self._avisadas += 1
            self.player.on_hand_end(mobs)
        legales = acciones_legales(observation)
        accion = self.player.choose_action(mobs, legales)
        if accion not in legales:
            raise AccionNoTraducible(f"{self.name} eligió {accion}, que no es legal")
        return a_musst(accion, observation)

    def on_game_end(self, info: GameEndInfo) -> None:
        pass  # el Player de musarena recibe on_game_end con su observación, que aquí no hay
