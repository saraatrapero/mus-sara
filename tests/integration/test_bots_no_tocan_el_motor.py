"""Un bot en el mismo proceso no puede cambiar la partida tocando su Observation (Req 4.1).

La Observation se construye con copias: si un bot modifica su historial o sus cartas, solo
cambia su copia. Y un bot que lanza ``SystemExit`` pierde la partida sin pararla.
"""

import sys

from musst import play_game
from musst.bots.api import Action, Bot, Observation
from musst.bots.builtin import RandomBot, SimpleBot
from musst.engine import BetAction, CutMusAction, PassAction


def _jugada_simple(obs: Observation) -> Action:
    tipos = obs.legal_types()
    if "cut" in tipos:
        return CutMusAction()
    if "pass" in tipos:
        return PassAction()
    return obs.legal_actions[0].default()


class QuitaRivales(Bot):
    """Borra a los rivales de la lista de participantes del lance y envida."""

    name = "quita_rivales"

    def decide(self, obs: Observation) -> Action:
        if obs.phase in ("pares", "juego") and "bet" in obs.legal_types():
            for evento in obs.history:
                if evento["kind"] == "LanceStarted":
                    participantes = evento["payload"]["participants"]
                    participantes[:] = [s for s in participantes if s % 2 == obs.team]
            return BetAction(2)
        return _jugada_simple(obs)


class Pasivo(Bot):
    name = "pasivo"

    def decide(self, obs: Observation) -> Action:
        return _jugada_simple(obs)


def test_modificar_el_historial_no_cambia_la_partida() -> None:
    # Antes del arreglo, la semilla 4 rompía play_game con IndexError (y con ella el torneo).
    for seed in range(12):
        match = play_game([QuitaRivales(), Pasivo(), Pasivo(), Pasivo()], seed=seed)
        assert match.result.winner in (0, 1)
        assert not match.errors, match.errors


class CambiaSusCartas(Bot):
    """Intenta convertir su mano en cuatro reyes saltándose el ``frozen`` de Card."""

    name = "cambia_cartas"

    def decide(self, obs: Observation) -> Action:
        for carta in obs.hand:
            object.__setattr__(carta, "rank", 12)
        return _jugada_simple(obs)


def test_modificar_las_cartas_de_la_observacion_no_cambia_la_mano() -> None:
    base = play_game([Pasivo(), Pasivo(), Pasivo(), Pasivo()], seed=3)
    trampa = play_game([CambiaSusCartas(), Pasivo(), Pasivo(), Pasivo()], seed=3)
    assert trampa.result == base.result


class SeVa(Bot):
    name = "se_va"

    def decide(self, obs: Observation) -> Action:
        sys.exit(1)


def test_un_bot_que_llama_a_sys_exit_pierde_sin_parar_la_partida() -> None:
    match = play_game([SeVa(), SimpleBot(1), RandomBot(2), SimpleBot(3)], seed=5, mode="tournament")
    assert match.result.winner == 1
    assert match.errors and match.errors[0].kind == "exception"


class EnvidoConDecimales(Bot):
    name = "decimales"

    def decide(self, obs: Observation) -> Action:
        if "bet" in obs.legal_types():
            return BetAction(2.5)  # type: ignore[arg-type]
        return _jugada_simple(obs)


def test_un_envite_con_decimales_es_ilegal() -> None:
    match = play_game(
        [EnvidoConDecimales(), Pasivo(), Pasivo(), Pasivo()], seed=1, mode="tournament"
    )
    assert match.errors and match.errors[0].kind == "illegal"
    assert all(isinstance(t, int) for t in match.result.score)
