# Testing y experimentos

```bash
pytest                         # 156 tests
pytest --cov=musst             # cobertura (88 % global; motor 93-100 %)
pytest tests/privacy           # solo fugas de información
pytest tests/bot_conformance   # conformidad de todos los bots registrados
```

## Pirámide

| Carpeta | Qué cubre |
|---|---|
| `tests/unit` | Baraja, evaluación de manos, mus y descartes, envites y órdagos, tanteo, acciones, máquina de estados, PlayerModel, análisis, señas, CLI |
| `tests/property` | Invariantes con *hypothesis*: 40 cartas siempre, marcador creciente, toda acción ejecutada es legal, la partida termina, misma seed ⇒ mismo log |
| `tests/privacy` | Ninguna observación contiene cartas ajenas ni del mazo; observaciones idénticas si solo cambian cartas ocultas; espectador sin manos; eventos de sistema invisibles |
| `tests/integration` | Partidas completas con cada bot; bots que fallan (excepción, ilegal, basura, timeout) pierden sin romper; sandbox en subproceso; torneo; API web completa; backend del navegador (Pyodide) |
| `tests/bot_conformance` | Se parametriza con **todos** los bots registrados (internos y `bots/*`) |

### Escenarios controlados ("baraja amañada")

`tests/helpers.py::rigged_game` fija las manos de cada asiento para probar reglas concretas:
"vale el quiero del compañero" (FEM VI.4), "quiero y no pierdo" (VI.9), deje en pares,
gana quien llega primero contando en orden de lances (VII.2), la negada que termina el juego,
"estamos dentro" (VII.7)…

## Experimentos reproducibles

```bash
python -m experiments.level_ladder --seeds 50 --seed 12345
python -m experiments.adaptation --games 25 --seed 7
```

Los resultados (CSV) se escriben en `experiments/results/`.

### Escalera de niveles (mus duplicado, 100 partidas por emparejamiento)

| Bot A | Bot B | % victorias de B | IC 95 % |
|---|---|---|---|
| random | sencillo | **76 %** | 67 – 83 % |
| random | medio | **87 %** | 79 – 92 % |
| random | profesional | **88 %** | 80 – 93 % |
| sencillo | medio | **59 %** | 49 – 68 % |
| sencillo | profesional | **59 %** | 49 – 68 % |
| medio | profesional | 55 % | 45 – 64 % |

Lectura honesta:

- Random < Sencillo < {Medio, Profesional}, con intervalos que no se solapan con el 50 % salvo
  en el último escalón.
- Profesional frente a Medio (55 %) **no es significativo** con 100 partidas. En este
  experimento cada partida crea bots nuevos, así que el profesional **no conserva memoria** de
  sus rivales: su ventaja principal (el PlayerModel) no actúa. Ver el experimento de adaptación.

### Métricas además de victorias

| Métrica | Dónde |
|---|---|
| Decisiones legales | 100 % (tests de conformidad y de invariantes) |
| Tiempo de decisión | `MatchResult.decision_times`; el test de conformidad exige p99 < 2 s |
| Calibración | Comparar P(ganar \| acepta) estimada con la frecuencia real (se usó para corregir los agentes, ADR-009) |
| Adaptación | Error y confianza del PlayerModel frente a jugadores sintéticos (`experiments/adaptation.py`, `tests/unit/test_player_model.py`) |

### Adaptación del bot profesional (25 partidas por configuración)

`experiments/adaptation.py` enfrenta al bot profesional a jugadores sintéticos con y sin
memoria persistente entre partidas:

| Rival | Memoria | % victorias del profesional | P(farol) estimada del rival (confianza) |
|---|---|---|---|
| Farolero (`bluff=0.8`) | no | 84 % | 0.34 (0.81) |
| Farolero (`bluff=0.8`) | **sí** | **88 %** | 0.46 (0.89) |
| Conservador (`bluff=0`, umbral 0.85) | no | 76 % | 0.06 (0.62) |
| Conservador (`bluff=0`, umbral 0.85) | **sí** | 72 % | 0.02 (0.85) |

Lectura honesta:

- El **modelo** aprende lo que debe: con memoria, la estimación de farol se separa claramente
  entre el farolero (0.46) y el conservador (0.02), y la confianza sube.
- El **impacto en victorias** es pequeño y, con 25 partidas, no es significativo (+4 puntos
  frente al farolero, −4 frente al conservador). Convertir mejor la información del modelo en
  decisiones es la principal línea de mejora (ver doc 10 del diseño).
- `bluff_frequency` mide la fracción de envites hechos con mano débil, no P(envidar | mano débil):
  por eso el farolero con `bluff=0.8` aparece con 0.46.
