"""Bot de ejemplo para el tutorial: envida con reyes, acepta con buena mano."""

from musst.bots.api import (
    AcceptAction,
    Action,
    BetAction,
    Bot,
    CutMusAction,
    DiscardAction,
    MusAction,
    Observation,
    PassAction,
    RejectAction,
)


class EjemploBot(Bot):
    name = "ejemplo"
    author = "MUS.ST"
    version = "1.0"

    def decide(self, observation: Observation) -> Action:
        legal = observation.legal_types()
        kings = sum(1 for c in observation.hand if c.rank in (12, 3))
        if "cut" in legal:
            return CutMusAction() if kings >= 2 or "mus" not in legal else MusAction()
        if "discard" in legal:
            worst = [c for c in observation.hand if c.rank not in (12, 3)] or [observation.hand[0]]
            return DiscardAction(tuple(worst))
        if "pass" in legal:
            return BetAction(2) if kings >= 3 else PassAction()
        if "accept" in legal and kings >= 2:
            return AcceptAction()
        return RejectAction()
