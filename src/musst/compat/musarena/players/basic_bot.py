"""Bot básico: la primera versión del heurístico, con reglas sencillas y sin leer la mesa.

Se conserva como referencia para medir si los bots nuevos son mejores.

Las reglas están pensadas para poder explicarse en voz alta:

1. **Mus**: puntúa la mano (31, duples, medias, pareja de reyes, grande o chica muy buenas) y
   corta si la puntuación llega a :data:`UMBRAL_CORTE`.
2. **Descarte**: juega "a reyes" (se queda con reyes y parejas) o "a chica" si lleva dos o
   más ases y menos de dos reyes (se queda con ases, cuatros y parejas).
3. **Apuestas**: estima la probabilidad de que su pareja gane el lance (ver
   :meth:`BasicBot.prob_ganar`) y
   - sin envite previo: envida más cuanto mejor va, con un farol de vez en cuando;
   - ante un envite: quiere solo si le compensa en valor esperado frente a perder el deje, y
     reenvida o echa órdago con manos muy buenas.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from musst.compat.musarena.actions import (
    Action,
    Descarte,
    Envido,
    Mus,
    NoHayMus,
    NoQuiero,
    Ordago,
    Paso,
    Quiero,
    Reenvido,
)
from musst.compat.musarena.cards import Carta
from musst.compat.musarena.fuerza import fuerza
from musst.compat.musarena.hands import Lance, TipoPares, clave_pares, puntos, tiene_juego, tipo_pares
from musst.compat.musarena.observation import Observation
from musst.compat.musarena.player import Bot
from musst.compat.musarena.state import TANTOS_VACA, Fase, pareja

#: Puntuación de la mano a partir de la cual se corta el mus.
UMBRAL_CORTE = 3.0


class BasicBot(Bot):
    """Bot de reglas. ``farol`` es la probabilidad de envidar sin cartas si nadie ha envidado."""

    tipo = "basico"
    descripcion = "Heurístico sencillo: envida con buenas cartas sin fijarse en los rivales"

    def __init__(self, nombre: str | None = None, seed: int | None = None, farol: float = 0.08):
        super().__init__(nombre, seed)
        self.farol = farol

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        if observation.fase is Fase.MUS:
            accion = self._mus(observation.cartas)
        elif observation.fase is Fase.DESCARTE:
            accion = self._descarte(observation.cartas)
        else:
            accion = self._apuesta(observation, legal_actions)
        if accion in legal_actions:
            return accion
        # Red de seguridad: nunca devolver una jugada ilegal.
        for prudente in (Paso(), NoQuiero(), Quiero()):
            if prudente in legal_actions:
                return prudente
        return legal_actions[0]

    # --- Mus y descartes -------------------------------------------------------------------

    @staticmethod
    def puntuacion_mano(cartas: Sequence[Carta]) -> float:
        """Cuánto vale la mano para cortar el mus."""
        valor = 0.0
        if puntos(cartas) == 31:
            valor += 3
        elif tiene_juego(cartas):
            valor += 1
        tipo = tipo_pares(cartas)
        valor += {TipoPares.NADA: 0, TipoPares.PAR: 0.5, TipoPares.MEDIAS: 2,
                  TipoPares.DUPLES: 3}[tipo]
        if tipo is TipoPares.PAR and clave_pares(cartas)[1] == 12:
            valor += 0.5  # pareja de reyes
        if fuerza(Lance.GRANDE, cartas) > 0.85:
            valor += 1
        if fuerza(Lance.CHICA, cartas) > 0.85:
            valor += 1
        return valor

    def _mus(self, cartas: Sequence[Carta]) -> Action:
        return NoHayMus() if self.puntuacion_mano(cartas) >= UMBRAL_CORTE else Mus()

    @staticmethod
    def _descarte(cartas: Sequence[Carta]) -> Descarte:
        cuentas = Counter(c.rango for c in cartas)
        a_chica = cuentas[1] >= 2 and cuentas[12] < 2

        def se_queda(c: Carta) -> bool:
            if cuentas[c.rango] >= 2:
                return True
            return c.rango <= 4 if a_chica else c.rango == 12

        tirar = [c for c in cartas if not se_queda(c)]
        if not tirar:
            # Hay que descartar al menos una: la suelta peor (o la peor de todas, con duples).
            sueltas = [c for c in cartas if cuentas[c.rango] == 1] or list(cartas)
            peor = max if a_chica else min
            tirar = [peor(sueltas, key=lambda c: c.rango)]
        return Descarte(frozenset(tirar))

    # --- Apuestas --------------------------------------------------------------------------

    @staticmethod
    def prob_ganar(obs: Observation) -> float:
        """Probabilidad estimada de que la pareja del bot gane el lance en curso.

        Contra ``k`` rivales, la mano propia gana a todos con probabilidad ``fuerza**k``. Si el
        compañero también juega el lance, puede ganarlo él: se supone que su mano es una mano
        cualquiera, que gana a los ``k`` rivales con probabilidad ``1/(k+1)``. Si ha envidado
        el rival, se rebaja la estimación (``p**1.5``) porque probablemente tiene buenas cartas.
        """
        ap = obs.apuesta
        mia = obs.pareja
        rivales = [a for a in ap.participantes if pareja(a) != mia]
        k = len(rivales)
        p = fuerza(obs.lance, obs.cartas) ** k
        if obs.companero in ap.participantes:
            p = 1 - (1 - p) * (1 - 1 / (k + 1))
        if ap.pareja_apostadora is not None and ap.pareja_apostadora != mia:
            # p**1.5 rebaja mucho las manos dudosas (0.6 -> 0.46) y casi nada las seguras
            # (0.99 -> 0.985): un envite rival asusta, pero no a quien lleva cuatro reyes.
            p **= 1.5
        return p

    def _apuesta(self, obs: Observation, legal_actions: Sequence[Action]) -> Action:
        ap = obs.apuesta
        p = self.prob_ganar(obs)
        mia, rival = obs.pareja, 1 - obs.pareja
        rival_cerca = obs.tantos[rival] >= TANTOS_VACA - 10

        if ap.pareja_apostadora is None:
            if p >= 0.92 and (rival_cerca or obs.tantos[mia] >= TANTOS_VACA - 6):
                return Ordago()
            if p >= 0.8:
                return Envido(min(10, 2 + int((p - 0.8) * 40)))  # de 2 a 10 tantos
            if p >= 0.62 or self.rng.random() < self.farol:
                return Envido()
            return Paso()

        if ap.ordago:
            if obs.tantos[rival] >= TANTOS_VACA - 6:
                umbral = 0.45  # el rival está a punto de ganar la vaca: merece la pena arriesgar
            else:
                umbral = 0.72
            return Quiero() if p >= umbral else NoQuiero()

        if p >= 0.95 and rival_cerca:
            return Ordago()
        if p >= 0.88:
            reenvidos = [a.tantos for a in legal_actions if isinstance(a, Reenvido)]
            if reenvidos:
                return Reenvido(min(max(2, ap.tantos), max(reenvidos)))
            return Quiero()
        # Querer gana o pierde la apuesta (valor esperado (2p - 1) * apuesta); no querer pierde
        # el deje. Se quiere si (2p - 1) * apuesta > -deje, con un pequeño margen de prudencia.
        umbral = (ap.tantos - ap.deje) / (2 * ap.tantos) + 0.05
        return Quiero() if p >= umbral else NoQuiero()
