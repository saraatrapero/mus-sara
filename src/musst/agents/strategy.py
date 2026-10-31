"""Agente de estrategia (genera candidatas con su valor esperado) y Agente Juez (elige)."""

from __future__ import annotations

import random

from musst.agents.base import AgentContext, Decision, ScoredAction
from musst.agents.specialists import current_lance_bets
from musst.bots.toolkit import (
    discard_options,
    hand_value,
    keep_heuristic_discard,
    sample_world,
    unseen_cards,
)
from musst.engine.actions import (
    AcceptAction,
    AcceptNoLoseAction,
    Action,
    BetAction,
    CutMusAction,
    DiscardAction,
    MusAction,
    OrdagoAction,
    PassAction,
    RaiseAction,
    RejectAction,
)
from musst.engine.cards import Card
from musst.engine.evaluation import pairs, total_points

ACCEPT_FLOOR_BET = 0.35
"""Probabilidad mínima de que el rival acepte un envite (no conocemos su política)."""
ACCEPT_FLOOR_ORDAGO = 0.3
"""Probabilidad mínima de que el rival acepte un órdago: los faroles también se pagan."""
BLUFF_P = 0.35
"""Por debajo de esta P(ganar el lance), envidar es un farol: solo se hace a propósito, con la
frecuencia de farol del nivel (``LevelConfig.bluff_rate``), nunca porque las cuentas salgan."""
ORDAGO_SURE = 0.8
"""Un órdago se echa casi seguro de ganarlo (P(ganar si lo quieren) ≥ 0.8)…"""
ORDAGO_DESPERATE = 0.5
"""…o por desesperación: cuando el agente de marcador baja su umbral por debajo de este valor
(vamos perdiendo y el rival está a punto de ganar), basta con superar ese umbral."""

ORDAGO_LEADING = 0.85
"""Yendo por delante en el marcador no hay prisa: solo se echa o se ve (acepta) un órdago con
P(ganarlo) ≥ 0.85. Arriesgar la partida entera estando ganando es regalarla."""

RAISE_ACCEPT = 0.7
"""Probabilidad supuesta de que quien envidó acepte una subida."""
RAISE_ESCALATION_DECAY = 0.4
"""Cada envite rival adicional multiplica su probabilidad de retirarse por este factor."""
RESPONSE_ORDAGO_ACCEPT = 0.4
"""Probabilidad mínima de que quien envidó acepte un órdago como respuesta."""


class StrategyAgent:
    """Genera acciones candidatas legales y estima su valor esperado en tantos."""

    name = "estrategia"

    def candidates(self, ctx: AgentContext) -> list[ScoredAction]:
        obs = ctx.obs
        types = obs.legal_types()
        p_win = ctx.estimate(
            "probabilidad", "p_win", ctx.estimate("cartas", f"strength_{ctx.lance}").value
        )
        p = p_win.value
        utility = ctx.estimate("marcador", "point_utility", 1.0).value
        game_value = ctx.estimate("marcador", "game_value", 40.0).value
        a_bet = max(ACCEPT_FLOOR_BET, ctx.estimate("probabilidad", "p_accept_bet", 0.4).value)
        p_bet = ctx.estimate("probabilidad", "p_win_if_accept_bet", p).value
        a_ord = max(
            ACCEPT_FLOOR_ORDAGO, ctx.estimate("probabilidad", "p_accept_ordago", 0.15).value
        )
        p_ord = ctx.estimate("probabilidad", "p_win_if_accept_ordago", p).value
        bonus = self._play_bonus(ctx)
        paso = 1.0 if ctx.lance in ("grande", "chica") else 0.0
        out: list[ScoredAction] = []
        factors = {"p_win": p, "confidence": p_win.confidence, "p_accept_bet": a_bet}

        def add(action: Action, ev: float, risk: float, **extra: float) -> None:
            out.append(ScoredAction(action, ev * utility, risk, {**factors, **extra}))

        bluff_rate = float(ctx.config.get("bluff_rate", 0.1))
        may_bluff = p >= BLUFF_P or ctx.rng.random() < bluff_rate
        ordago_threshold = ctx.estimate("marcador", "ordago_threshold", 0.55).value
        leading = obs.score[obs.team] > obs.score[1 - obs.team]
        sure = float(ctx.config.get("ordago_sure", ORDAGO_SURE))
        if leading:
            ordago_ok = p_ord >= max(sure, ORDAGO_LEADING)
        else:
            ordago_ok = p_ord >= sure or (
                ordago_threshold < ORDAGO_DESPERATE and p_ord >= ordago_threshold
            )
        if "pass" in types:  # lance abierto
            add(PassAction(), p * (bonus + paso), 0.0)
            spec = obs.spec("bet")
            assert spec is not None
            amounts = sorted({spec.min_amount or 2, 4, 8}) if may_bluff else []
            if p < BLUFF_P:
                amounts = amounts[:1]  # un farol, de 2: barato si lo cazan
            for amount in amounts:
                if amount > (spec.max_amount or amount):
                    continue
                # Cuanto mayor el envite, más fuerte hace falta estar para quererlo.
                a = a_bet * max(0.3, 1 - (amount - 2) / 12)
                pa = p_bet if amount <= 2 else p_bet * max(0.6, 1 - (amount - 2) / 20)
                ev = (1 - a) * (1 + p * bonus) + a * ((2 * pa - 1) * amount + pa * bonus)
                add(BetAction(amount), ev, a * amount * (pa * (1 - pa)) ** 0.5, p_win_if_accept=pa)
            if ordago_ok:
                ev_ord = (1 - a_ord) * (1 + p * bonus) + a_ord * (2 * p_ord - 1) * game_value
                add(OrdagoAction(), ev_ord, a_ord * game_value, p_win_if_accept=p_ord)
            return out

        bet = obs.current_bet
        assert bet is not None
        accept_type = (
            "accept"
            if "accept" in types
            else "accept_no_lose"
            if "accept_no_lose" in types
            else None
        )
        p_bluff = ctx.estimate("farol", "p_bluff", 0.0).value
        accept_action: Action = AcceptAction() if accept_type == "accept" else AcceptNoLoseAction()
        if bet.is_ordago:
            threshold = ctx.estimate("marcador", "ordago_threshold", 0.55).value
            if leading:
                threshold = max(threshold, ORDAGO_LEADING)
            if accept_type:
                add(accept_action, (p - threshold) * game_value, game_value * 0.5, p_bluff=p_bluff)
            # Se compara contra rechazar (referencia 0): aceptar si P(ganar) supera el umbral
            # que fija el agente de marcador.
            add(RejectAction(), 0.0, 0.0)
            return out
        stake = bet.stake
        if accept_type:
            add(
                accept_action,
                (2 * p - 1) * stake + p * bonus,
                stake * (p * (1 - p)) ** 0.5,
                p_bluff=p_bluff,
            )
        add(RejectAction(), self._reject_ev(ctx, -bet.previous, p), 0.0)
        spec = obs.spec("raise")
        if spec is not None and may_bluff:
            for extra in sorted({spec.min_amount or 2, 5}):
                if extra > (spec.max_amount or extra):
                    continue
                total = stake + extra
                # Quien ya envidó ha mostrado fuerza: suele mantenerse ante una subida.
                # ``p`` ya está condicionada a su envite (ponderación del agente de probabilidad).
                # Ante un envite, los mundos están ponderados por la fuerza de quien envidó:
                # P(acepta la subida) y P(ganar | la acepta) salen del mismo Monte Carlo.
                a = max(a_bet, self._raise_acceptance(ctx))
                ev = (1 - a) * stake + a * (2 * p_bet - 1) * total + p * bonus
                add(RaiseAction(extra), ev, a * total * (p_bet * (1 - p_bet)) ** 0.5)
        if "ordago" in types and ordago_ok:
            a = max(a_ord, RESPONSE_ORDAGO_ACCEPT)
            ev = (1 - a) * stake + a * (2 * p_ord - 1) * game_value
            add(OrdagoAction(), ev, a * game_value)
        return out

    def _raise_acceptance(self, ctx: AgentContext) -> float:
        """Cuantas más veces ha envidado ya el rival en el lance, menos probable que se retire."""
        opp_bets = sum(n for s, n in current_lance_bets(ctx).items() if s % 2 != ctx.obs.team)
        return 1 - (1 - RAISE_ACCEPT) * RAISE_ESCALATION_DECAY ** max(0, opp_bets - 1)

    def _reject_ev(self, ctx: AgentContext, base: float, p: float) -> float:
        """Si mi compañero aún puede querer, rechazar no cierra el envite."""
        if ctx.estimate("pareja", "partner_can_answer", 0.0).value > 0:
            partner_accept = ctx.estimate("pareja", "partner_accept", 0.45).value
            bet = ctx.obs.current_bet
            stake = bet.stake if bet else 0
            return (1 - partner_accept) * base + partner_accept * (2 * p - 1) * stake
        return base

    def _opponent_acceptance(self, ctx: AgentContext) -> float:
        values = [
            ctx.estimate("comportamiento", f"acceptance_rate_{s}", 0.45).value
            for s in ctx.obs.opponents
        ]
        # Basta con que uno de los dos quiera (FEM VI.4).
        return 1 - (1 - values[0]) * (1 - values[1])

    def _play_bonus(self, ctx: AgentContext) -> float:
        """Tantos de jugada que se cobran si se gana el lance (pares/juego/punto).

        Con ``team_bonus`` se usa la estimación del agente de probabilidad para toda la pareja
        (la jugada del compañero también cobra); si no, solo la propia mano."""
        if ctx.config.get("team_bonus") and "probabilidad" in ctx.reports:
            est = ctx.reports["probabilidad"].estimates.get("team_bonus")
            if est is not None:
                return est.value
        hand = ctx.obs.hand
        if ctx.lance == "pares":
            return float(int(pairs(hand).kind))
        if ctx.lance == "juego":
            return 3.0 if total_points(hand) == 31 else 2.0
        if ctx.lance == "punto":
            return 1.0
        return 0.0

    def _p_game(self, ctx: AgentContext, p_lance: float) -> float:
        return p_lance


class Judge:
    """Compara alternativas con valor esperado ajustado por riesgo e incertidumbre."""

    name = "juez"

    def __init__(self, risk_aversion: float = 0.3, noise: float = 0.0) -> None:
        self.risk_aversion = risk_aversion
        self.noise = noise

    def decide(self, ctx: AgentContext, candidates: list[ScoredAction]) -> Decision:
        legal = ctx.obs.legal_types()
        valid = [c for c in candidates if c.action.type in legal]
        if not valid:  # el agente de reglas no deja pasar nada ilegal
            fallback = ctx.obs.legal_actions[0].default()
            return Decision(fallback, 0.0, {}, tuple(ctx.reports), narrative="sin candidatas")
        conf = ctx.estimate("probabilidad", "p_win", 0.5).confidence
        appetite = ctx.estimate("marcador", "risk_appetite", 0.5).value
        lam = self.risk_aversion * (1.5 - appetite)

        def score(c: ScoredAction) -> float:
            return c.ev - lam * c.risk * (1 - conf)

        ranked = sorted(valid, key=score, reverse=True)
        chosen = ranked[0]
        if (
            self.noise
            and len(ranked) > 1
            and ctx.rng.random() < self.noise
            and abs(score(ranked[0]) - score(ranked[1])) < 1.5
        ):
            chosen = ranked[1]
        margin = score(chosen) - (score(ranked[1]) if len(ranked) > 1 else score(chosen) - 1)
        confidence = max(0.05, min(0.99, 0.5 * conf + 0.5 * min(1.0, abs(margin) / 3)))
        narrative = "; ".join(f"EV({c.label()})={c.ev:+.2f}" for c in ranked[:3])
        return Decision(
            chosen.action,
            confidence,
            {**chosen.factors, "ev": chosen.ev, "risk": chosen.risk},
            tuple(ctx.reports),
            tuple(ranked),
            narrative,
        )


class MusPlanner:
    """Decisiones de mus y descarte por valor de la mano (con muestreo de reposiciones)."""

    def __init__(self, cut_threshold: float = 0.42, draws: int = 10) -> None:
        self.cut_threshold = cut_threshold
        self.draws = draws

    def mus(self, ctx: AgentContext) -> Action:
        if "mus" not in ctx.obs.legal_types():
            return CutMusAction()
        value = hand_value(ctx.obs.hand)
        threshold = self.cut_threshold + 0.03 * ctx.obs.mus_rounds
        mine, theirs = ctx.obs.score[ctx.obs.team], ctx.obs.score[1 - ctx.obs.team]
        if theirs > mine + 10:  # por detrás, se busca mejor mano
            threshold += 0.05
        return CutMusAction() if value >= threshold else MusAction()

    def discard(self, ctx: AgentContext) -> Action:
        hand = ctx.obs.hand
        if self.draws <= 0:
            return DiscardAction(keep_heuristic_discard(hand))
        pool = unseen_cards(ctx.obs)
        best: tuple[float, tuple[Card, ...]] | None = None
        rng: random.Random = ctx.rng
        for option in discard_options(hand):
            keep = [c for c in hand if c not in option]
            total = 0.0
            for _ in range(self.draws):
                new = keep + rng.sample(pool, len(option))
                total += hand_value(new)
            avg = total / self.draws
            if best is None or avg > best[0]:
                best = (avg, option)
        assert best is not None
        return DiscardAction(best[1])


__all__ = ["Judge", "MusPlanner", "StrategyAgent", "hand_value", "sample_world"]
