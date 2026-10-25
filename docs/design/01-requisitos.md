# 01 — Análisis de requisitos

## 1. Análisis

MUS.ST tiene dos objetivos a la vez, que a veces tiran en direcciones distintas:

| Objetivo | Qué exige |
|---|---|
| **Producto**: plataforma de Mus que aprende cómo juegas | UX cuidada, bots adaptativos, perfiles, estadísticas, entrenamiento, replay |
| **Práctica IA 2026/27**: se evalúa por requisitos defendibles | Librería Python instalable, web pública, API de bots, tests, torneo automático, repositorio profesional |

Para que no compitan, la práctica marca el **camino crítico** (lo que da nota) y el producto
se construye **encima** sin bloquearlo. Por eso el plan (doc 10) prioriza: motor, API de
bots, bot propio, web mínima, torneo y CI, antes que perfiles, aprendizaje y pulido visual.

### Actores

| Actor | Descripción |
|---|---|
| Jugador humano | Juega, entrena y consulta estadísticas. Puede ser anónimo o registrado. |
| Compañero humano | Segundo humano en la pareja; necesita **su propio dispositivo/sesión** (ver Riesgo R3). |
| Bot interno | Bots del equipo (Sencillo, Medio, Profesional). |
| Bot externo | Bot de otro desarrollador, añadido por Pull Request (Req 2.1, 3.3). |
| Desarrollador | Usa el modo dev (estado completo); nunca disponible en producción. |
| Sistema de torneo | Proceso automático (GitHub Actions) que enfrenta a todos los bots. |

## 2. Requisitos funcionales

Prioridad: **P0** = camino crítico de la práctica · **P1** = núcleo del producto · **P2** = ampliación.

### RF-J — Juego (motor)

| ID | Requisito | Prio | Fuente |
|---|---|---|---|
| RF-J01 | Baraja española de 40 naipes, modalidad ocho reyes / ocho ases (3 = rey, 2 = as) | P0 | FEM II.3 |
| RF-J02 | Sorteo del primer reparto, reparto de uno en uno, de derecha a izquierda; mano = jugador a la derecha del que reparte | P0 | FEM III.1-2, VIII.8 |
| RF-J03 | Fase de mus: dar/cortar mus con el orden de FEM IV.4; descartes y reposición; rebarajar el descarte si se acaba el mazo | P0 | FEM IV, III.11, III.15 |
| RF-J04 | Lances en orden: grande → chica → pares → juego **o** punto | P0 | FEM VII.2 |
| RF-J05 | Declaración pública de pares sí/no y juego sí/no; solo hablan en pares/juego quienes los tienen | P0 | FEM VI.5, VI.22 |
| RF-J06 | Envites: paso, envido (2), envido N, reenvite, quiero, no quiero, órdago | P0 | FEM VIII.8, VI |
| RF-J07 | Órdago aceptado: se enseñan los naipes y se resuelve el juego; anula los envites aceptados anteriores | P0 | FEM VI.6, VII.12 |
| RF-J08 | Tanteo en orden de lances: negadas/revoques en el acto; envites aceptados y valor de jugadas al final de la jugada | P0 | FEM VI.6, VII.2 |
| RF-J09 | Deje en pares, juego y punto | P0 | FEM VII.1, VIII.8 |
| RF-J10 | Fin del juego al alcanzar el objetivo (40 por defecto, configurable entre 40 y 60) | P0 | FEM Intro E |
| RF-J11 | Anuncio "estamos dentro" cuando a una pareja le faltan ≤ 4 tantos | P1 | FEM VII.7 |
| RF-J12 | Al terminar juego/punto, los cuatro enseñan sus naipes (evento público) | P0 | FEM VII.9 |
| RF-J13 | Rechazo de acciones ilegales sin romper la partida | P0 | Req 5.1.1 |
| RF-J14 | Partida completa jugable desde código sin interfaz | P0 | Req 1.1 |
| RF-J15 | Seed para reproducir cualquier partida | P0 | — |
| RF-J16 | Composición de asientos configurable (H+H vs B+B, H+B vs H+B, 4 bots…) | P1 | — |
| RF-J17 | `SignalSystem` preparado con las señas FEM; **desactivado en v1** | P2 | FEM VIII.2-7 |
| RF-J18 | Partida a N juegos ("a cinco juegos" FEM) configurable; v1 = 1 juego | P2 | FEM Intro E |

### RF-B — Plataforma de bots

| ID | Requisito | Prio | Fuente |
|---|---|---|---|
| RF-B01 | API pública Python: `class Bot: def decide(self, observation) -> Action` | P0 | Req 2.1 |
| RF-B02 | Un bot externo no modifica el motor; se registra con un fichero en `bots/` | P0 | Req 2.1 |
| RF-B03 | Suite de tests de conformidad que todo bot debe pasar antes del merge | P0 | Req 2.2 |
| RF-B04 | Documentación online: referencia del API + tutorial de principio a fin | P0 | Req 2.3 |
| RF-B05 | Ejecución aislada (subproceso, timeout, límites) | P0 | Req 4.1 |
| RF-B06 | Bot que falla, se cuelga o juega ilegal pierde la partida sin romper el torneo | P0 | Req 4.1 |

### RF-T — Competición

| ID | Requisito | Prio | Fuente |
|---|---|---|---|
| RF-T01 | Torneo todos contra todos con seeds fijas y asientos rotados | P0 | Req 4.1 |
| RF-T02 | Clasificación: bot, partidas, victorias, derrotas, %V, tantos, errores | P0 | Req 4.1 |
| RF-T03 | Publicación automática del scoreboard (GitHub Actions → Pages) | P0 | Req 4.2 |
| RF-T04 | Bot Arena en la web (observar Bot vs Bot sin información privada) | P2 | — |

### RF-U — Interfaz y modos

| ID | Requisito | Prio |
|---|---|---|
| RF-U01 | Web pública donde un humano juega una partida completa contra bots (Req 1.2, 1.3) | P0 |
| RF-U02 | Modo 1 Partida rápida (H+H vs 2 bots; en el MVP, H+bot compañero vs 2 bots) | P0 |
| RF-U03 | Modo 3 Partida personalizada (nivel, nombres, avatares, velocidad, sonido) | P1 |
| RF-U04 | Modo 2 Entrenamiento + análisis posterior | P1 |
| RF-U05 | Modo 5 Entrenamiento contra un bot concreto | P1 |
| RF-U06 | Modo 6 Historial + replay (⏮ ◀ ▶ ⏭) | P1 |
| RF-U07 | Asistente "¿Qué puedo hacer ahora?" (solo acciones legales; nunca decide) | P1 |
| RF-U08 | Tutorial interactivo y modo "Aprender jugando" | P1 |
| RF-U09 | Situaciones de entrenamiento ("vas 35-38, el rival envida 4…") | P1 |
| RF-U10 | Resumen post-partida: resultado, momentos clave, estadísticas, aprendizaje del bot | P1 |
| RF-U11 | Simulación contrafactual **solo después** de la partida | P2 |
| RF-U12 | Modo desarrollo (estado completo, paso a paso, forzar acciones) — nunca en producción | P1 |
| RF-U13 | Recuperar una partida tras cerrar la app | P2 |

### RF-P — Usuarios, perfil y aprendizaje

| ID | Requisito | Prio |
|---|---|---|
| RF-P01 | Registro/login con contraseña hasheada; foto opcional → avatar | P1 |
| RF-P02 | `PlayerModel` contextual por usuario, actualizado tras cada partida | P1 |
| RF-P03 | Pantalla de estadísticas descriptivas (no una "nota") | P1 |
| RF-P04 | Detección de cambio de estrategia con aumento de incertidumbre | P2 |
| RF-P05 | Logros sobrios ("Primera victoria", "Remontada"…) | P2 |

### RF-A — Inteligencia artificial

| ID | Requisito | Prio |
|---|---|---|
| RF-A01 | Bot Sencillo: heurísticas, errores razonables | P0 |
| RF-A02 | Bot Medio: probabilístico (Monte Carlo) + marcador + historial básico | P1 |
| RF-A03 | Bot Profesional: arquitectura multiagente completa + PlayerModel | P1 |
| RF-A04 | La diferencia entre niveles se mide experimentalmente | P1 |
| RF-A05 | Toda decisión produce una `DecisionExplanation` (acción, confianza, evidencia, agentes) | P1 |

## 3. Requisitos no funcionales

| ID | Categoría | Requisito | Métrica / verificación |
|---|---|---|---|
| RNF-01 | Corrección | El motor implementa las reglas FEM; las convenciones están marcadas | Tests por artículo FEM |
| RNF-02 | Privacidad de información | Ninguna observación contiene cartas ajenas, cartas futuras ni estado de agentes | Tests de fuga (doc 10 §3) |
| RNF-03 | Robustez | Ningún bot, timeout, acción ilegal o desconexión rompe la app | Tests de fallos inyectados |
| RNF-04 | Reproducibilidad | Misma seed + mismos bots deterministas ⇒ mismo log de eventos | Test de hash del log |
| RNF-05 | Rendimiento | Motor ≥ 1 000 manos/s en un solo hilo; decisión de bot Profesional ≤ 1 s (configurable) | Benchmark en CI |
| RNF-06 | Mantenibilidad | Type hints, docstrings, `ruff` y `mypy --strict` en `musst.engine` | CI |
| RNF-07 | Cobertura | ≥ 90 % en `engine`, ≥ 75 % global | `pytest --cov` |
| RNF-08 | Portabilidad | Motor sin dependencias de terceros (stdlib pura) | `pyproject` |
| RNF-09 | Seguridad | Hash de contraseñas (argon2), sesiones seguras, validación con Pydantic | doc 08 |
| RNF-10 | Accesibilidad | WCAG 2.1 AA: contraste, no depender solo del color, reducción de movimiento, teclado | Lighthouse/axe |
| RNF-11 | Responsive | Ordenador, tablet y móvil (≥ 360 px) | Pruebas manuales + Playwright |
| RNF-12 | Configurabilidad | Sin números mágicos: TOML de reglas, agentes y UI | Revisión |
| RNF-13 | Observabilidad | Logging por niveles; cartas privadas nunca en logs públicos | Test de logs |
| RNF-14 | Coste | Despliegue gratuito | doc 02 §6 |
| RNF-15 | Privacidad de datos | Minimización: no se guarda información personal innecesaria | doc 08 |

## 4. Trazabilidad con la práctica

| Req práctica | Puntos | Cubierto por | Fase |
|---|---|---|---|
| 1.1 Librería instalable + partida sin interfaz | 1.5 | Paquete `musst` y `musst.play(...)` | 1-10 |
| 1.2 Web: humano juega partida completa vs bot | 1.0 | Frontend + API FastAPI | 13 |
| 1.3 URL pública sin instalar | 0.5 | Despliegue (doc 02 §6) | 13/29 |
| 2.1 API pública de bots | 1.0 | `musst.bots.api.Bot` | 12 |
| 2.2 Tests automáticos de nuevos bots | 0.5 | `tests/bot_conformance/` + workflow PR | 12 |
| 2.3 Docs online, referencia + tutorial | 0.5 | MkDocs + ReadTheDocs | 12/28 |
| 3.1 Bot propio | 0.5 × dificultad | Sencillo/Medio/Profesional | 11, 16-22 |
| 3.2 Bot para otro equipo | 0.5 × dificultad | Fuera de este repo | — |
| 3.3 Bot externo recibido por PR | 0.25/bot | Tutorial + plantilla de PR | 25+ |
| 4.1 Torneo robusto | 1.0 | `musst.arena` | 25 |
| 4.2 Scoreboard publicado automáticamente | 0.5 | Workflow programado → Pages | 26 |
| C.1 README, LICENSE, .gitignore, estructura | 0.5 | Fase 1 | 1 |
| C.2 Ramas, PR, `main` protegida | 0.5 | `main`/`develop`/`feature/*` + branch protection | 1 |
| C.3 Tests en cada PR | 0.5 | GitHub Actions | 1 (pronto, no en la fase 27) |

> **Nota:** la dificultad del Mus no aparece en la tabla de la práctica (Sección 4). Hay que
> pedir al profesor que la asigne, porque multiplica la puntuación de los bots (pregunta P3).
