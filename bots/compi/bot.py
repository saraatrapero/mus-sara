"""Bot `compi`: juega en pareja y mirando el marcador, con reglas sencillas."""

from musst.bots.api import (
    AcceptAction,
    AcceptNoLoseAction,
    Action,
    BetAction,
    Bot,
    Card,
    CutMusAction,
    DiscardAction,
    MusAction,
    Observation,
    OrdagoAction,
    PassAction,
    RaiseAction,
    RejectAction,
)
from musst.bots.toolkit import hand_strength, hand_value
from musst.engine import evaluation as ev

FIGURES = (10, 11, 12)  # sota, caballo y rey: valen 10 para el juego


def points(card: Card) -> int:
    """Lo que vale una carta para el juego (el 3 cuenta como rey y el 2 como as)."""
    rank = ev.grande_key([card])[0]
    return 10 if rank in FIGURES else rank


class CompiBot(Bot):
    name = "compi"
    author = "Equipo CONECTA_CUATRO"
    version = "1.0"

    def decide(self, observation: Observation) -> Action:
        try:
            return self._decide(observation)
        except Exception:  # nunca lanzar: una acción legal prudente
            return self._safe(observation)

    # ------------------------------------------------------------------ fases
    def _decide(self, obs: Observation) -> Action:
        legal = obs.legal_types()
        if "mus" in legal or "cut" in legal:
            return self._mus(obs)
        if "discard" in legal:
            return DiscardAction(self._discard(obs.hand))
        strength = self._team_strength(obs)
        if "pass" in legal:
            return self._abrir(obs, strength)
        return self._respond(obs, strength)

    def _mus(self, obs: Observation) -> Action:
        hand = obs.hand
        good = (
            ev.total_points(hand) in (31, 32)
            or ev.pairs(hand).kind >= ev.PairsKind.MEDIAS
            or hand_value(hand) >= 0.5
        )
        if good or "mus" not in obs.legal_types():
            return CutMusAction()
        return MusAction()

    def _discard(self, hand: tuple[Card, ...]) -> tuple[Card, ...]:
        """Va a por juego y pares: guarda figuras y parejas, tira lo demás (mínimo una)."""
        ranks = [ev.grande_key([c])[0] for c in hand]
        keep = [c for c, r in zip(hand, ranks, strict=True) if r in FIGURES or ranks.count(r) >= 2]
        discard = [c for c in hand if c not in keep]
        if not discard:  # todo vale: tira la carta que menos suma
            discard = [min(hand, key=points)]
        return tuple(discard)

    # ------------------------------------------------------------- en pareja
    def _team_strength(self, obs: Observation) -> float:
        """Fuerza de la pareja en el lance: la mía, más lo que ha cantado mi compañero."""
        lance = obs.phase
        mine = hand_strength(obs.hand, lance)
        said = obs.declarations.get(lance, {})
        if lance in ("pares", "juego"):
            rivals = [said.get(s) for s in obs.opponents]
            if rivals and all(r is False for r in rivals):
                return 1.0  # los rivales han dicho que no tienen: el lance es nuestro
            if said.get(obs.partner):
                mine = max(mine, 0.5) + 0.15  # mi compañero también tiene
        return min(1.0, mine + self._urgency(obs))

    def _urgency(self, obs: Observation) -> float:
        """Más atrevido si vamos perdiendo, más prudente si vamos ganando."""
        us, them = obs.score[obs.team], obs.score[1 - obs.team]
        return 0.15 * (them - us) / max(1, obs.target)

    def _rival_about_to_win(self, obs: Observation) -> bool:
        return obs.score[1 - obs.team] >= obs.target - 5

    # --------------------------------------------------------------- envites
    def _abrir(self, obs: Observation, s: float) -> Action:
        legal = obs.legal_types()
        if "ordago" in legal and s >= 0.9 and self._rival_about_to_win(obs):
            return OrdagoAction()
        spec = obs.spec("bet")
        if spec is not None and s >= 0.7:
            low, high = spec.min_amount or 2, spec.max_amount or 2
            return BetAction(min(high, max(low, 4 if s >= 0.85 else 2)))
        return PassAction()

    def _respond(self, obs: Observation, s: float) -> Action:
        legal = obs.legal_types()
        bet = obs.current_bet
        accept: Action = AcceptAction() if "accept" in legal else AcceptNoLoseAction()
        can_accept = accept.type in legal
        if bet is not None and bet.is_ordago:
            need = 0.6 if self._rival_about_to_win(obs) else 0.85
            return accept if can_accept and s >= need else RejectAction()
        spec = obs.spec("raise")
        if spec is not None and s >= 0.9:
            return RaiseAction(spec.min_amount or 2)
        if can_accept and s >= 0.55:
            return accept
        return RejectAction()

    def _safe(self, obs: Observation) -> Action:
        legal = obs.legal_types()
        for kind, action in (
            ("pass", PassAction()),
            ("reject", RejectAction()),
            ("cut", CutMusAction()),
        ):
            if kind in legal:
                return action
        if "discard" in legal:
            return DiscardAction((obs.hand[0],))
        return obs.legal_actions[0].default()
