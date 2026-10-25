# 07 — PlayerModel, memoria y aprendizaje

## 1. Filosofía

- **Modelo probabilístico interpretable**: distribuciones Beta sobre tasas de comportamiento,
  condicionadas al contexto. Se explica en clase en dos minutos y encaja en el temario
  (*Razonamiento con incertidumbre*).
- No se usa ML complejo porque sí. La interfaz `BehaviourModel` permite cambiar la
  implementación (clasificador, RL, secuencial) sin tocar los agentes.
- Se aprende **"hace X cuando ocurre Y"**, no solo "hace X".
- Nunca se afirma "miente": "P(farol) estimada = 0.68 (confianza media, n = 14)".

## 2. Estructura

```python
@dataclass
class Rate:                       # Beta(α, β)
    alpha: float = 1.0            # prior configurable
    beta: float = 1.0
    def mean(self) -> float: ...
    def confidence(self) -> float: ...     # función de α+β (tamaño efectivo de muestra)
    def update(self, success: bool, weight: float = 1.0) -> None: ...
    def decay(self, factor: float) -> None: ...  # olvido exponencial

class PlayerModel:
    player_id: str
    global_: dict[Metric, Rate]                       # aggression, acceptance_rate, ...
    contextual: dict[tuple[Metric, Context], Rate]    # (aggression, (GRANDE, BEHIND))
    sample_size: int
    last_updated: datetime
    drift: DriftState
```

### 2.1 Métricas

| Métrica | Definición operativa (éxitos / oportunidades) |
|---|---|
| `aggression` | envites o subidas / turnos en los que podía envidar |
| `risk_tolerance` | aceptaciones con mano débil (revelada) / aceptaciones con mano revelada |
| `bluff_frequency` | envites con mano por debajo del percentil 40 / envites con mano revelada |
| `acceptance_rate` | quiero / envites recibidos |
| `rejection_rate` | no quiero / envites recibidos |
| `raise_rate` | subidas / envites recibidos |
| `ordago_rate` | órdagos / oportunidades |
| `mus_rate` | mus / turnos de mus |
| `declaration_accuracy` | En v1 la declaración es automática (siempre exacta); queda reservada para el modo con señas. **Se documenta, no se inventa.** |

> Los faroles **solo se pueden medir con cartas reveladas**. Como en v1 todas las manos se
> enseñan al final de la jugada (FEM VII.9), el aprendizaje usa las cartas tras el showdown,
> nunca durante la jugada.

### 2.2 Contextos (dimensiones combinables)

- **Lance**: grande, chica, pares, juego, punto, mus.
- **Marcador**: `ahead` (> +5), `behind` (< −5), `close_to_target` (alguna pareja a ≤ 8 tantos), `even`.
- **Fase de la partida**: `early` (máximo < 15), `mid`, `late` (máximo ≥ 30).
- **Posición**: mano / postre.

Para evitar explotar el número de combinaciones se usa **back-off jerárquico**: si el contexto
específico tiene poca muestra, su estimación se encoge hacia la del contexto padre (prior
jerárquico: α₀, β₀ del padre escalados por `k`). Ejemplo: (aggression, grande, behind) →
(aggression, grande) → aggression global.

## 3. Memorias

| Memoria | Alcance | Contenido | Persistencia |
|---|---|---|---|
| Short-term | Jugada y partida actuales | Acciones públicas, declaraciones | RAM del bot |
| Session | Sesión del usuario | Rates con decaimiento rápido | RAM / caché del servidor |
| Long-term | Histórico | Rates contextuales agregadas | BD (`player_models`) |
| PlayerProfile | Vista agregada | Resumen para la pantalla de estadísticas | Derivada de la long-term |

Minimización: se guardan **contadores**, no transcripciones. Los eventos crudos se guardan
solo para el replay del propio usuario.

**Aislamiento:** el bot recibe el PlayerModel de sus rivales desde el servidor (fuera de la
`Observation` del motor, en `on_game_start`). Es información **histórica pública**: no contiene
nada de la partida en curso que el bot no pueda ver. Los bots externos del torneo no reciben
modelos de humanos.

## 4. Detección de cambio de estrategia

Se mantienen dos estimaciones de cada métrica principal: la larga (decaimiento lento) y la
reciente (ventana de las últimas ~3 jugadas, decaimiento rápido). Si la divergencia de
Jensen-Shannon entre ambas Betas supera un umbral (o un test de Page-Hinkley lo detecta):

1. evento interno `StrategyShiftSuspected(metric, context)`;
2. se **reduce la confianza** del modelo largo (se escalan α, β por un factor < 1);
3. el Juez da más peso a la estimación reciente.

Ejemplo del enunciado: 5 partidas conservador → 3 jugadas agresivo ⇒ `aggression` reciente ≫
larga ⇒ se baja la confianza y el bot pasa a aceptar menos faroles "de oficio".

## 5. Ciclo post-partida

```
GameFinished
   ▼
1. Extraer decisiones + contexto + manos reveladas (eventos)
2. Comparar predicciones (P(farol), P(ganar lance)) con lo ocurrido → registro de calibración
3. Actualizar el PlayerModel (Rates contextuales) y comprobar el cambio de estrategia
4. Actualizar estadísticas
5. Generar el resumen privado del bot:
     "El rival aceptó 8 de 10 envites."
     "Tendencia a farolear en grande (P≈0.41, conf. media)."
     "Más agresivo cuando iba por detrás (+18 pp)."
6. Mensaje al usuario: "El bot ha actualizado su modelo sobre tu forma de jugar."
```

**Calibración** (aprender de sus errores): Brier score y diagrama de fiabilidad de las
predicciones de Probabilidad y Farol. Si la calibración empeora, se ajusta la temperatura de
las estimaciones (calibración de Platt simple) por nivel.

## 6. Escenarios controlados (validación)

Jugadores sintéticos con parámetros conocidos (`SyntheticPlayer(bluff_frequency=0.8)`,
`SyntheticPlayer(risk_tolerance=0.1)`, `SyntheticPlayer(shift_after=50)`). Tests y experimentos
comprueban que:

- el error |estimado − real| decrece con n (se espera ~1/√n), y el IC cubre el valor real;
- dos perfiles distintos se separan (distancia entre posteriores > umbral tras N jugadas);
- el cambio de estrategia se detecta con un retraso acotado.
