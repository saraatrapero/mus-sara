# 06 — Arquitectura de agentes

## 1. Principios

1. Los agentes **solo leen** la `Observation` y la memoria de su propio bot. Nunca el `GameState`.
2. Los agentes **no ejecutan** acciones: producen recomendaciones. El Juez elige una acción de
   `observation.legal_actions`, y el motor la vuelve a validar.
3. Toda salida probabilística lleva **confianza** (incertidumbre explícita).
4. Cada agente es una clase pequeña con un método puro: `analyze(ctx) -> AgentReport`.

```python
@dataclass(frozen=True)
class AgentReport:
    agent: str
    estimates: Mapping[str, Estimate]        # p. ej. "p_win_grande": Estimate(0.72, conf=0.8)
    recommendations: tuple[Recommendation, ...] = ()
    notes: tuple[str, ...] = ()               # para debugging, no para el jugador

@dataclass(frozen=True)
class Estimate:
    value: float
    confidence: float        # 0..1, se muestra como Baja / Media / Alta
    n: int                   # tamaño de muestra que la respalda
```

## 2. Agentes

| Agente | Entrada | Salida | Técnica (v1) |
|---|---|---|---|
| **Cartas** | mi mano, cartas vistas | fuerza en cada lance, percentil frente a manos posibles | Enumeración/Monte Carlo sobre las cartas no vistas |
| **Probabilidad** | Cartas + declaraciones públicas + acciones | P(ganar lance), P(rival con jugada X), EV de pasar/aceptar/subir | **Monte Carlo con pesos**: se muestrean manos rivales compatibles con lo público (p. ej. "pares sí") y se reponderan con el modelo de comportamiento (verosimilitud de sus acciones dada la mano) |
| **Comportamiento** | Historial de acciones del rival + PlayerModel | perfil contextual: agresividad, aceptación, etc. | Frecuencias Beta-Bernoulli por contexto (doc 07) |
| **Farol** | Acción observada + Comportamiento + Cartas | P(mano fuerte / media / farol) | Bayes: P(farol \| acción, contexto) ∝ P(acción \| farol, contexto)·P(farol \| contexto) |
| **Marcador** | Marcador, objetivo, posición | Utilidad de los tantos, apetito de riesgo | Utilidad no lineal: valor de un tanto según la distancia a 40; P(ganar la partida \| marcador) precomputada por simulación |
| **Historial** | Partidas anteriores del rival | Priors para el PlayerModel | Agregación con decaimiento temporal |
| **Pareja** | Acciones del compañero y su historial | P(el compañero apoya / sube / se retira) | Frecuencias contextuales del compañero |
| **Estrategia** | Todos los informes | Candidatas ⊆ `legal_actions` con su EV estimado | EV = Σ P(resultado)·utilidad(tantos, marcador) |
| **Reglas** | Observation | Filtra las candidatas a las legales | Consulta `legal_actions` (es un espejo; la autoridad sigue siendo el motor) |
| **Juez** | Candidatas + informes | `Decision` | Comparación de EV ajustada por riesgo e incertidumbre |
| **Orquestador** | Observation, nivel | Qué agentes consultar y con qué peso | Reglas de activación + presupuesto de tiempo |

### 2.1 Orquestador

- **Activación por contexto**: en `MUS_DECISION` y `DISCARD` solo consulta Cartas y Probabilidad;
  ante un órdago o con el marcador cerca de 40, consulta todos los agentes con más muestras de
  Monte Carlo ("análisis profundo").
- **Pesos**: configurables por nivel en `agents.toml`; el peso del Comportamiento crece con
  la confianza del PlayerModel (con pocos datos, menos influencia).
- **Presupuesto**: un límite de tiempo por decisión; si se agota, el Juez decide con lo que haya.

### 2.2 Juez

```python
@dataclass(frozen=True)
class Decision:
    action: Action
    confidence: float
    evidence: tuple[Evidence, ...]          # factores y su contribución
    agents_consulted: tuple[str, ...]
    alternatives: tuple[ScoredAction, ...]  # para el análisis posterior

@dataclass(frozen=True)
class DecisionExplanation:                  # para debugging, modo dev y defensa
    decision: str                           # "BET_4"
    factors: Mapping[str, float]            # hand_strength, opponent_bluff_p, score_context, risk
    confidence: float
    narrative: str                          # "EV(quiero)=+1.3 vs EV(no quiero)=-1.0; P(farol)=0.63 (conf. media)"
```

Criterio: `argmax_a [EV(a) − λ·Riesgo(a)·(1 − confianza)]`, con λ según el nivel y el
marcador. Comprueba coherencia (por ejemplo, no envidar en pares con el compañero
"pares no" sin tener pares) y que la acción sea legal.

## 3. Niveles: diferencia real y medible

| | Sencillo | Medio | Profesional |
|---|---|---|---|
| Fuerza de mano | Tablas heurísticas | Monte Carlo (200 muestras) | Monte Carlo con pesos (1 000+), condicionado a acciones |
| Marcador | No | Umbrales | Utilidad completa |
| Modelo del rival | No | Frecuencias globales de la sesión | PlayerModel contextual + Farol + cambio de estrategia |
| Pareja | No | No | Sí |
| Mus/descarte | Reglas fijas (buscar 31, reyes…) | Elige el descarte por EV | EV + señal implícita del mus del compañero |
| Faroles | Aleatorios con p fija baja | p según la posición | Óptimos según la tendencia del rival a aceptar |
| Errores | Ruido ε = 0.15 entre acciones cercanas | ε = 0.05 | ε = 0 |
| Tiempo | < 10 ms | < 200 ms | < 1 s |

**Medición** (doc 10 §5): tasa de victorias por pares en mus duplicado (≥ 2 000 partidas por
emparejamiento) con IC al 95 %. Criterio de aceptación: Profesional > Medio > Sencillo >
Random con significación estadística.

## 4. Bots internos

- `RandomBot`: referencia mínima y base de los tests.
- `SimpleBot` (Sencillo): primer bot real (Fase 11), sirve para el Req 3.1 lo antes posible.
- `MediumBot`, `ProBot`: se construyen sobre los agentes (Fases 16-22).

Los tres bots internos usan **la misma API pública** que un bot externo, para que la API se
pruebe con un uso real.
