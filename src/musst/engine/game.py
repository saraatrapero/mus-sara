"""Motor de juego: estado, máquina de estados, legalidad y tanteo.

``MusGame`` es la única autoridad sobre una partida. Ninguna acción cambia el estado sin pasar
por :meth:`MusGame.validate`. Las acciones ilegales lanzan :class:`IllegalAction` y no
modifican nada.

Asientos 0-3 en orden de habla (antihorario). Pareja 0 = asientos {0, 2}; pareja 1 = {1, 3}.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from musst.engine import evaluation as ev
from musst.engine.actions import (
    AcceptAction,
    AcceptNoLoseAction,
    Action,
    ActionSpec,
    BetAction,
    CutMusAction,
    DiscardAction,
    MusAction,
    OrdagoAction,
    PassAction,
    RaiseAction,
    RejectAction,
)
from musst.engine.cards import Card, shuffled_deck
from musst.engine.config import RulesConfig
from musst.engine.events import EventKind, GameEvent, Visibility
from musst.engine.signals import Signal, truthful_signals

NUM_SEATS = 4


class Phase(str, Enum):
    MUS = "mus"
    DISCARD = "discard"
    GRANDE = "grande"
    CHICA = "chica"
    PARES = "pares"
    JUEGO = "juego"
    PUNTO = "punto"
    GAME_OVER = "game_over"


LANCES: tuple[Phase, ...] = (Phase.GRANDE, Phase.CHICA, Phase.PARES, Phase.JUEGO, Phase.PUNTO)

ALLOWED_TRANSITIONS: dict[Phase, frozenset[Phase]] = {
    Phase.MUS: frozenset({Phase.DISCARD, Phase.GRANDE}),
    Phase.DISCARD: frozenset({Phase.MUS}),
    Phase.GRANDE: frozenset({Phase.CHICA, Phase.GAME_OVER}),
    Phase.CHICA: frozenset({Phase.PARES, Phase.JUEGO, Phase.PUNTO, Phase.GAME_OVER}),
    Phase.PARES: frozenset({Phase.JUEGO, Phase.PUNTO, Phase.GAME_OVER}),
    Phase.JUEGO: frozenset({Phase.MUS, Phase.GAME_OVER}),
    Phase.PUNTO: frozenset({Phase.MUS, Phase.GAME_OVER}),
    Phase.GAME_OVER: frozenset(),
}
"""Tabla explícita de transiciones de la máquina de estados (ver docs/architecture.md).

CHICA y PARES pueden saltar a JUEGO/PUNTO porque los lances sin envites se resuelven solos;
JUEGO/PUNTO vuelven a MUS al empezar la jugada siguiente.
"""


class IllegalAction(Exception):
    """La acción propuesta no es legal en el estado actual."""


class IllegalTransition(Exception):
    """Error interno: transición no permitida por la máquina de estados."""


def team_of(seat: int) -> int:
    return seat % 2


def partner_of(seat: int) -> int:
    return (seat + 2) % NUM_SEATS


@dataclass
class LanceState:
    """Estado de los envites de un lance."""

    lance: Phase
    participants: list[int]
    has_betting: bool
    status: str = "open"  # open | pending | passed | accepted | rejected | no_bet | ordago
    turn_idx: int = 0
    bettor_team: int | None = None
    stake: int = 0
    previous: int = 0
    is_ordago: bool = False
    responders: list[int] = field(default_factory=list)
    accepted_stake: int = 0

    @property
    def closed(self) -> bool:
        return self.status not in ("open", "pending")


@dataclass
class GameResult:
    winner: int
    score: tuple[int, int]
    reason: str
    rounds: int


class MusGame:
    """Una partida de Mus a ``config.target_points`` tantos."""

    def __init__(self, seed: int | None = None, config: RulesConfig | None = None) -> None:
        self.config = config or RulesConfig()
        self.seed = seed if seed is not None else random.SystemRandom().randrange(2**31)
        self.rng = random.Random(self.seed)
        self.score: list[int] = [0, 0]
        self.events: list[GameEvent] = []
        self.round_no = 0
        self.phase = Phase.MUS
        self.result: GameResult | None = None
        self.hands: list[list[Card]] = [[] for _ in range(NUM_SEATS)]
        self.deck: list[Card] = []
        self.discard_pile: list[Card] = []
        self.mus_rounds = 0
        self.mus_idx = 0
        self.discard_idx = 0
        self.pending_discards: dict[int, tuple[Card, ...]] = {}
        self.lances: dict[Phase, LanceState] = {}
        self.declarations: dict[str, dict[int, bool]] = {}
        self.teams_in: set[int] = set()
        self.dealer = self.rng.randrange(NUM_SEATS)
        self.mano = (self.dealer + 1) % NUM_SEATS
        # Miradas y señas (FEM VIII). Generador aparte: activarlas no cambia el reparto.
        self.gaze_rng = random.Random(self.seed * 7919 + 1)
        self.gaze: list[int | None] = [None] * NUM_SEATS
        self.gaze_timer = [0] * NUM_SEATS
        self.ticks = 0
        self.signals_made: dict[int, set[Signal]] = {s: set() for s in range(NUM_SEATS)}
        self._emit(
            EventKind.GAME_STARTED,
            None,
            {"seed_public": False, "target": self.config.target_points, "teams": [[0, 2], [1, 3]]},
        )
        self._start_round()
        self._advance_time()

    # ------------------------------------------------------------------ utilidades
    def clone(self) -> MusGame:
        """Copia profunda e independiente (para simulaciones del motor, nunca para bots)."""
        return copy.deepcopy(self)

    @property
    def finished(self) -> bool:
        return self.phase is Phase.GAME_OVER

    def order_from(self, start: int) -> list[int]:
        return [(start + i) % NUM_SEATS for i in range(NUM_SEATS)]

    @property
    def speaking_order(self) -> list[int]:
        return self.order_from(self.mano)

    def _emit(
        self,
        kind: EventKind,
        actor: int | None,
        payload: dict[str, Any] | None = None,
        visibility: Visibility = Visibility.PUBLIC,
        recipients: tuple[int, ...] = (),
    ) -> None:
        self.events.append(
            GameEvent(
                seq=len(self.events),
                kind=kind,
                round_no=self.round_no,
                phase=self.phase.value,
                actor=actor,
                payload=payload or {},
                visibility=visibility,
                recipients=recipients,
            )
        )

    def _set_phase(self, new: Phase) -> None:
        if new not in ALLOWED_TRANSITIONS[self.phase] and new is not self.phase:
            raise IllegalTransition(f"{self.phase.value} -> {new.value}")
        self.phase = new

    # ------------------------------------------------------------------ jugada
    def _start_round(self) -> None:
        self.round_no += 1
        self.lances = {}
        self.declarations = {}
        self.mus_rounds = 0
        self.mus_idx = 0
        self.pending_discards = {}
        self.discard_pile = []
        self.signals_made = {s: set() for s in range(NUM_SEATS)}
        self.deck = shuffled_deck(self.rng)
        self.phase = Phase.MUS
        self._emit(EventKind.DEALER_ASSIGNED, None, {"dealer": self.dealer, "mano": self.mano})
        self._emit(
            EventKind.DECK_SHUFFLED,
            None,
            {"deck": [c.code for c in self.deck]},
            Visibility.SYSTEM,
        )
        self.hands = [[] for _ in range(NUM_SEATS)]
        # FEM III.2: de uno en uno, de derecha a izquierda, empezando por el mano.
        for _ in range(4):
            for seat in self.speaking_order:
                self.hands[seat].append(self.deck.pop())
        for seat in range(NUM_SEATS):
            self._emit(
                EventKind.CARDS_DEALT,
                None,
                {"seat": seat, "cards": [c.code for c in self.hands[seat]]},
                Visibility.PRIVATE,
                (seat,),
            )

    # ------------------------------------------------------------------ turnos
    @property
    def turn(self) -> int | None:
        """Asiento que debe actuar, o ``None`` si la partida terminó."""
        if self.phase is Phase.GAME_OVER:
            return None
        if self.phase is Phase.MUS:
            return self.speaking_order[self.mus_idx]
        if self.phase is Phase.DISCARD:
            return self._discard_order()[self.discard_idx]
        lance = self.lances[self.phase]
        if lance.status == "pending":
            return lance.responders[0]
        return lance.participants[lance.turn_idx]

    def _discard_order(self) -> list[int]:
        # FEM III.11: empieza el que reparte y termina el mano.
        return [(self.dealer - i) % NUM_SEATS for i in range(NUM_SEATS)]

    # ------------------------------------------------------------------ legalidad
    def legal_specs(self, seat: int) -> list[ActionSpec]:
        """Familias de acciones legales para ``seat`` (vacío si no es su turno)."""
        if seat != self.turn:
            return []
        cfg = self.config
        if self.phase is Phase.MUS:
            if self.mus_rounds >= cfg.max_mus_rounds:
                return [ActionSpec("cut")]
            return [ActionSpec("mus"), ActionSpec("cut")]
        if self.phase is Phase.DISCARD:
            return [ActionSpec("discard", cfg.min_discard, 4)]
        lance = self.lances[self.phase]
        if lance.status == "open":
            return [
                ActionSpec("pass"),
                ActionSpec("bet", cfg.min_bet, cfg.max_bet),
                ActionSpec("ordago"),
            ]
        specs: list[ActionSpec] = []
        if self._must_accept_no_lose(seat, lance):
            if self.lance_has(partner_of(seat), lance.lance):
                specs.append(ActionSpec("accept_no_lose"))
        else:
            specs.append(ActionSpec("accept"))
        specs.append(ActionSpec("reject"))
        if not lance.is_ordago:
            room = cfg.max_bet - lance.stake
            if room >= cfg.min_bet:
                specs.append(ActionSpec("raise", cfg.min_bet, room))
            specs.append(ActionSpec("ordago"))
        return specs

    def _must_accept_no_lose(self, seat: int, lance: LanceState) -> bool:
        """FEM VI.9: el postre con 33 no puede querer un órdago a juego salvo "quiero y no pierdo"."""
        return (
            lance.lance is Phase.JUEGO
            and lance.is_ordago
            and seat == self.dealer
            and ev.total_points(self.hands[seat], self.config.eight_kings) == 33
        )

    def lance_has(self, seat: int, lance: Phase) -> bool:
        k8 = self.config.eight_kings
        if lance is Phase.PARES:
            return ev.pairs(self.hands[seat], k8).has_pairs
        if lance is Phase.JUEGO:
            return ev.has_juego(self.hands[seat], k8)
        return True

    def validate(self, seat: int, action: Action) -> str | None:
        """Devuelve ``None`` si la acción es legal, o el motivo si no lo es."""
        if self.phase is Phase.GAME_OVER:
            return "La partida ha terminado"
        if not 0 <= seat < NUM_SEATS:
            return "Asiento inválido"
        if seat != self.turn:
            return "No es tu turno"
        specs = {s.type: s for s in self.legal_specs(seat)}
        spec = specs.get(action.type)
        if spec is None:
            return f"Acción '{action.type}' no permitida en esta fase"
        if isinstance(action, BetAction | RaiseAction):
            assert spec.min_amount is not None and spec.max_amount is not None
            if not spec.min_amount <= action.amount <= spec.max_amount:
                return f"Cantidad fuera de rango [{spec.min_amount}, {spec.max_amount}]"
        if isinstance(action, DiscardAction):
            cards = action.cards
            if len(set(cards)) != len(cards):
                return "Cartas repetidas en el descarte"
            if not self.config.min_discard <= len(cards) <= 4:
                return f"Debes descartar entre {self.config.min_discard} y 4 cartas"
            if any(c not in self.hands[seat] for c in cards):
                return "Solo puedes descartar cartas de tu mano"
        return None

    # ------------------------------------------------------------------ aplicar
    def apply(self, seat: int, action: Action) -> list[GameEvent]:
        """Valida y ejecuta ``action``. Devuelve los eventos generados."""
        reason = self.validate(seat, action)
        if reason is not None:
            raise IllegalAction(reason)
        start = len(self.events)
        # validate() garantiza que el tipo de acción corresponde a la fase.
        if isinstance(action, MusAction | CutMusAction):
            self._on_mus(seat, action)
        elif isinstance(action, DiscardAction):
            self._on_discard(seat, action)
        else:
            self._on_lance_action(seat, action)
        self._advance_time()
        return self.events[start:]

    # ------------------------------------------------------------------ miradas y señas
    def tick(self) -> list[GameEvent]:
        """Avanza el reloj de la mesa un paso (las miradas cambian). No es una acción de juego."""
        start = len(self.events)
        self._advance_time()
        return self.events[start:]

    def _advance_time(self) -> None:
        if not self.config.signals_enabled or self.phase is Phase.GAME_OVER:
            return
        self.ticks += 1
        cfg = self.config
        for seat in range(NUM_SEATS):
            self.gaze_timer[seat] -= 1
            if self.gaze_timer[seat] > 0:
                continue
            self.gaze_timer[seat] = self.gaze_rng.randint(cfg.gaze_min_ticks, cfg.gaze_max_ticks)
            w_partner, w_rivals, _w_table = cfg.gaze_weights
            r = self.gaze_rng.random() * sum(cfg.gaze_weights)
            if r < w_partner:
                target: int | None = partner_of(seat)
            elif r < w_partner + w_rivals:
                target = (seat + self.gaze_rng.choice((1, 3))) % NUM_SEATS
            else:
                target = None
            if target != self.gaze[seat]:
                self.gaze[seat] = target
                self._emit(EventKind.GAZE_CHANGED, seat, {"seat": seat, "target": target})

    def legal_signals(self, seat: int) -> list[Signal]:
        """Señas que ``seat`` puede hacer ahora: verdaderas (FEM VIII.4), tras cortar el mus,
        y cada una una sola vez por jugada."""
        if not self.config.signals_enabled or self.phase not in LANCES:
            return []
        valid = truthful_signals(self.hands[seat], self.config.eight_kings)
        return sorted(valid - self.signals_made[seat], key=lambda s: s.value)

    def watchers(self, seat: int) -> list[int]:
        """Quién está mirando a ``seat`` en este momento."""
        return [s for s in range(NUM_SEATS) if s != seat and self.gaze[s] == seat]

    def signal(self, seat: int, signal: Signal | str) -> list[GameEvent]:
        """Hace una seña. Solo la ven quienes miran a ``seat`` en ese instante; quien la hace
        sabe quién le miraba. Lanza :class:`IllegalAction` si no es verdadera o no toca."""
        try:
            sig = Signal(signal)
        except ValueError as exc:
            raise IllegalAction(f"Seña desconocida: {signal}") from exc
        if not 0 <= seat < NUM_SEATS:
            raise IllegalAction("Asiento inválido")
        if sig not in self.legal_signals(seat):
            raise IllegalAction("Esa seña no es posible ahora (solo señas verdaderas, tras cortar)")
        start = len(self.events)
        self.signals_made[seat].add(sig)
        seen_by = self.watchers(seat)
        self._emit(
            EventKind.SIGNAL_MADE,
            seat,
            {"seat": seat, "signal": sig.value, "seen_by": seen_by},
            Visibility.PRIVATE,
            (seat,),
        )
        if seen_by:
            self._emit(
                EventKind.SIGNAL_SEEN,
                seat,
                {"seat": seat, "signal": sig.value},
                Visibility.PRIVATE,
                tuple(seen_by),
            )
        return self.events[start:]

    # --- mus
    def _on_mus(self, seat: int, action: MusAction | CutMusAction) -> None:
        if isinstance(action, CutMusAction):
            self._emit(EventKind.MUS_CUT, seat)
            self._begin_lances()
            return
        self._emit(EventKind.MUS_REQUESTED, seat)
        self.mus_idx += 1
        if self.mus_idx == NUM_SEATS:
            self.mus_rounds += 1
            self.discard_idx = 0
            self.pending_discards = {}
            self._set_phase(Phase.DISCARD)

    def _on_discard(self, seat: int, action: DiscardAction) -> None:
        self.pending_discards[seat] = action.cards
        for card in action.cards:
            self.hands[seat].remove(card)
            self.discard_pile.append(card)
        self._emit(EventKind.CARDS_DISCARDED, seat, {"seat": seat, "count": len(action.cards)})
        self._emit(
            EventKind.CARDS_DISCARDED,
            seat,
            {"seat": seat, "cards": [c.code for c in action.cards]},
            Visibility.PRIVATE,
            (seat,),
        )
        self.discard_idx += 1
        if self.discard_idx < NUM_SEATS:
            return
        # FEM III.2: se sirve de una vez a cada jugador, en el orden del reparto.
        for target in self.speaking_order:
            needed = len(self.pending_discards[target])
            received: list[Card] = []
            for _ in range(needed):
                if not self.deck:
                    self._reshuffle_discards()
                received.append(self.deck.pop())
            self.hands[target].extend(received)
            self._emit(
                EventKind.CARDS_RECEIVED,
                None,
                {"seat": target, "cards": [c.code for c in received]},
                Visibility.PRIVATE,
                (target,),
            )
        self.pending_discards = {}
        self.mus_idx = 0
        self._set_phase(Phase.MUS)

    def _reshuffle_discards(self) -> None:
        """FEM III.15: si se acaba el mazo, se baraja el descarte."""
        self.deck = self.discard_pile
        self.discard_pile = []
        self.rng.shuffle(self.deck)
        self._emit(EventKind.DECK_RESHUFFLED, None, {"cards": len(self.deck)})

    # --- lances
    def _begin_lances(self) -> None:
        self._set_phase(Phase.GRANDE)
        self._open_lance(Phase.GRANDE)

    def _open_lance(self, lance: Phase) -> None:
        order = self.speaking_order
        k8 = self.config.eight_kings
        if lance is Phase.PARES:
            for seat in order:
                has = ev.pairs(self.hands[seat], k8).has_pairs
                self.declarations.setdefault("pares", {})[seat] = has
                self._emit(EventKind.PAIRS_DECLARED, seat, {"seat": seat, "has": has})
            participants = [s for s in order if self.declarations["pares"][s]]
        elif lance is Phase.JUEGO:
            participants = [s for s in order if self.declarations["juego"][s]]
        else:
            participants = order
        teams = {team_of(s) for s in participants}
        state = LanceState(lance, participants, has_betting=len(teams) == 2)
        if not participants or not state.has_betting:
            state.status = "no_bet"
        self.lances[lance] = state
        self._emit(
            EventKind.LANCE_STARTED,
            None,
            {
                "lance": lance.value,
                "participants": participants,
                "betting": state.has_betting,
                "lance_mano": participants[0] if participants else None,
            },
        )
        if state.closed:
            self._advance_lance()

    def _declare_juego(self) -> None:
        k8 = self.config.eight_kings
        for seat in self.speaking_order:
            has = ev.has_juego(self.hands[seat], k8)
            self.declarations.setdefault("juego", {})[seat] = has
            self._emit(EventKind.GAME_DECLARED, seat, {"seat": seat, "has": has})

    def _advance_lance(self) -> None:
        if self.phase is Phase.GAME_OVER:
            return
        if self.phase is Phase.GRANDE:
            nxt = Phase.CHICA
        elif self.phase is Phase.CHICA:
            nxt = Phase.PARES
        elif self.phase is Phase.PARES:
            self._declare_juego()
            nxt = Phase.JUEGO if any(self.declarations["juego"].values()) else Phase.PUNTO
        else:
            self._finish_round()
            return
        self._set_phase(nxt)
        self._open_lance(nxt)

    def _responders(self, actor: int, lance: LanceState) -> list[int]:
        order = self.order_from((actor + 1) % NUM_SEATS)
        return [s for s in order if team_of(s) != team_of(actor) and s in lance.participants]

    def _on_lance_action(self, seat: int, action: Action) -> None:
        lance = self.lances[self.phase]
        team = team_of(seat)
        if isinstance(action, PassAction):
            self._emit(EventKind.PASSED, seat, {"lance": lance.lance.value})
            lance.turn_idx += 1
            if lance.turn_idx >= len(lance.participants):
                lance.status = "passed"
                self._advance_lance()
            return
        if isinstance(action, BetAction):
            lance.status = "pending"
            lance.bettor_team = team
            lance.previous = self.config.negada_points
            lance.stake = action.amount
            lance.responders = self._responders(seat, lance)
            self._emit(
                EventKind.BET_PLACED, seat, {"lance": lance.lance.value, "amount": action.amount}
            )
            return
        if isinstance(action, RaiseAction):
            lance.previous = lance.stake
            lance.stake += action.amount
            lance.bettor_team = team
            lance.responders = self._responders(seat, lance)
            self._emit(
                EventKind.BET_RAISED,
                seat,
                {"lance": lance.lance.value, "amount": action.amount, "total": lance.stake},
            )
            return
        if isinstance(action, OrdagoAction):
            lance.previous = lance.stake if lance.status == "pending" else self.config.negada_points
            lance.status = "pending"
            lance.is_ordago = True
            lance.bettor_team = team
            lance.responders = self._responders(seat, lance)
            self._emit(EventKind.ORDAGO_DECLARED, seat, {"lance": lance.lance.value})
            return
        if isinstance(action, AcceptAction | AcceptNoLoseAction):
            if lance.is_ordago:
                self._emit(
                    EventKind.ORDAGO_ACCEPTED,
                    seat,
                    {"lance": lance.lance.value, "no_lose": isinstance(action, AcceptNoLoseAction)},
                )
                lance.status = "ordago"
                self._resolve_ordago(lance)
                return
            lance.status = "accepted"
            lance.accepted_stake = lance.stake
            self._emit(
                EventKind.BET_ACCEPTED, seat, {"lance": lance.lance.value, "amount": lance.stake}
            )
            self._advance_lance()
            return
        if isinstance(action, RejectAction):
            lance.responders.pop(0)
            final = not lance.responders
            self._emit(EventKind.BET_REJECTED, seat, {"lance": lance.lance.value, "final": final})
            if not final:
                return  # FEM VI.4: vale el "quiero" del compañero si lo dice.
            lance.status = "rejected"
            assert lance.bettor_team is not None
            concept = (
                "negada" if lance.previous == self.config.negada_points else "envite_no_querido"
            )
            self._award(lance.bettor_team, lance.previous, concept, lance.lance, immediate=True)
            if self.phase is not Phase.GAME_OVER:
                self._advance_lance()
            return
        raise IllegalAction(f"Acción inesperada: {action!r}")  # pragma: no cover

    # ------------------------------------------------------------------ resolución
    def lance_winner(self, lance: Phase) -> int | None:
        """Asiento ganador del lance (con las cartas reales). ``None`` si nadie lo lleva."""
        k8 = self.config.eight_kings
        order = self.speaking_order
        keys: dict[int, tuple[int, ...]]
        if lance is Phase.GRANDE:
            keys = {s: ev.grande_key(self.hands[s], k8) for s in order}
        elif lance is Phase.CHICA:
            keys = {s: ev.chica_key(self.hands[s], k8) for s in order}
        elif lance is Phase.PARES:
            keys = {
                s: ev.pairs(self.hands[s], k8).key for s in order if self.lance_has(s, Phase.PARES)
            }
        elif lance is Phase.JUEGO:
            keys = {s: ev.juego_key(self.hands[s], k8) for s in order if self.lance_has(s, lance)}
        else:
            keys = {s: ev.punto_key(self.hands[s], k8) for s in order}
        if not keys:
            return None
        return ev.best_seat(keys, order)

    def play_value(self, team: int, lance: Phase) -> int:
        """Valor de las jugadas de una pareja en pares/juego/punto [CONVENCIÓN]."""
        cfg = self.config
        k8 = cfg.eight_kings
        total = 0
        if lance is Phase.PARES:
            values = {
                ev.PairsKind.PAR: cfg.par_points,
                ev.PairsKind.MEDIAS: cfg.medias_points,
                ev.PairsKind.DUPLES: cfg.duples_points,
                ev.PairsKind.NONE: 0,
            }
            for seat in (team, team + 2):
                total += values[ev.pairs(self.hands[seat], k8).kind]
        elif lance is Phase.JUEGO:
            for seat in (team, team + 2):
                points = ev.total_points(self.hands[seat], k8)
                if points == 31:
                    total += cfg.juego_31_points
                elif points > 31:
                    total += cfg.juego_points
        elif lance is Phase.PUNTO:
            total = cfg.punto_points
        return total

    def _reveal_hands(self) -> None:
        if any(
            e.kind is EventKind.HANDS_REVEALED and e.round_no == self.round_no for e in self.events
        ):
            return
        self._emit(
            EventKind.HANDS_REVEALED,
            None,
            {"hands": {str(s): [c.code for c in self.hands[s]] for s in range(NUM_SEATS)}},
        )

    def _resolve_ordago(self, lance: LanceState) -> None:
        winner_seat = self.lance_winner(lance.lance)
        assert winner_seat is not None
        self._reveal_hands()
        self._emit(
            EventKind.LANCE_RESOLVED,
            None,
            {"lance": lance.lance.value, "winner_seat": winner_seat, "ordago": True},
        )
        # FEM VII.12: el órdago aceptado anula los envites aceptados anteriores.
        self._end_game(team_of(winner_seat), "ordago")

    def _award(
        self, team: int, points: int, concept: str, lance: Phase, immediate: bool = False
    ) -> bool:
        """Suma tantos. Devuelve ``True`` si con ellos termina el juego."""
        if points <= 0 or self.phase is Phase.GAME_OVER:
            return False
        self.score[team] += points
        self._emit(
            EventKind.POINTS_AWARDED,
            None,
            {
                "team": team,
                "points": points,
                "concept": concept,
                "lance": lance.value,
                "immediate": immediate,
                "score": list(self.score),
            },
        )
        remaining = self.config.target_points - self.score[team]
        if 0 < remaining <= self.config.team_in_threshold and team not in self.teams_in:
            self.teams_in.add(team)
            self._emit(EventKind.TEAM_IS_IN, None, {"team": team})
        if self.score[team] >= self.config.target_points and (
            not immediate or self.config.end_on_immediate_points
        ):
            self._reveal_hands()
            self._end_game(team, "points")
            return True
        return False

    def _finish_round(self) -> None:
        """Tanteo al final de la jugada, en orden de lances (FEM VI.6, VII.2)."""
        self._reveal_hands()  # FEM VII.9
        for phase, lance in self.lances.items():
            winner_seat = self.lance_winner(phase)
            self._emit(
                EventKind.LANCE_RESOLVED,
                None,
                {"lance": phase.value, "winner_seat": winner_seat, "status": lance.status},
            )
            if winner_seat is None:
                continue
            winner = team_of(winner_seat)
            if self._score_lance(phase, lance, winner):
                return
        self._emit(EventKind.ROUND_FINISHED, None, {"score": list(self.score)})
        self.dealer = self.mano
        self.mano = (self.mano + 1) % NUM_SEATS
        self._start_round()

    def _score_lance(self, phase: Phase, lance: LanceState, winner: int) -> bool:
        cfg = self.config
        if lance.status == "rejected":
            # El envite rechazado ya se apuntó. En pares/juego/punto hay deje:
            # la pareja que ganó el envite cobra además sus jugadas (FEM VII.1, VIII.8).
            if phase in (Phase.GRANDE, Phase.CHICA):
                return False
            assert lance.bettor_team is not None
            return self._award(
                lance.bettor_team, self.play_value(lance.bettor_team, phase), phase.value, phase
            )
        if lance.status == "accepted":
            if self._award(winner, lance.accepted_stake, "envite", phase):
                return True
        elif phase in (Phase.GRANDE, Phase.CHICA):
            return self._award(winner, cfg.paso_points, "paso", phase)
        if phase in (Phase.PARES, Phase.JUEGO, Phase.PUNTO):
            return self._award(winner, self.play_value(winner, phase), phase.value, phase)
        return False

    def _end_game(self, winner: int, reason: str) -> None:
        self.phase = Phase.GAME_OVER
        self.result = GameResult(winner, (self.score[0], self.score[1]), reason, self.round_no)
        self._emit(
            EventKind.GAME_FINISHED,
            None,
            {"winner": winner, "score": list(self.score), "reason": reason},
        )

    def forfeit(self, loser_team: int, reason: str) -> None:
        """Termina la partida por abandono, fallo de bot o error (no es una acción de juego)."""
        if self.phase is Phase.GAME_OVER:
            return
        self._end_game(1 - loser_team, reason)
