# 10 — Testing, experimentos, plan por fases y riesgos

## 1. Pirámide de tests

| Tipo | Carpeta | Qué cubre | Herramientas |
|---|---|---|---|
| Unitarios | `tests/unit/` | Cartas, evaluación de manos, legalidad, tanteo, transiciones | pytest |
| Basados en propiedades | `tests/property/` | Invariantes en miles de partidas aleatorias | hypothesis |
| Escenarios | `tests/scenarios/` | Manos y situaciones fijadas a mano ("deck amañado"), una por artículo FEM | pytest + fixtures YAML |
| Integración | `tests/integration/` | Partida completa vía `play_game`, runner, sandbox, API HTTP/WS | pytest, httpx |
| Privacidad | `tests/privacy/` | Fugas de información | pytest + hypothesis |
| Conformidad de bots | `tests/bot_conformance/` | Todo bot registrado | pytest (parametrizado) |
| E2E web | `web/tests/` | Partida completa en el navegador | Playwright |
| Rendimiento | `tests/perf/` | Manos/s del motor, latencia de los bots | pytest-benchmark |

## 2. Casos clave del motor

- **Baraja**: 40 cartas únicas; 3 cuenta como rey y 2 como as en grande, chica, pares y juego.
- **Reparto**: 4 cartas, orden antihorario, mano a la derecha del dealer, rotación.
- **Mus**: orden FEM IV.4; mus de los cuatro → descartes 1-4; rebarajar el descarte (III.15); varias rondas de mus.
- **Grande/chica**: orden, empates a favor del mano, valor en paso.
- **Pares**: par/medias/duples, comparación, una sola pareja con pares (sin envites), nadie con pares.
- **Juego/punto**: orden 31 > 32 > 40 > 37…33; punto si nadie tiene juego; un solo jugador con juego.
- **Envites**: negada (1); subida rechazada; "si uno quiere, vale el quiero" (VI.4); deje; órdago en cada lance.
- **Órdago**: aceptado → fin del juego y anulación de envites anteriores (VII.12); rechazado → negada y la jugada sigue.
- **"Quiero y no pierdo"**: el postre con 33 (VI.9-10).
- **Tanteo**: orden de lances (VII.2); llegar a 40 en grande antes que el rival en juego.
- **Final**: 40 exactos o más; "estamos dentro" a ≤ 4.
- **Ilegales**: fuera de turno, envido sin pares en pares, descartar 0 o 5, acción tras el final → `IllegalAction` y estado intacto.
- **Límite**: mazo agotado en el descarte, cuatro rondas de mus seguidas, apuesta enorme aceptada (> tantos restantes).

## 3. Tests de información privada (críticos)

1. Para N = 5 000 partidas aleatorias y cada observación de cada asiento: el JSON no contiene
   ninguna carta de otro asiento antes de `HandsRevealed`.
2. Ninguna observación contiene cartas del mazo ni del descarte ajeno.
3. Un `SpyBot` que intenta acceder al motor (por ejemplo `gc.get_objects()`) no encuentra
   ningún `GameState` en su proceso de sandbox.
4. Las respuestas HTTP/WS de `/games/{id}` no contienen manos ajenas.
5. Los logs fuera del canal `musst.secret` no contienen cartas.
6. El replay de una partida sin terminar está prohibido (403).
7. Prueba de "observación mínima": dos estados que solo difieren en las cartas ocultas
   producen **observaciones idénticas** para el asiento afectado.

## 4. Invariantes (hypothesis)

- En cualquier momento hay 40 cartas entre manos, mazo y descarte.
- El marcador nunca disminuye.
- La partida siempre termina (no hay ciclos infinitos de mus: tope configurable + rebarajado).
- `replay(seed, actions)` reproduce el log byte a byte.
- Cada acción ejecutada pertenece a `legal_actions` en ese estado.

## 5. Experimentos reproducibles (`experiments/`)

| Experimento | Métrica |
|---|---|
| Escalera de niveles (Random < Sencillo < Medio < Pro) | Win rate con IC al 95 % en mus duplicado, tantos medios |
| Básico vs adaptativo frente a perfiles sintéticos | Mejora del win rate frente a farolero, conservador y cambiante |
| Calibración | Brier score, curva de fiabilidad de P(ganar lance) y P(farol) |
| Adaptación | Partidas hasta que el error del PlayerModel < 0.1; retraso en detectar el cambio de estrategia |
| Coste | Tiempo de decisión p50/p99 por nivel |
| Legalidad | % de decisiones legales (debe ser 100 %) |

Cada experimento se ejecuta con `python -m experiments.<nombre> --seed 12345` y guarda
CSV + figura en `experiments/results/`.

## 6. CI (GitHub Actions)

| Workflow | Disparador | Pasos |
|---|---|---|
| `ci.yml` | push / PR a `develop` y `main` | ruff (lint y format), mypy, pytest + cobertura, build del paquete, build del frontend |
| `bot-pr.yml` | PR que toca `bots/**` | análisis estático, conformidad, mini-torneo contra los bots de referencia |
| `docs.yml` | PR | `mkdocs build --strict` (ReadTheDocs publica) |
| `tournament.yml` | merge en `main` + nightly | torneo + publicar scoreboard en Pages |
| `deploy.yml` | merge en `main` | desplegar backend y frontend |

## 7. Plan por fases

He agrupado tus 31 fases en **hitos**, con dos cambios de orden justificados:

- **CI/CD y estructura del repo pasan a la Fase 1** (no a la 27): la práctica puntúa C.3
  ("tests en cada PR") y C.2, y tenerlo desde el principio protege el motor.
- **Bot básico, API de bots y una web mínima van antes que usuarios y perfiles**: son el
  contenido del **punto de control** (Secciones 1 y 2).

| Hito | Fases | Entregable | Criterio de salida |
|---|---|---|---|
| **H0 Validación** | 0 | Este diseño + respuestas del profesor | Preguntas P1-P8 resueltas |
| **H1 Cimientos** | 1, (27) | Repo: pyproject, LICENSE, README, `main`/`develop` protegidas, CI con ruff, mypy y pytest, MkDocs | CI verde en un PR |
| **H2 Motor** | 2-10 | `musst.engine` completo; `play_game` con RandomBot | Todos los tests de reglas, invariantes y privacidad en verde; cobertura ≥ 90 % |
| **H3 Plataforma** | 11, 12 | SimpleBot, API pública, sandbox, tests de conformidad, tutorial "crea tu bot" | Un bot de ejemplo se añade sin tocar el motor |
| **H4 Web MVP** | 13 | FastAPI + mesa jugable (humano + bot compañero vs 2 bots), desplegada | URL pública, partida completa → **punto de control** |
| **H5 Competición** | 25, 26 | Arena + scoreboard automático | El torneo sobrevive a un bot roto inyectado |
| **H6 IA** | 16-20 | Agentes, Orquestador, Juez, MediumBot, ProBot | La escalera de niveles es significativa |
| **H7 Aprendizaje** | 14, 15, 21, 22 | Usuarios, perfiles, PlayerModel, aprendizaje post-partida | Los escenarios sintéticos se detectan |
| **H8 Análisis** | 23, 24 | Replay, estadísticas, post-partida, contrafactual | Replay idéntico al log |
| **H9 Producto** | 28-30 | Tutorial, entrenamiento, docs finales, pulido, accesibilidad | Lighthouse a11y ≥ 90 |

Cada fase se hace en su rama `feature/`, con un PR a `develop` y sus tests.

## 8. Posibles problemas y riesgos

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | El profesor no acepta el Mus de 4 jugadores | Bloqueante | P1 con alternativas preparadas; el motor sigue valiendo |
| R2 | Valores de las jugadas no especificados por la FEM | Medio | [CONVENCIÓN] configurable + P5 |
| R3 | **Dos humanos en la misma pareja** necesitan dos dispositivos (en uno se verían las cartas del compañero) | Alto para el Modo 1 | MVP: humano + bot compañero; después, sala con código de invitación por WebSocket. Nunca hot-seat sin pantalla de "pasa el dispositivo" |
| R4 | Hosting gratuito con arranque en frío / disco efímero | Medio | Pantalla de "despertando servidor"; BD externa gratuita; Plan B con Streamlit |
| R5 | Monte Carlo lento en Python | Medio | Numpy vectorizado, presupuesto de tiempo, precomputar tablas de manos (solo hay 40C4 = 91 390 manos) |
| R6 | Alcance excesivo frente a la fecha de entrega | Alto | Los hitos H1-H5 son el camino crítico de la nota; el resto es incremental |
| R7 | Sandbox de Python no es seguridad fuerte | Medio | Defensa por capas + revisión de PR (doc 05 §3), declarado honestamente |
| R8 | El PlayerModel aprende poco con pocas partidas | Medio | Priors jerárquicos, confianza explícita, escenarios sintéticos para demostrarlo |
| R9 | Fotos de usuarios (datos personales) | Medio | No guardar el original; avatar generado localmente o de un set; consentimiento |
| R10 | Requisito de la práctica sobre IA de pago | — | Usar solo herramientas permitidas por la universidad (§5.8 de la práctica) |
| R11 | Defensa: todos deben poder explicar todo | Alto | ADRs, diseño simple e interpretable, reparto de "propietarios" por módulo |
