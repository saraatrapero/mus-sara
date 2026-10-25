# MUS.ST

> *El Mus que aprende cómo juegas.*

Plataforma de Mus (Reglamento de la Federación Española de Mus) con un motor de reglas
fiable, bots inteligentes y adaptativos, modelos de jugador, estadísticas, entrenamiento y
una arquitectura preparada para competiciones de bots.

Proyecto de la práctica de **Inteligencia Artificial — 3º MAT-A, CUNEF Universidad, 2026/2027**.

## Estado

**Fase 0 — diseño.** Todavía no hay código. El diseño completo está en
[`docs/design/`](docs/design/00-indice.md) y está pendiente de validación por el profesor
([preguntas](docs/design/11-preguntas-profesor.md)).

## Cuatro pilares

| Jugar | Aprender | Competir | Analizar |
|---|---|---|---|
| Partida rápida, personalizada, contra un bot | Tutorial, aprender jugando, situaciones de entrenamiento | Bot Arena, torneo automático, scoreboard | Historial, replay, estadísticas, análisis post-partida |

## Flujo de trabajo

`main` (protegida) ← `develop` ← `feature/*`, siempre mediante Pull Request con CI verde.
