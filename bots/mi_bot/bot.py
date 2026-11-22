"""Bot `mi_bot`: reglas sencillas sobre la probabilidad de ganar cada lance."""

import random

from musst.bots.api import (
    AcceptAction,
    AcceptNoLoseAction,
    Action,
    BetAction,
    Bot,
    CutMusAction,
    DiscardAction,
    MusAction,
    Observation,
    OrdagoAction,
    PassAction,
    RaiseAction,
    RejectAction,
)
from musst.bots.toolkit import early_game, estimate_lance_win, hand_value, keep_heuristic_discard
from musst.engine import evaluation as ev

SIMULACIONES = 200  # repartos simulados por decisión
CORTAR = 0.45  # corta el mus con una mano al menos así de buena (valor de mano de 0 a 1)

# Umbrales de probabilidad de ganar el lance (0 = imposible, 1 = seguro)
ENVIDAR = 0.70  # envida 2
ENVIDAR_FUERTE = 0.85  # envida 4
SUBIR = 0.90  # reenvida si le envidan
QUERER = 0.55  # acepta un envite
ORDAGO_ECHAR = 0.95  # echa órdago (solo a partir de media partida)
ORDAGO_QUERER = 0.85  # acepta un órdago


class MiBot(Bot):
    name = "mi_bot"
    author = "Daniela González y Marcos González"
    version = "1.0"

    def __init__(self, seed: int = 2026) -> None:
        self.rng = random.Random(seed)

    def decide(self, observation: Observation) -> Action:
        try:
            return self._decide(observation)
        except Exception:  # nunca lanzar excepciones: se perdería la partida
            return self._seguro(observation)

    def _decide(self, obs: Observation) -> Action:
        legal = obs.legal_types()
        if "mus" in legal or "cut" in legal:
            return self._mus(obs)
        if "discard" in legal:
            return DiscardAction(keep_heuristic_discard(obs.hand))
        fuerza = self._fuerza(obs)
        if "pass" in legal:
            return self._abrir(obs, fuerza)
        return self._responder(obs, fuerza)

    # --------------------------------------------------------------- mus
    def _mus(self, obs: Observation) -> Action:
        """Corta con juego de 31/32, medias o duples, o una mano buena en general (>= CORTAR)."""
        hand = obs.hand
        buena = (
            ev.total_points(hand) in (31, 32)
            or ev.pairs(hand).kind >= ev.PairsKind.MEDIAS
            or hand_value(hand) >= CORTAR
        )
        if buena or "mus" not in obs.legal_types():
            return CutMusAction()
        return MusAction()

    # ----------------------------------------------------------- fuerza
    def _fuerza(self, obs: Observation) -> float:
        """Probabilidad de que mi pareja gane el lance, simulando repartos (toolkit del repo).

        Ya tiene en cuenta lo que han declarado todos (pares/juego) y quién es mano.
        """
        return estimate_lance_win(obs, obs.phase, self.rng, samples=SIMULACIONES).p_win

    # ----------------------------------------------------------- envites
    def _abrir(self, obs: Observation, fuerza: float) -> Action:
        legal = obs.legal_types()
        if "ordago" in legal and fuerza >= ORDAGO_ECHAR and not early_game(obs):
            return OrdagoAction()
        spec = obs.spec("bet")
        if spec is not None and fuerza >= ENVIDAR:
            cantidad = 4 if fuerza >= ENVIDAR_FUERTE else 2
            minimo, maximo = spec.min_amount or 2, spec.max_amount or 2
            return BetAction(min(maximo, max(minimo, cantidad)))
        return PassAction()

    def _responder(self, obs: Observation, fuerza: float) -> Action:
        legal = obs.legal_types()
        querer: Action = AcceptAction() if "accept" in legal else AcceptNoLoseAction()
        puede_querer = querer.type in legal
        apuesta = obs.current_bet
        if apuesta is not None and apuesta.is_ordago:
            return querer if puede_querer and fuerza >= ORDAGO_QUERER else RejectAction()
        spec = obs.spec("raise")
        if spec is not None and fuerza >= SUBIR:
            return RaiseAction(spec.min_amount or 2)
        if puede_querer and fuerza >= QUERER:
            return querer
        return RejectAction()

    # ----------------------------------------------------------- seguridad
    def _seguro(self, obs: Observation) -> Action:
        legal = obs.legal_types()
        for tipo, accion in (
            ("pass", PassAction()),
            ("reject", RejectAction()),
            ("cut", CutMusAction()),
        ):
            if tipo in legal:
                return accion
        if "discard" in legal:
            return DiscardAction((obs.hand[0],))
        return obs.legal_actions[0].default()
