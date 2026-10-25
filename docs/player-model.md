# PlayerModel y aprendizaje

Diseño completo: [design/07-player-model.md](design/07-player-model.md). Código: `src/musst/learning/`.

## Qué aprende

| Métrica | Definición (éxitos / oportunidades) |
|---|---|
| `aggression` | envites / turnos con el lance abierto |
| `bluff_frequency` | envites con mano débil revelada / envites con mano revelada |
| `risk_tolerance` | aceptaciones con mano débil / aceptaciones con mano revelada |
| `acceptance_rate`, `rejection_rate`, `raise_rate` | respuestas a envites |
| `ordago_rate` | órdagos / oportunidades |
| `mus_rate` | mus / turnos de mus |

Cada métrica se guarda **por contexto**: lance (`grande`, `chica`, `pares`, `juego`, `punto`,
`mus`) × marcador (`ahead`, `behind`, `close`, `even`). Así el modelo captura "farolea más en
grande cuando va por detrás".

## Cómo estima

- Tasa Beta con prior (jugador típico) + **back-off jerárquico**: un contexto con poca muestra se
  encoge hacia su padre `(lance, *)` y este hacia el global.
- Cada estimación lleva su **confianza** (`n / (n + 6)`) y una etiqueta Baja/Media/Alta.
  Nunca se afirma "miente": *"P(farol) estimada 68 % (confianza media, n = 14)"*.

## Memorias

| Memoria | Implementación |
|---|---|
| Corto plazo | `Observation.history` de la jugada actual |
| Sesión | `Learner.recent` (olvido rápido, factor 0.6 por partida) |
| Largo plazo | `ModelStore`: memoria, fichero JSON o base de datos (factor 0.98) |
| Perfil | `PlayerModel.profile()` → pantalla de estadísticas |

Solo se guardan contadores, no transcripciones.

## Ciclo post-partida

`Learner.learn_game(historial público, {asiento: id})`:

1. Extrae decisiones con su contexto (`learning/extract.py`) usando **solo** eventos públicos y
   las manos reveladas al final de cada jugada.
2. Actualiza los modelos largo y reciente.
3. **Detecta cambios de estrategia**: si la divergencia de Jensen-Shannon entre el modelo largo
   y el reciente supera 0.03 bits, reduce la confianza del modelo largo a la mitad.
4. Genera el resumen privado ("Aceptó 8 de 10 envites", "tendencia a farolear en grande", …).

## Validación con jugadores sintéticos

`learning/synthetic.py` define `SyntheticPlayer(bluff, value_threshold, risk_tolerance,
shift_after)`. Los tests comprueban que:

- un jugador con `bluff=0.8` se distingue de uno con `bluff=0.0` (diferencia > 0.2, confianza > 0.5);
- `risk_tolerance=0.9` y `0.1` producen perfiles distintos;
- un cambio de 0 % a 95 % de faroles se detecta como cambio de estrategia.
