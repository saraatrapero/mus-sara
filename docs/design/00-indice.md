# MUS.ST — Documento de diseño (Fase 0)

> *El Mus que aprende cómo juegas.*

Este directorio contiene el diseño completo previo a la implementación. **No hay código todavía.**
Ninguna fase de implementación empieza hasta que este diseño se valide (ver
[11-preguntas-profesor.md](11-preguntas-profesor.md)).

## Fuentes de verdad

| Ámbito | Fuente | Uso |
|---|---|---|
| Reglas del juego | *Reglamento de Juego de la Federación Española de Mus* (FEM) | Única autoridad sobre reglas. Citado como `FEM Cap.X Art.Y`. |
| Requisitos técnicos y evaluación | *Práctica de Programación – IA 3 MAT-A 2026/2027* (J. Paris) | Arquitectura, API de bots, tests, torneo, repositorio. Citado como `Req N.M`. |

Cuando el Reglamento FEM **no especifica** algo (por ejemplo, el valor de las cartas para
pares/juego/punto), se marca explícitamente como **[CONVENCIÓN]**: regla tradicional del Mus,
implementada como parámetro configurable y pendiente de confirmación. Nunca se presenta como
regla FEM.

## Índice

| # | Documento | Contenido |
|---|---|---|
| 01 | [Requisitos](01-requisitos.md) | Análisis, requisitos funcionales y no funcionales, trazabilidad con la práctica |
| 02 | [Arquitectura](02-arquitectura.md) | Capas, componentes, tecnologías, decisiones |
| 03 | [Reglas y motor](03-motor-y-reglas.md) | Reglas FEM, máquina de estados, GameEngine, acciones, puntuación |
| 04 | [Eventos y observaciones](04-eventos-y-observaciones.md) | Event sourcing, eventos públicos/privados, ObservationBuilder |
| 05 | [API de bots](05-api-bots.md) | Interfaz `Bot`, sandbox, torneo, scoreboard |
| 06 | [Agentes](06-agentes.md) | Arquitectura multiagente, niveles de dificultad, DecisionExplanation |
| 07 | [PlayerModel](07-player-model.md) | Modelo de jugador, memoria, detección de cambios, calibración |
| 08 | [Datos y seguridad](08-datos-y-seguridad.md) | Modelo de datos, persistencia, seguridad, logging |
| 09 | [Interfaz](09-interfaz.md) | Pantallas, mesa, accesibilidad, identidad visual |
| 10 | [Testing y plan](10-testing-y-plan.md) | Plan de pruebas, experimentos, plan por fases, riesgos |
| 11 | [Preguntas para el profesor](11-preguntas-profesor.md) | **Conflictos y decisiones que debe validar el profesor** |

## Principios rectores

1. **Corrección del motor antes que sofisticación de la IA.**
2. **El motor es la única autoridad.** La IA recomienda; el `RulesEngine` valida; el `GameEngine` ejecuta.
3. **Nadie recibe el estado completo.** Humanos y bots reciben solo una `Observation` específica de su asiento.
4. **Todo es un evento.** La partida se puede reconstruir y reproducir a partir de su log.
5. **Reproducibilidad.** Toda partida automática acepta una `seed`.
6. **Incertidumbre explícita.** Ningún agente afirma certezas: probabilidades más una confianza.
7. **Incremental.** Cada fase se entrega con tests y no empieza la siguiente sin validar.
8. **Explicable por el equipo.** No se usa ninguna tecnología solo porque "queda más avanzada".
