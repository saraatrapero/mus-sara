"""Bot heurístico avanzado: lee la mesa y decide pensando en ganar la vaca.

En cada decisión el bot:

1. **Lee la mesa** (:class:`~musst.compat.musarena.estrategia.creencias.Creencias`): estima qué mano puede
   tener cada uno de los otros tres a partir de sus declaraciones, de quién cortó el mus y de
   cómo han apostado.
2. **Calcula la probabilidad de que su pareja gane el lance**, con los empates a favor del más
   cercano a la mano (:func:`~musst.compat.musarena.estrategia.evaluacion.prob_ganar_lance`).
3. **Decide pensando en la vaca** (:func:`~musst.compat.musarena.estrategia.evaluacion.prob_vaca`): para
   querer o no, compara cómo quedaría su probabilidad de ganar la vaca en cada caso. Así, un
   mismo envite se quiere o no según el marcador: si un "no quiero" le haría perder la vaca,
   quiere. El umbral del órdago también baja cuanto peor va la vaca.
4. **Aprende de cada rival** (:class:`~musst.compat.musarena.estrategia.lectura.LectorRivales`): al final de
   cada mano ve las cartas de todos y ajusta cuánto va de farol cada uno.

Jugadas "humanas" que hace:

- **Corta el mus** con manos del percentil fijado por su estilo, algo antes si es mano o si los
  rivales han pedido mus, y algo después si su compañero ha pedido mus.
- **Descarta** eligiendo, entre los 15 descartes posibles, el que deja mejor mano media tras robar.
- **Envida** cuando su probabilidad de ganar el lance supera un umbral, más cuanta más mano
  tiene y con algo de variación para no ser previsible.
- **Pasa para querer**: con mano muy buena a veces pasa, si detrás habla un rival que puede
  envidar.
- **Va de farol**, sobre todo cuando habla el último y todos han pasado.
- **Deja hablar al compañero**: si el compañero responde después, solo quiere con lo que puede
  ganar él solo (medido: quitar esta regla le hace perder unos 4 puntos de porcentaje).
- **Reenvida y echa órdagos** con manos muy buenas; el órdago, antes si la vaca va mal.

Lo que se probó y **no** funcionó (queda como lección para el bot entrenado): elegir el tamaño
de los envites, los reenvidos y los órdagos con el modelo de "qué hará el rival" juega peor que
usar umbrales sobre la probabilidad propia, porque amplifica los errores de ese modelo.

Todos los umbrales están en un :class:`Estilo`, para poder tener bots con carácter distinto y
ajustarlos automáticamente. Cada decisión deja su explicación en ``self.razon``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

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
from musst.compat.musarena.estrategia.creencias import Creencias, ModeloRival, ronda_de_mus
from musst.compat.musarena.estrategia.evaluacion import bonus_pareja, prob_ganar_lance, prob_vaca
from musst.compat.musarena.estrategia.lectura import LectorRivales
from musst.compat.musarena.estrategia.tipos import PUNTOS, indice_de
from musst.compat.musarena.estrategia.valor import PERCENTIL, valor_tras_descarte
from musst.compat.musarena.observation import Observation
from musst.compat.musarena.player import Bot
from musst.compat.musarena.state import Fase, pareja


@dataclass(frozen=True)
class Estilo:
    """Carácter del bot: todos los umbrales de decisión."""

    nombre: str = "equilibrado"
    corte: float = 0.62  # percentil de mano a partir del cual corta el mus
    envite: float = 0.66  # probabilidad de ganar el lance a partir de la cual envida
    subida: float = 0.82  # probabilidad a partir de la cual reenvida
    ordago_igualado: float = 0.95  # probabilidad para echar órdago con la vaca igualada...
    ordago_desesperado: float = 0.9  # ...y cuánto baja ese umbral cuando la vaca va mal
    agresividad: float = 1.0  # multiplica el tamaño de los envites
    farol: float = 0.07  # probabilidad base de ir de farol
    pasar_para_querer: float = 0.25  # probabilidad de pasar con mano muy buena
    prudencia: float = 0.0  # ventaja mínima (en probabilidad de vaca) para querer
    dejar_al_companero: bool = True  # si el compañero habla después, querer solo con mano propia
    dispersion_vaca: float = 9.0  # incertidumbre del modelo de vaca (más = el marcador pesa menos)
    leer_rivales: bool = True  # aprender durante la partida cuánto va de farol cada rival

    def umbral_ordago(self, prob_vaca: float) -> float:
        """Probabilidad de ganar el lance que hace falta para echar órdago.

        Con la vaca igualada hace falta mucha mano; cuanto peor va la vaca, menos (si la vaca
        está casi perdida, un órdago es la mejor forma de darle la vuelta).
        """
        umbral = self.ordago_igualado - self.ordago_desesperado * (0.5 - prob_vaca)
        return min(0.99, max(0.5, umbral))


ESTILOS: dict[str, Estilo] = {
    "equilibrado": Estilo(),
    "agresivo": Estilo(
        "agresivo", corte=0.56, envite=0.58, subida=0.75, ordago_igualado=0.9,
        agresividad=1.5, farol=0.14, pasar_para_querer=0.15,
    ),
    "conservador": Estilo(
        "conservador", corte=0.68, envite=0.72, subida=0.88, ordago_igualado=0.98,
        ordago_desesperado=0.7, agresividad=0.7, farol=0.03, pasar_para_querer=0.3,
        prudencia=0.01,
    ),
}


class HeuristicBot(Bot):
    """Bot de reglas que lee la mesa. ``estilo`` es un :class:`Estilo` o su nombre."""

    tipo = "reglas"
    descripcion = "Lee la mesa, calcula probabilidades y juega según el marcador, con faroles"

    def __init__(
        self,
        nombre: str | None = None,
        seed: int | None = None,
        estilo: Estilo | str = "equilibrado",
        modelo: ModeloRival | None = None,
    ) -> None:
        super().__init__(nombre, seed)
        self.estilo = ESTILOS[estilo] if isinstance(estilo, str) else estilo
        self.modelo = modelo or ModeloRival()
        self.lector = LectorRivales()
        self.razon = ""

    def on_hand_end(self, observation: Observation) -> None:
        if self.estilo.leer_rivales and observation.manos_jugadas:
            self.lector.registrar(observation.manos_jugadas[-1], observation.asiento)

    def modelos_rivales(self, asiento: int) -> dict[int, ModeloRival]:
        """Modelo de cada uno de los otros jugadores (con lo aprendido de ellos)."""
        if not self.estilo.leer_rivales:
            return {}
        return self.lector.modelos(self.modelo, asiento)

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        if observation.fase is Fase.MUS:
            accion, razon = self._mus(observation)
        elif observation.fase is Fase.DESCARTE:
            accion, razon = self._descarte(observation, legal_actions)
        elif observation.apuesta.pareja_apostadora is None:
            accion, razon = self._abrir(observation, legal_actions)
        else:
            accion, razon = self._responder(observation, legal_actions)
        if accion not in legal_actions:  # red de seguridad: nunca una jugada ilegal
            accion = next(
                (a for a in (Paso(), NoQuiero(), Quiero()) if a in legal_actions),
                legal_actions[0],
            )
            razon += " (corregida a una jugada legal)"
        self.razon = razon
        return accion

    # --- Mus y descartes -------------------------------------------------------------------

    def _mus(self, obs: Observation) -> tuple[Action, str]:
        percentil = PERCENTIL[indice_de(obs.cartas)]
        if PUNTOS[indice_de(obs.cartas)] == 31:
            return NoHayMus(), "corto: tengo la 31"
        umbral = self.estilo.corte
        if obs.asiento == obs.mano:
            umbral -= 0.03  # siendo mano gano los empates
        for evento in ronda_de_mus(obs.historial):
            if evento.asiento == obs.companero:
                umbral += 0.03  # mi compañero ha pedido mus: no lleva gran cosa
            elif evento.asiento is not None and pareja(evento.asiento) != obs.pareja:
                umbral -= 0.02  # los rivales piden mus: tampoco llevan gran cosa
        if obs.tantos[1 - obs.pareja] >= 30:
            umbral -= 0.04  # que los rivales no mejoren su mano
        if percentil >= umbral:
            return NoHayMus(), f"corto: mano del percentil {percentil:.0%} (umbral {umbral:.0%})"
        return Mus(), f"pido mus: mano del percentil {percentil:.0%} (umbral {umbral:.0%})"

    def _descarte(self, obs: Observation, legal: Sequence[Action]) -> tuple[Action, str]:
        opciones = [a for a in legal if isinstance(a, Descarte)]
        mejor = max(
            opciones,
            key=lambda d: (valor_tras_descarte(obs.cartas, d.cartas), -len(d.cartas)),
        )
        valor = valor_tras_descarte(obs.cartas, mejor.cartas)
        return mejor, f"descarto {len(mejor.cartas)}: la mano media que queda vale {valor:.2f}"

    # --- Apuestas --------------------------------------------------------------------------

    def _abrir(self, obs: Observation, legal: Sequence[Action]) -> tuple[Action, str]:
        """Nadie ha envidado todavía en este lance."""
        e = self.estilo
        mesa = _Mesa(obs, self.modelo, e.dispersion_vaca, self.modelos_rivales(obs.asiento))
        p = mesa.p
        pv = mesa.vaca(0, 0)
        despues = obs.apuesta.por_hablar[1:]

        umbral_ordago = e.umbral_ordago(pv)
        if p >= umbral_ordago:
            return Ordago(), (f"órdago: gano el lance con {p:.0%} y la vaca va {pv:.0%} "
                              f"(con esa vaca echo órdago desde {umbral_ordago:.0%})")

        rival_detras = any(pareja(s) != obs.pareja for s in despues)
        if p >= 0.85 and rival_detras and self.rng.random() < e.pasar_para_querer:
            return Paso(), f"paso para querer: gano con {p:.0%} y detrás habla un rival"

        if p >= e.envite:
            return self._cantidad(p)

        ultimo = not despues
        if self.rng.random() < e.farol * (2.5 if ultimo else 0.6):
            return Envido(), (f"farol: solo gano con {p:.0%}"
                              + (", pero hablo el último" if ultimo else ""))
        return Paso(), f"paso: gano el lance con {p:.0%}"

    def _cantidad(self, p: float) -> tuple[Action, str]:
        """Cuánto envidar, una vez decidido que se envida: más cuanta más mano, con variación."""
        e = self.estilo
        tantos = 2
        if p >= e.envite + 0.1:
            tantos = round(2 + e.agresividad * (p - e.envite - 0.1) * 25)
            tantos += self.rng.choice((-1, 0, 0, 1))
        tantos = max(2, min(_CANTIDADES[-1], tantos))
        return Envido(tantos), f"envido {tantos}: gano el lance con {p:.0%}"

    def _responder(self, obs: Observation, legal: Sequence[Action]) -> tuple[Action, str]:
        """El rival ha envidado, reenvidado o echado órdago."""
        e = self.estilo
        ap = obs.apuesta
        # Si mi compañero contesta después, solo quiero con lo que puedo ganar yo solo:
        # si él tiene mano, ya querrá él.
        companero_detras = e.dejar_al_companero and obs.companero in ap.por_hablar[1:]
        mesa = _Mesa(obs, self.modelo, e.dispersion_vaca, self.modelos_rivales(obs.asiento),
                     incluir_companero=not companero_detras)
        p = mesa.p
        quien = "yo solo" if companero_detras else "mi pareja"

        # Si no quiero, el rival cobra el deje ya y, en pares/juego/punto, sus bonus.
        u_no = mesa.vaca(0, ap.deje + mesa.bonus_rival)

        if ap.ordago:
            if p > u_no + e.prudencia:
                return Quiero(), (f"quiero el órdago: {quien} gano con {p:.0%} y, sin "
                                  f"arriesgar, la vaca iría {u_no:.0%}")
            return NoQuiero(), (f"no quiero el órdago: {quien} gano con {p:.0%} y, sin "
                                f"arriesgar, la vaca va {u_no:.0%}")

        umbral_ordago = e.umbral_ordago(mesa.vaca(0, 0))
        if p >= umbral_ordago and Ordago() in legal:
            return Ordago(), f"órdago: {quien} gano con {p:.0%} (umbral {umbral_ordago:.0%})"
        reenvidos = [x.tantos for x in legal if isinstance(x, Reenvido)]
        if p >= e.subida and reenvidos:
            tantos = min(max(2, ap.tantos), _CANTIDADES[-1], max(reenvidos))
            return Reenvido(tantos), f"reenvido {tantos}: {quien} gano con {p:.0%}"

        # Querer o no: querer gana o pierde la apuesta (y los bonus); no querer regala el deje.
        u_quiero = mesa.querido(ap.tantos, p)
        if u_quiero - e.prudencia > u_no:
            return Quiero(), (f"quiero: {quien} gano con {p:.0%} (vaca {u_quiero:.0%} "
                              f"queriendo, {u_no:.0%} sin querer)")
        return NoQuiero(), (f"no quiero: {quien} gano solo con {p:.0%} (vaca {u_quiero:.0%} "
                            f"queriendo, {u_no:.0%} sin querer)")


#: Cantidades que el bot considera al envidar o reenvidar. Como un jugador real, no envida
#: cantidades enormes: para jugarse la vaca ya está el órdago.
_CANTIDADES = (2, 3, 4, 5, 6, 8, 10)


class _Mesa:
    """Lo que el bot calcula sobre el lance en curso para comparar sus opciones."""

    def __init__(
        self, obs: Observation, modelo: ModeloRival, dispersion_vaca: float = 9.0,
        modelos: dict[int, ModeloRival] | None = None, incluir_companero: bool = True,
    ) -> None:
        self.obs = obs
        self.dispersion_vaca = dispersion_vaca
        self.creencias = Creencias.desde_observacion(obs, modelo, modelos)
        self.participantes = obs.apuesta.participantes
        self.p = prob_ganar_lance(
            obs.lance, obs.asiento, obs.cartas, obs.mano, self.participantes, self.creencias,
            incluir_companero,
        )
        self.bonus_propio = self._bonus(obs.pareja)
        self.bonus_rival = self._bonus(1 - obs.pareja)
        self.propios = obs.tantos[obs.pareja]
        self.rivales = obs.tantos[1 - obs.pareja]

    def _bonus(self, p: int) -> float:
        o = self.obs
        return bonus_pareja(o.lance, p, o.asiento, o.cartas, self.participantes, self.creencias)

    def vaca(self, mas_propios: float, mas_rivales: float) -> float:
        """Probabilidad de ganar la vaca si cada pareja suma esos tantos."""
        return prob_vaca(
            self.propios + mas_propios, self.rivales + mas_rivales, self.dispersion_vaca
        )

    def querido(self, total: float, prob: float) -> float:
        """Probabilidad de vaca si se juega (a ver quién gana) una apuesta de ``total``."""
        return (prob * self.vaca(total + self.bonus_propio, 0)
                + (1 - prob) * self.vaca(0, total + self.bonus_rival))


def estilo_con(nombre: str = "equilibrado", **cambios: float) -> Estilo:
    """Copia de un estilo con algunos parámetros cambiados (útil para ajustar el bot)."""
    return replace(ESTILOS[nombre], **cambios)
