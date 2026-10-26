# Registro de decisiones de arquitectura (ADR)

Cada decisión incluye qué problema resuelve, por qué se elige, alternativas, ventajas,
limitaciones y cómo se ha probado.

## ADR-001 · Motor en Python puro, sin dependencias

- **Problema**: la lógica debe ser una librería instalable y jugable sin interfaz (Req 1.1).
- **Decisión**: `musst.engine` solo usa la biblioteca estándar.
- **Alternativas**: numpy para acelerar la evaluación.
- **Ventajas**: se instala en cualquier sitio; ningún riesgo de dependencias en el sandbox.
- **Limitaciones**: Monte Carlo más lento (mitigado con un número de muestras configurable por nivel).
- **Pruebas**: `tests/unit`, `tests/property`; el CI instala el wheel y juega una partida.

## ADR-002 · El motor es la única autoridad

- **Problema**: ni la IA ni el frontend deben poder hacer trampas o romper la partida.
- **Decisión**: toda acción pasa por `MusGame.validate`; las ilegales lanzan `IllegalAction` sin cambiar el estado.
- **Alternativas**: confiar en que el frontend solo muestre acciones legales.
- **Pruebas**: `test_accion_ilegal_rechazada_y_estado_intacto`, `test_en_torneo_el_bot_que_falla_pierde`.

## ADR-003 · Observaciones por lista blanca

- **Problema**: información privada (Req 5.1.1).
- **Decisión**: `build_observation` copia campos concretos; nunca se serializa `MusGame`.
- **Pruebas**: `tests/privacy` (60 partidas aleatorias × 4 asientos × cada paso).

## ADR-004 · Turnos secuenciales

- **Problema**: en la mesa física se habla a la vez (FEM VI.1, VI.4).
- **Decisión**: el motor da la palabra de uno en uno; "vale el quiero" se modela dando la palabra al compañero tras un "no quiero".
- **Limitación**: no se modelan las declaraciones simultáneas de una pareja (imposibles en digital).

## ADR-005 · Frontend sin framework ni paso de compilación

- **Problema**: la mesa necesita control fino de la interfaz, pero el equipo debe poder explicarlo todo.
- **Decisión**: HTML + CSS + JavaScript (módulos ES) servidos por FastAPI. **Cambia el diseño
  inicial** (TypeScript + Vite) porque el entorno no tiene Node y un paso de compilación no
  aportaba lo suficiente.
- **Alternativas**: Streamlit (menos control visual), React/Vite (requiere Node).
- **Limitaciones**: sin tipado estático en el cliente.

## ADR-006 · Persistencia con `sqlite3` + repositorio

- **Decisión**: `sqlite3` de la biblioteca estándar detrás de `Repository`. **Cambia el
  diseño inicial** (SQLAlchemy + Alembic) para no añadir dependencias.
- **Migración a PostgreSQL**: implementar la misma interfaz con `psycopg`; el esquema SQL es estándar.
- **Pruebas**: `tests/integration/test_api.py` usa una BD en memoria.

## ADR-007 · Contraseñas con `hashlib.scrypt`

- **Decisión**: scrypt (N=2^14, r=8, p=1) con sal aleatoria, de la biblioteca estándar. **Cambia
  el diseño inicial** (argon2id) para evitar una dependencia con extensiones C.
- **Pruebas**: `test_registro_login_hash_y_estadisticas` comprueba que no se guarda la contraseña.

## ADR-008 · Modelo del rival interpretable (Beta + back-off)

- **Problema**: aprender "hace X cuando ocurre Y" con pocas partidas.
- **Decisión**: tasas Beta por (métrica, lance, marcador) con encogimiento jerárquico hacia el contexto padre.
- **Alternativas**: clasificadores o RL (la interfaz `ModelStore`/`Learner` permite añadirlos).
- **Pruebas**: `tests/unit/test_player_model.py` con jugadores sintéticos.

## ADR-009 · Selección adversa en el agente de probabilidad

- **Problema**: las primeras versiones de los bots basados en agentes perdían contra el bot
  sencillo: lanzaban órdagos y subidas suponiendo que el rival aceptaría con cualquier mano.
- **Decisión**: el Monte Carlo estima P(acepta) y P(ganar | acepta) con un modelo de política
  del rival (umbral de fuerza), pondera los mundos por la verosimilitud de sus envites y aplica
  una probabilidad mínima de aceptación por la incertidumbre sobre su política.
- **Pruebas**: `experiments/level_ladder.py`.

## ADR-010 · Mus duplicado en el torneo

- **Problema**: el azar del reparto domina pocas partidas.
- **Decisión**: cada seed se juega dos veces intercambiando las parejas de asiento.
- **Pruebas**: `tests/integration/test_arena.py` (reproducibilidad y bot roto).

## ADR-011 · Web en GitHub Pages con Python en el navegador (Pyodide)

- **Problema**: la web debe publicarse en GitHub Pages, que solo sirve ficheros estáticos.
- **Decisión**: el frontend habla con el mismo `/api/...`, pero en Pages las peticiones las
  atiende `musst.web.backend` dentro de un **Web Worker** con **Pyodide**. La lógica de la API
  se movió a `musst.server.service.MusService`, que usan tanto FastAPI como el navegador: no hay
  dos implementaciones. Los datos (perfil, partidas, estadísticas, modelo del jugador) se guardan
  en SQLite sobre IndexedDB.
- **Alternativas**: servidor en Render/HF Spaces (arranque en frío, cuentas externas);
  reescribir el motor en JavaScript (dos motores que mantener).
- **Ventajas**: gratis, sin servidor, el mismo código Python y las mismas pruebas; los bots
  piensan en un worker y la mesa no se congela.
- **Limitaciones (aceptadas)**:
    - Las cartas de los bots están en la memoria del navegador del jugador. El frontend sigue
      recibiendo solo la observación de su asiento, pero alguien con conocimientos podría leerlas.
      Solo se engaña a sí mismo: no hay ranking de humanos en esta versión.
    - Perfil local sin contraseña; los datos no salen del navegador.
    - Sin compañero humano por invitación ni bots externos en subproceso (requieren servidor).
      El torneo con todos los bots se ejecuta en GitHub Actions y se publica en `scoreboard/`.
    - Primera carga: unos 10 MB de Pyodide desde jsDelivr (después, caché).
- **Pruebas**: `tests/integration/test_web_backend.py`; el job `web` del CI genera el sitio y
  comprueba que el paquete funciona sin FastAPI; prueba manual en Chrome (partida completa,
  perfil y estadísticas tras recargar).
