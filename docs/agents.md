# Agentes de IA

Diseño completo: [design/06-agentes.md](design/06-agentes.md). Código: `src/musst/agents/`.

## Niveles

| Nivel | Clase | Técnica |
|---|---|---|
| Sencillo | `SimpleBot` | Heurísticas de fuerza de mano por lance; ruido del 15 % y faroles ocasionales (errores razonables) |
| Medio | `AgentBot("medio")` | Agentes de cartas, probabilidad (Monte Carlo, 150 muestras) y marcador |
| Profesional | `AgentBot("profesional")` | Todos los agentes + PlayerModel con memoria + farol + pareja (300-800 muestras) |

## Agentes

| Agente | Clase | Produce |
|---|---|---|
| Orquestador | `Orchestrator` | Elige agentes; activa el análisis profundo ante órdagos, apuestas ≥ 8 o el final de la partida |
| Cartas | `CardAgent` | Fuerza de la propia mano en cada lance |
| Comportamiento | `BehaviourAgent` | Agresividad, farol, aceptación y subidas de cada rival en el contexto actual (lance × marcador) |
| Probabilidad | `ProbabilityAgent` | P(ganar el lance), P(el rival acepta), P(ganar \| acepta), para envite y órdago |
| Farol | `BluffAgent` | P(el rival que envida farolea) por Bayes |
| Marcador | `ScoreAgent` | Apetito de riesgo, umbral de órdago, valor del juego, utilidad de un tanto |
| Pareja | `PartnerAgent` | P(mi compañero acepta si yo no quiero) |
| Estrategia | `StrategyAgent` | Candidatas legales con su valor esperado (EV) |
| Juez | `Judge` | `argmax EV − λ·riesgo·(1 − confianza)` → `Decision` |
| Reglas | motor | La autoridad es siempre `MusGame.validate` |

### Probabilidad con selección adversa

Para cada mundo muestreado (cartas no vistas repartidas de forma compatible con las
declaraciones públicas):

1. Se pondera por la verosimilitud de los envites rivales:
   `P(envite | fuerza) = 0.5·farol^n + (1 − farol)·σ((fuerza − τ)/0.05)`, con un umbral τ que sube
   con cada reenvite y **baja si el rival es agresivo** (aprendido por el PlayerModel).
2. Se anota si ganamos el lance y si el rival aceptaría (su fuerza ≥ umbral de aceptación).

Así se obtienen P(ganar), P(acepta) y P(ganar | acepta). Sin esto, el bot sobrestima sus
envites: quien acepta suele tener buena mano.

## DecisionExplanation

```python
bot = ProBot()
...
bot.last_decision.explanation()
# {'decision': 'BET_2',
#  'factors': {'p_win': 0.71, 'confidence': 0.93, 'p_accept_bet': 0.34, 'ev': 1.42, 'risk': 0.6},
#  'confidence': 0.74,
#  'agents_consulted': ['cartas', 'comportamiento', 'probabilidad', 'marcador', 'pareja'],
#  'alternatives': [{'action': 'BET_2', 'ev': 1.42, 'risk': 0.6}, ...],
#  'narrative': 'EV(BET_2)=+1.42; EV(PASS)=+0.71; EV(BET_4)=+1.10'}
```

En el servidor, las explicaciones se guardan por partida y solo se ven en el modo desarrollo
(`MUSST_DEV_MODE=1`, ruta `/api/dev/games/{id}`). Nunca se envían al jugador durante la partida.
