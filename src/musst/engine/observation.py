"""ObservationBuilder: la única puerta entre el estado secreto y los jugadores.

Se construye por **lista blanca**: se copian campos concretos y nunca se serializa el estado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from musst.engine.actions import ActionSpec
from musst.engine.cards import Card
from musst.engine.events import EventKind
from musst.engine.game import NUM_SEATS, MusGame, Phase, partner_of, team_of


@dataclass(frozen=True)
class BetView:
    lance: str
    bettor_team: int | None
    stake: int
    previous: int
    is_ordago: bool
    responders: tuple[int, ...]


@dataclass(frozen=True)
class Observation:
    """Todo lo que un asiento puede saber legítimamente en este momento."""

    seat: int
    partner: int
    team: int
    hand: tuple[Card, ...]
    phase: str
    turn: int | None
    dealer: int
    mano: int
    round_no: int
    score: tuple[int, int]
    target: int
    declarations: dict[str, dict[int, bool]]
    current_bet: BetView | None
    lance_participants: tuple[int, ...]
    lance_statuses: dict[str, str]
    cards_in_deck: int
    mus_rounds: int
    legal_actions: tuple[ActionSpec, ...]
    history: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    revealed_hands: dict[int, tuple[Card, ...]] | None = None
    finished: bool = False
    winner: int | None = None

    @property
    def is_my_turn(self) -> bool:
        return self.turn == self.seat

    @property
    def opponents(self) -> tuple[int, int]:
        return ((self.seat + 1) % NUM_SEATS, (self.seat + 3) % NUM_SEATS)

    def legal_types(self) -> set[str]:
        return {spec.type for spec in self.legal_actions}

    def spec(self, kind: str) -> ActionSpec | None:
        for spec in self.legal_actions:
            if spec.type == kind:
                return spec
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialización JSON (para web y sandbox)."""
        bet = self.current_bet
        return {
            "seat": self.seat,
            "partner": self.partner,
            "team": self.team,
            "hand": [c.code for c in self.hand],
            "phase": self.phase,
            "turn": self.turn,
            "dealer": self.dealer,
            "mano": self.mano,
            "round": self.round_no,
            "score": list(self.score),
            "target": self.target,
            "declarations": {
                k: {str(s): v for s, v in d.items()} for k, d in self.declarations.items()
            },
            "current_bet": None
            if bet is None
            else {
                "lance": bet.lance,
                "bettor_team": bet.bettor_team,
                "stake": bet.stake,
                "previous": bet.previous,
                "is_ordago": bet.is_ordago,
                "responders": list(bet.responders),
            },
            "lance_participants": list(self.lance_participants),
            "lance_statuses": dict(self.lance_statuses),
            "cards_in_deck": self.cards_in_deck,
            "mus_rounds": self.mus_rounds,
            "legal_actions": [s.to_dict() for s in self.legal_actions],
            "history": list(self.history),
            "revealed_hands": None
            if self.revealed_hands is None
            else {str(s): [c.code for c in h] for s, h in self.revealed_hands.items()},
            "finished": self.finished,
            "winner": self.winner,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Observation:
        bet = data.get("current_bet")
        revealed = data.get("revealed_hands")
        return cls(
            seat=data["seat"],
            partner=data["partner"],
            team=data["team"],
            hand=tuple(Card.parse(c) for c in data["hand"]),
            phase=data["phase"],
            turn=data["turn"],
            dealer=data["dealer"],
            mano=data["mano"],
            round_no=data["round"],
            score=(data["score"][0], data["score"][1]),
            target=data["target"],
            declarations={
                k: {int(s): v for s, v in d.items()} for k, d in data["declarations"].items()
            },
            current_bet=None
            if bet is None
            else BetView(
                bet["lance"],
                bet["bettor_team"],
                bet["stake"],
                bet["previous"],
                bet["is_ordago"],
                tuple(bet["responders"]),
            ),
            lance_participants=tuple(data["lance_participants"]),
            lance_statuses=dict(data["lance_statuses"]),
            cards_in_deck=data["cards_in_deck"],
            mus_rounds=data["mus_rounds"],
            legal_actions=tuple(
                ActionSpec(s["type"], s.get("min"), s.get("max")) for s in data["legal_actions"]
            ),
            history=tuple(data.get("history", ())),
            revealed_hands=None
            if revealed is None
            else {int(s): tuple(Card.parse(c) for c in h) for s, h in revealed.items()},
            finished=data["finished"],
            winner=data["winner"],
        )


def build_observation(game: MusGame, seat: int, history_limit: int | None = None) -> Observation:
    """Proyecta el estado de ``game`` a la vista del asiento ``seat``."""
    if not 0 <= seat < NUM_SEATS:
        raise ValueError("Asiento inválido")
    bet: BetView | None = None
    participants: tuple[int, ...] = ()
    if game.phase in game.lances:
        lance = game.lances[game.phase]
        participants = tuple(lance.participants)
        if lance.status == "pending":
            bet = BetView(
                lance.lance.value,
                lance.bettor_team,
                lance.stake,
                lance.previous,
                lance.is_ordago,
                tuple(lance.responders),
            )
    visible = [e.to_dict() for e in game.events if e.visible_to(seat)]
    if history_limit is not None:
        visible = visible[-history_limit:]
    revealed = _revealed_hands(game)
    result = game.result
    return Observation(
        seat=seat,
        partner=partner_of(seat),
        team=team_of(seat),
        hand=tuple(game.hands[seat]),
        phase=game.phase.value,
        turn=game.turn,
        dealer=game.dealer,
        mano=game.mano,
        round_no=game.round_no,
        score=(game.score[0], game.score[1]),
        target=game.config.target_points,
        declarations={k: dict(v) for k, v in game.declarations.items()},
        current_bet=bet,
        lance_participants=participants,
        lance_statuses={p.value: s.status for p, s in game.lances.items()},
        cards_in_deck=len(game.deck),
        mus_rounds=game.mus_rounds,
        legal_actions=tuple(game.legal_specs(seat)),
        history=tuple(visible),
        revealed_hands=revealed,
        finished=game.phase is Phase.GAME_OVER,
        winner=result.winner if result else None,
    )


def build_spectator_view(game: MusGame) -> dict[str, Any]:
    """Vista de espectador: solo eventos públicos, sin ninguna mano."""
    return {
        "phase": game.phase.value,
        "turn": game.turn,
        "dealer": game.dealer,
        "mano": game.mano,
        "round": game.round_no,
        "score": list(game.score),
        "declarations": {
            k: {str(s): v for s, v in d.items()} for k, d in game.declarations.items()
        },
        "history": [e.to_dict() for e in game.events if e.visible_to(None)],
        "finished": game.finished,
    }


def _revealed_hands(game: MusGame) -> dict[int, tuple[Card, ...]] | None:
    """Manos públicas de la jugada en curso, solo si ya se han enseñado (FEM VII.9)."""
    for event in reversed(game.events):
        if event.round_no != game.round_no:
            break
        if event.kind is EventKind.HANDS_REVEALED:
            return {
                int(s): tuple(Card.parse(c) for c in cards)
                for s, cards in event.payload["hands"].items()
            }
    return None
