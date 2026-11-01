"""Agentes especialistas: cartas, probabilidad, comportamiento, farol, marcador y pareja."""

from __future__ import annotations

import math

from musst.agents.base import Agent, AgentContext, AgentReport, Estimate
from musst.bots.toolkit import (
    LANCE_NAMES,
    hand_strength,
    lance_winner,
    sample_world,
    unseen_cards,
)
from musst.engine.cards import Card
from musst.engine.config import RulesConfig
from musst.engine.evaluation import play_points
from musst.learning.extract import STRONG, WEAK
from musst.learning.player_model import PRIORS, score_context

DEFAULT_RULES = RulesConfig()
BETTING_EVENTS = {"BetPlaced", "BetRaised", "OrdagoDeclared"}


def current_lance_bets(ctx: AgentContext) -> dict[int, int]:
    """Número de envites/subidas de cada asiento en el lance actual de esta jugada."""
    counts: dict[int, int] = {}
    for e in ctx.obs.history:
        if (
            e["round"] == ctx.obs.round_no
            and e["kind"] in BETTING_EVENTS
            and e["payload"].get("lance") == ctx.lance
        ):
            counts[e["actor"]] = counts.get(e["actor"], 0) + 1
    return counts


BET_THRESHOLD = 0.7
"""Fuerza a partir de la cual se supone que un jugador envida "de verdad"."""
BET_THRESHOLD_STEP = 0.1
"""Cada subida adicional exige más fuerza."""
BET_SHARPNESS = 0.05
AGGRESSION_THRESHOLD_SHIFT = 0.8
"""Cuánto baja el umbral de envite por cada punto de agresividad por encima del prior."""


def bet_likelihood(
    strength: float, bluff: float, n_bets: int, threshold: float = BET_THRESHOLD
) -> float:
    """P(observar ``n_bets`` envites | fuerza de la mano).

    Mezcla de "farol" (probabilidad ``bluff`` sea cual sea la mano) y "envite de valor"
    (sigmoide alrededor de un umbral que sube con cada reenvite).
    """
    tau = threshold + BET_THRESHOLD_STEP * (n_bets - 1)
    value_bet = 1 / (1 + math.exp(-(strength - tau) / BET_SHARPNESS))
    return max(0.02, bluff) ** n_bets * 0.5 + (1 - bluff) * value_bet


class CardAgent(Agent):
    """Fuerza de la propia mano en cada lance (heurística explicable)."""

    name = "cartas"

    def analyze(self, ctx: AgentContext) -> AgentReport:
        report = AgentReport(self.name)
        for lance in LANCE_NAMES:
            report.estimates[f"strength_{lance}"] = Estimate(
                hand_strength(ctx.obs.hand, lance), 1.0
            )
        return report


class BehaviourAgent(Agent):
    """Perfil contextual de los rivales a partir del PlayerModel (memoria larga + sesión)."""

    name = "comportamiento"

    def analyze(self, ctx: AgentContext) -> AgentReport:
        report = AgentReport(self.name)
        obs = ctx.obs
        for seat in obs.opponents:
            pid = ctx.player_ids.get(seat)
            their = obs.score[seat % 2]
            mine = obs.score[obs.team]
            sctx = score_context(their, mine, obs.target)
            for metric in (
                "aggression",
                "bluff_frequency",
                "acceptance_rate",
                "raise_rate",
                "bet_with_strong",
                "bet_with_weak",
            ):
                if ctx.learner is None or pid is None:
                    value, conf = PRIORS[metric], 0.0
                else:
                    value, conf = ctx.learner.blended(pid, metric, ctx.lance, sctx)
                report.estimates[f"{metric}_{seat}"] = Estimate(value, conf)
        return report


def learned_bet_likelihood(strength: float, with_weak: float, with_strong: float) -> float:
    """P(envida | fuerza) aprendida del jugador: interpola entre lo que hace con mano floja y
    con mano buena (manos enseñadas al final de cada jugada, FEM VII.9)."""
    t = max(0.0, min(1.0, (strength - WEAK) / (STRONG - WEAK)))
    return max(0.02, with_weak + (with_strong - with_weak) * t)


READ_EVENTS = {
    "Passed": "pass",
    "BetPlaced": "bet",
    "BetRaised": "bet",
    "OrdagoDeclared": "bet",
    "BetAccepted": "accept",
    "OrdagoAccepted": "accept",
    "BetRejected": "reject",
}
LIKELIHOOD_FLOOR = 0.12
"""Nadie juega de forma perfectamente predecible (tapados, faroles, errores)."""


def action_likelihood(kind: str, strength: float, bluff: float = 0.15) -> float:
    """P(observar esa acción | fuerza de su mano en ese lance). Suave, con suelo."""
    value_bet = 1 / (1 + math.exp(-(strength - BET_THRESHOLD) / 0.08))
    if kind == "bet":
        p = bluff * 0.5 + (1 - bluff) * value_bet
    elif kind == "pass":
        p = 1 - (bluff * 0.5 + (1 - bluff) * value_bet)
    elif kind == "accept":
        p = 1 / (1 + math.exp(-(strength - 0.55) / 0.1))
    else:  # reject
        p = 1 - 1 / (1 + math.exp(-(strength - 0.55) / 0.1))
    return max(LIKELIHOOD_FLOOR, p)


def round_reads(ctx: AgentContext) -> list[tuple[int, str, str]]:
    """(asiento, lance, tipo) de todo lo que han hecho los demás en esta jugada."""
    out = []
    for e in ctx.obs.history:
        kind = READ_EVENTS.get(e["kind"])
        if kind and e["round"] == ctx.obs.round_no and e["actor"] not in (None, ctx.obs.seat):
            out.append((e["actor"], e["payload"].get("lance", ""), kind))
    return out


def team_play_value(lance: str, world: dict[int, tuple[Card, ...]], team: int) -> float:
    """Tantos de jugada que cobra una pareja al ganar el lance [CONVENCIÓN del motor]."""
    if lance not in ("pares", "juego", "punto"):
        return 0.0
    return float(play_points(lance, (world[team], world[team + 2]), DEFAULT_RULES))


class CountingAgent(Agent):
    """Conteo: cartas que ya no pueden tener los demás y cuántas cartas pidió cada uno.

    En el Mus se baraja la baraja entera en cada jugada y los descartes ajenos van boca abajo,
    así que lo que se puede contar es: mis cartas, mis descartes (salvo que se rebaraje) y el
    número de cartas que pide cada jugador. Pedir pocas cartas indica que se guardaba buena mano.
    """

    name = "conteo"

    def analyze(self, ctx: AgentContext) -> AgentReport:
        obs = ctx.obs
        report = AgentReport(self.name)
        asked: dict[int, int] = {}
        for e in obs.history:
            if e["round"] != obs.round_no:
                continue
            if e["kind"] == "CardsDiscarded" and "count" in e["payload"]:
                seat = e["payload"]["seat"]
                asked[seat] = asked.get(seat, 0) + e["payload"]["count"]
        unseen = len(unseen_cards(obs))
        report.estimates["unseen_cards"] = Estimate(float(unseen), 1.0)
        for seat, n in asked.items():
            report.estimates[f"asked_{seat}"] = Estimate(float(n), 1.0)
        if asked:
            report.notes.append(
                "Cartas pedidas: "
                + ", ".join(f"asiento {s}: {n}" for s, n in sorted(asked.items()))
            )
        return report


def discard_weight(strength: float, asked: float | None) -> float:
    """Peso de un mundo según cuántas cartas pidió el jugador (1 = guardaba casi todo)."""
    if asked is None:
        return 1.0
    kept = max(0.0, 4.0 - asked) / 3.0  # 1 si pidió una carta, 0 si pidió cuatro
    return max(0.2, 1.0 + 0.8 * kept * (strength - 0.5))


class ProbabilityAgent(Agent):
    """Probabilidades del lance por Monte Carlo condicionado a la información pública.

    Además de P(ganar), estima la **selección adversa**: un rival solo acepta (o sube) con
    mano fuerte, así que se calcula P(acepta) y P(ganar | acepta) para un envite normal y
    para un órdago. Cada mundo muestreado se pondera por la verosimilitud de los envites
    rivales ya observados: P(envite | fuerza) ≈ fuerza si es fuerte y P(farol) si es débil.
    """

    name = "probabilidad"

    def thresholds(self, ctx: AgentContext) -> tuple[float, float]:
        """Fuerza mínima con la que se supone que el rival acepta un envite / un órdago."""
        if "comportamiento" not in ctx.reports:
            return 0.55, 0.8
        acc = (
            sum(
                ctx.estimate("comportamiento", f"acceptance_rate_{s}", 0.45).value
                for s in ctx.obs.opponents
            )
            / 2
        )
        tau_bet = max(0.3, min(0.9, 0.55 - 0.6 * (acc - 0.45)))
        return tau_bet, min(0.95, tau_bet + 0.25)

    def bet_threshold(self, ctx: AgentContext, seat: int) -> float:
        """Umbral de envite del rival: un jugador más agresivo envida con manos peores."""
        if "comportamiento" not in ctx.reports:
            return BET_THRESHOLD
        aggr = ctx.estimate("comportamiento", f"aggression_{seat}", PRIORS["aggression"])
        shift = (aggr.value - PRIORS["aggression"]) * AGGRESSION_THRESHOLD_SHIFT * aggr.confidence
        return max(0.35, min(0.9, BET_THRESHOLD - shift))

    def analyze(self, ctx: AgentContext) -> AgentReport:
        obs = ctx.obs
        lance = ctx.lance
        report = AgentReport(self.name)
        if lance not in LANCE_NAMES:
            return report
        samples = int(ctx.config.get("samples_deep" if ctx.deep else "samples", 200))
        bets = {s: n for s, n in current_lance_bets(ctx).items() if s % 2 != obs.team}
        tau_bet, tau_ordago = self.thresholds(ctx)
        asked = {
            s: ctx.estimate("conteo", f"asked_{s}", -1).value
            for s in obs.opponents
            if "conteo" in ctx.reports
        }
        learned: dict[int, tuple[float, float, float]] = {}
        if "comportamiento" in ctx.reports:
            for s in bets:
                ws = ctx.estimate(
                    "comportamiento", f"bet_with_strong_{s}", PRIORS["bet_with_strong"]
                )
                ww = ctx.estimate("comportamiento", f"bet_with_weak_{s}", PRIORS["bet_with_weak"])
                learned[s] = (ww.value, ws.value, min(ws.confidence, ww.confidence))
        total = wins = 0.0
        acc_b = win_acc_b = acc_o = win_acc_o = 0.0
        bonus_sum = 0.0
        read_bets = ctx.config.get("read_bets", True)
        read_all = ctx.config.get("read_all", False)
        reads = round_reads(ctx) if read_all else []
        if read_all:
            bets = {}  # la lectura completa ya incluye los envites del lance actual
        for _ in range(samples):
            world = sample_world(obs, ctx.rng)
            w = 1.0
            for seat, n in (bets if read_bets else {}).items():
                strength = hand_strength(world[seat], lance)
                bluff = ctx.estimate(
                    "comportamiento", f"bluff_frequency_{seat}", PRIORS["bluff_frequency"]
                ).value
                default = bet_likelihood(strength, bluff, n, self.bet_threshold(ctx, seat))
                if seat in learned:
                    l_weak, l_strong, conf_l = learned[seat]
                    own = learned_bet_likelihood(strength, l_weak, l_strong) * default ** (n - 1)
                    w *= conf_l * own + (1 - conf_l) * default
                else:
                    w *= default
            for seat, rl, kind in reads:
                bluff = ctx.estimate(
                    "comportamiento", f"bluff_frequency_{seat}", PRIORS["bluff_frequency"]
                ).value
                w *= action_likelihood(kind, hand_strength(world[seat], rl), bluff)
            for seat, n_asked in asked.items():
                if n_asked >= 0:
                    w *= discard_weight(hand_strength(world[seat], lance), n_asked)
            winner = lance_winner(lance, world, obs.mano)
            won = winner is not None and winner % 2 == obs.team
            opp = max(hand_strength(world[s], lance) for s in obs.opponents)
            # Con los mundos ya ponderados por sus envites, "opp" representa también la
            # fuerza de quien envidó: sirve para estimar si aguantará una subida.
            total += w
            wins += w * won
            if won:
                bonus_sum += w * team_play_value(lance, world, obs.team)
            if opp >= tau_bet:
                acc_b += w
                win_acc_b += w * won
            if opp >= tau_ordago:
                acc_o += w
                win_acc_o += w * won
        p = wins / total if total else 0.0
        p_acc_b = win_acc_b / acc_b if acc_b else p
        p_acc_o = win_acc_o / acc_o if acc_o else p
        review = ctx.config.get("self_review")
        if review is not None:  # autocrítica: corrige con lo que de verdad pasó otras veces
            raw = p
            p = review.correct(lance, p)
            p_acc_b = review.correct(lance, p_acc_b)
            p_acc_o = review.correct(lance, p_acc_o)
            if abs(p - raw) >= 0.02:
                report.notes.append(
                    f"Autocrítica: corrijo P(ganar {lance}) de {raw:.2f} a {p:.2f} por partidas anteriores"
                )
        se = (p * (1 - p) / samples) ** 0.5
        conf = max(0.0, 1.0 - 4 * se)
        report.estimates["p_win"] = Estimate(p, conf, samples)
        report.estimates["team_bonus"] = Estimate(bonus_sum / wins if wins else 0.0, conf, samples)
        report.estimates["p_accept_bet"] = Estimate(acc_b / total if total else 0.0, conf, samples)
        report.estimates["p_win_if_accept_bet"] = Estimate(p_acc_b, conf, samples)
        report.estimates["p_accept_ordago"] = Estimate(
            acc_o / total if total else 0.0, conf, samples
        )
        report.estimates["p_win_if_accept_ordago"] = Estimate(p_acc_o, conf, samples)
        report.notes.append(f"P(ganar {lance}) = {p:.2f} con {samples} muestras")
        return report


class BluffAgent(Agent):
    """P(el rival que envida está faroleando), por Bayes. Probabilidades, no certezas."""

    name = "farol"

    def analyze(self, ctx: AgentContext) -> AgentReport:
        report = AgentReport(self.name)
        bet = ctx.obs.current_bet
        if bet is None or bet.bettor_team == ctx.obs.team:
            return report
        bettors = [s for s, _ in current_lance_bets(ctx).items() if s % 2 != ctx.obs.team]
        if not bettors:
            return report
        seat = bettors[-1]
        samples = 120
        weak = 0
        for _ in range(samples):
            world = sample_world(ctx.obs, ctx.rng)
            if hand_strength(world[seat], ctx.lance) < WEAK:
                weak += 1
        p_weak = weak / samples
        bluff = ctx.estimate("comportamiento", f"bluff_frequency_{seat}", PRIORS["bluff_frequency"])
        aggr = ctx.estimate("comportamiento", f"aggression_{seat}", PRIORS["aggression"])
        p_bet_strong = max(0.2, min(0.95, aggr.value * 2))
        num = bluff.value * p_weak
        den = num + p_bet_strong * (1 - p_weak)
        p_bluff = num / den if den > 0 else 0.0
        report.estimates["p_bluff"] = Estimate(p_bluff, bluff.confidence, bluff.n)
        report.notes.append(
            f"Estimación: {p_bluff:.0%} de probabilidad de que el asiento {seat} represente "
            "una mano más fuerte de la que tiene"
        )
        return report


class ScoreAgent(Agent):
    """Valor estratégico de los tantos según el marcador (no es lo mismo 5-5 que 38-35)."""

    name = "marcador"

    def analyze(self, ctx: AgentContext) -> AgentReport:
        obs = ctx.obs
        mine = obs.score[obs.team]
        theirs = obs.score[1 - obs.team]
        my_left = max(1, obs.target - mine)
        their_left = max(1, obs.target - theirs)
        # Apetito de riesgo: si el rival está a punto de entrar, arriesgar cuesta menos.
        risk_appetite = max(0.0, min(1.0, 0.5 + (my_left - their_left) / (2 * obs.target)))
        if their_left <= 5:
            risk_appetite = max(risk_appetite, 0.8)
        # Umbral para el órdago: más bajo cuanto peor vamos.
        ordago_threshold = max(0.3, min(0.75, 0.55 - (my_left - their_left) / (3 * obs.target)))
        if their_left <= 3:
            ordago_threshold = min(ordago_threshold, 0.4)
        report = AgentReport(self.name)
        report.estimates["risk_appetite"] = Estimate(risk_appetite, 1.0)
        report.estimates["ordago_threshold"] = Estimate(ordago_threshold, 1.0)
        report.estimates["game_value"] = Estimate(float(my_left + their_left), 1.0)
        report.estimates["point_utility"] = Estimate(1.0 + 3.0 / my_left, 1.0)
        return report


class PartnerAgent(Agent):
    """Coordinación con el compañero: ¿suele apoyar (aceptar) cuando yo no quiero?"""

    name = "pareja"

    def analyze(self, ctx: AgentContext) -> AgentReport:
        report = AgentReport(self.name)
        obs = ctx.obs
        bet = obs.current_bet
        pid = ctx.player_ids.get(obs.partner)
        if ctx.learner is not None and pid is not None:
            value, conf = ctx.learner.blended(pid, "acceptance_rate", ctx.lance)
        else:
            value, conf = PRIORS["acceptance_rate"], 0.0
        partner_can_answer = bet is not None and obs.partner in bet.responders[1:]
        report.estimates["partner_accept"] = Estimate(value, conf)
        report.estimates["partner_can_answer"] = Estimate(1.0 if partner_can_answer else 0.0, 1.0)
        return report
