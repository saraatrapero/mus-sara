"""Por qué ha hecho cada bot lo que ha hecho, en castellano y para cualquier persona.

Se guarda una línea por decisión de bot durante la partida y solo se enseña **al terminar**
(en el resumen final): durante la partida delataría sus cartas. Usa lo que el propio bot
calculó (probabilidad de ganar el lance, valor esperado de cada opción) o, en el nivel
sencillo, la fuerza heurística de su mano y la regla que aplicó.
"""

from __future__ import annotations

from typing import Any

from musst.agents.base import Decision
from musst.engine.actions import Action, action_to_dict
from musst.engine.observation import Observation

LANCES = {
    "grande": "grande",
    "chica": "chica",
    "pares": "pares",
    "juego": "juego",
    "punto": "punto",
}
CON_ARTICULO = {
    "grande": "la grande",
    "chica": "la chica",
    "pares": "a pares",
    "juego": "el juego",
    "punto": "el punto",
}


def action_label(action: Action | dict[str, Any] | str) -> str:
    """«Envido 2», «Quiero», «Órdago»… a partir de una acción o de su etiqueta (BET_2)."""
    if isinstance(action, str):
        kind, _, amount = action.partition("_")
        if kind == "ACCEPT" and amount == "NO_LOSE":
            kind, amount = "ACCEPT_NO_LOSE", ""
        data: dict[str, Any] = {"type": kind.lower()}
        if amount.isdigit():
            data["amount"] = int(amount)
    elif isinstance(action, dict):
        data = action
    else:
        data = action_to_dict(action)
    kind = str(data.get("type", ""))
    qty = data.get("amount")
    return {
        "pass": "Paso",
        "bet": f"Envido {qty}",
        "raise": f"Subo {qty}",
        "accept": "Quiero",
        "accept_no_lose": "Quiero",
        "reject": "No quiero",
        "ordago": "¡Órdago!",
        "mus": "Mus",
        "cut": "Corto el mus",
        "discard": "Descarto",
    }.get(kind, kind)


def _pct(p: float) -> str:
    return f"{round(p * 100)} %"


def _tantos(x: float) -> str:
    s = f"{x:+.1f}".replace(".", ",")
    return f"{s} tantos"


def _from_decision(obs: Observation, decision: Decision) -> str:
    """Razón de un bot por agentes (medio, profesional, matemático)."""
    f = decision.evidence
    lance = LANCES.get(obs.phase, obs.phase)
    parts: list[str] = []
    if obs.phase == "mus":
        return (
            "Corta el mus: juzga que su mano es buena para jugarla tal como está."
            if decision.action.type == "cut"
            else "Pide mus: espera mejorar su mano cambiando cartas."
        )
    p = f.get("p_win")
    if p is not None:
        parts.append(
            f"Calcula que gana {CON_ARTICULO.get(obs.phase, lance)} con un {_pct(p)} de probabilidad"
        )
    p_acc = f.get("p_win_if_accept")
    if p_acc is not None and decision.action.type in ("bet", "raise", "ordago"):
        parts.append(f"si se lo quieren, gana el {_pct(p_acc)} de las veces")
    alts = sorted(decision.alternatives, key=lambda a: a.ev, reverse=True)
    chosen = action_label(decision.action)
    if len(alts) >= 2:
        best = alts[0]
        other = next((a for a in alts if a.label() != best.label()), None)
        if best.label() == _label_of(decision.action) and other is not None:
            parts.append(
                f"«{chosen}» le da {_tantos(best.ev)} de media frente a "
                f"{_tantos(other.ev)} de «{action_label(other.label())}»"
            )
        elif decision.action.type in ("bet", "raise") and (p_acc is not None and p_acc < 0.35):
            parts.append(
                "va de farol: si se lo quieren lo normal es perder, pero cuenta con que no se "
                "lo quieran y así se lleva el tanto"
            )
        else:  # ha elegido otra (prudencia, riesgo, variar el juego)
            parts.append(
                f"aunque en tantos rentaba algo más «{action_label(best.label())}», eligió esta: "
                "el bot pesa el riesgo y a veces varía su juego para no ser previsible"
            )
    if decision.action.type == "ordago":
        parts.append("se juega la partida entera porque está casi seguro de ganarla")
    if not parts:
        return decision.narrative or "Elige la opción con más valor esperado."
    text = "; ".join(parts) + "."
    return text[0].upper() + text[1:]


def _label_of(action: Action) -> str:
    d = action_to_dict(action)
    return str(d["type"]).upper() + (f"_{d['amount']}" if "amount" in d else "")


def _from_simple(obs: Observation, info: dict[str, Any]) -> str:
    """Razón del nivel sencillo: fuerza heurística de la mano y la regla que aplicó."""
    lance = LANCES.get(obs.phase, obs.phase)
    s = info.get("fuerza")
    rule = info.get("regla", "")
    if s is None:
        return (rule[:1].upper() + rule[1:] + ".") if rule else "Juega por intuición."
    lance_txt = "pares" if obs.phase == "pares" else CON_ARTICULO.get(obs.phase, lance)
    base = f"Su mano vale {round(s * 100)}/100 para {lance_txt}"
    return f"{base}: {rule}." if rule else base + "."


AGENTES = {
    "cartas": "Cartas (fuerza de su mano)",
    "probabilidad": "Probabilidad (P(ganar el lance))",
    "marcador": "Marcador (cuánto vale cada tanto según el tanteo)",
    "conteo": "Conteo (cartas ya vistas)",
    "comportamiento": "Comportamiento (cómo juega cada rival)",
    "farol": "Farol (si el rival puede ir de farol)",
    "pareja": "Pareja (lo que puede hacer su compañero)",
    "bayesiano": "Bayesiano (actualiza con lo que hacen los demás)",
    "analista": "Analista (cálculo exacto de los lances)",
    "evaluador": "Evaluador (valor esperado de cada opción)",
    "juez_matematico": "Juez matemático (P(ganar la partida))",
    "juez": "Juez (elige con el riesgo del nivel)",
    "estrategia": "Estrategia (genera las opciones)",
}


def _method(bot: Any, decision: Decision | None) -> str:
    """Método de cálculo del bot, en una frase."""
    if decision is not None and isinstance(decision.math, dict):
        m = decision.math.get("metodo", {})
        n = m.get("repartos")
        bayes = (
            "con Bayes sobre lo que han hecho los rivales"
            if m.get("decisiones_rivales", "").startswith("Bayes")
            else "sin evidencia de los rivales (a priori)"
        )
        return (
            f"Muestreo exacto de repartos{f' ({n})' if n else ''} {bayes}, y decide por "
            "P(ganar la partida)"
        )
    level = getattr(getattr(bot, "level", None), "name", None)
    samples = getattr(getattr(bot, "level", None), "samples", None)
    if level == "medio":
        return f"Monte Carlo: simula unos {samples} repartos posibles de las cartas que no ve"
    if level == "profesional":
        return (
            f"Monte Carlo con unos {samples} repartos, ponderados por lo que sabe de cada "
            "rival, y valor esperado"
        )
    if decision is not None:
        return "Valor esperado de cada opción"
    return "Heurística: puntúa su mano de 0 a 100 y aplica reglas fijas"


def explain_move(obs: Observation, action: Action, bot: Any) -> dict[str, Any] | None:
    """Una línea «qué hizo y por qué» para el resumen final. ``None`` si no aporta nada."""
    if action.type == "discard":
        return None
    decision = getattr(bot, "last_decision", None)
    reason: str
    used = decision if isinstance(decision, Decision) and decision.action == action else None
    agentes = [AGENTES.get(a, a) for a in used.agents_consulted] if used is not None else []
    if used is not None:
        reason = _from_decision(obs, used)
    elif isinstance(getattr(bot, "last_reason", None), dict):
        reason = _from_simple(obs, bot.last_reason)
    else:
        reason = "Decisión por reglas fijas del bot."
    return {
        "seat": obs.seat,
        "round": obs.round_no,
        "lance": obs.phase,
        "action": action_label(action),
        "type": action.type,
        "reason": reason,
        "metodo": _method(bot, used),
        "agentes": agentes,
    }
