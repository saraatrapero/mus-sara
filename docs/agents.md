# Agentes de IA

Diseño completo: [design/06-agentes.md](design/06-agentes.md). Código: `src/musst/agents/`.

## Niveles

| Nivel | Clase | Técnica |
|---|---|---|
| Sencillo | `SimpleBot` | Heurísticas de fuerza de mano por lance; ruido del 15 % y faroles ocasionales (errores razonables) |
| Medio | `AgentBot("medio")` | Agentes de cartas, probabilidad (Monte Carlo, 90 muestras) y marcador |
| Profesional | `AgentBot("profesional")` | Todos los agentes + PlayerModel con memoria + farol + pareja (300-800 muestras) |

### Qué hace cada nivel (diferencias claras)

| | Sencillo | Medio | Profesional |
|---|---|---|---|
| Fuerza de su mano | Heurística | Monte Carlo (90 manos) | Monte Carlo (300; 800 en jugadas críticas) |
| Lee los envites del rival | No | Solo en el lance actual | Sí, ponderado por lo que sabe de cada rival |
| Conoce a cada jugador (PlayerModel) | No | No | Sí: farol, agresividad, qué envida con buena y mala mano |
| Conteo (cartas pedidas, descartes) | No | No | Sí |
| Tantos de jugada de la pareja (pares/juego) | No | Solo los suyos | Los de toda la pareja |
| Descarte | Heurístico | Heurístico | Simulado (30 reposiciones por opción) |
| Errores deliberados | 15 % | 30 % en decisiones ajustadas | Ninguno |
| Faroles | 5 % | Deliberados, 10 % de las manos flojas | Deliberados, 7 % |
| Órdago | Con mano muy fuerte | P(ganar) ≥ 0.8 o desesperación; **yendo por delante, P ≥ 0.85** (también para ver uno) | P(ganar) ≥ 0.8 o desesperación; **yendo por delante, P ≥ 0.85** (también para ver uno) |
| Señas | Si le mira cualquiera | Si le mira su compañero | Solo si le mira su compañero y ningún rival |
| Aprende entre partidas | No | No | Sí: perfiles y autocrítica |

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
