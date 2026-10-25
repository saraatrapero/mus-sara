# 11 — QUESTIONS FOR PROFESSOR

Preguntas que debe validar el profesor (Javier Paris) **antes de empezar la Fase 2**.

| Pregunta | Estado |
|---|---|
| P1 — 4 jugadores | ✅ **Resuelta**: se permite el Mus de 4 jugadores |
| P3 — Dificultad | ✅ **Resuelta**: dificultad **5** |
| P10 a — Infraestructura | ✅ **Resuelta**: la web se publica en GitHub Pages con Python en el navegador (Pyodide) |
| Resto | Pendientes |

## P1 — CONFLICTO: el Mus se juega con 4 jugadores en 2 parejas ✅ resuelta

> **Respuesta del profesor (correo, 2026):** *"tenéis permitido el uso del juego del MUS para
> 4 jugadores para la práctica de programación de la asignatura. […] el hecho de tener 4
> jugadores va a complicar altamente el diseño y generación de una estrategia buena para el
> juego. Sabiendo esto, si preferís mantener ese juego, me parece bien."*
>
> **Decisión:** se mantiene el Mus FEM de 4 jugadores en 2 parejas (opción A), sin cambios en
> el motor.

**Hecho.** La práctica dice: *"Cada equipo elegirá un juego de 2 jugadores"* (§3) y *"Como
condición previa, el juego elegido debe ser un juego por turnos de 2 jugadores y debe estar
validado por el profesor"* (§4, §5). El Mus reglamentario FEM es un juego de **4 jugadores en 2
parejas**, con información oculta y turnos que rotan entre los cuatro asientos.

**No hemos cambiado el juego.** Proponemos y pedimos validar una de estas opciones:

| Opción | Descripción | Ventajas | Inconvenientes |
|---|---|---|---|
| **A (preferida)** | Mus FEM de 4 jugadores. **La unidad competitiva es la pareja**: en el torneo cada participante es un bot que ocupa los dos asientos de su pareja como **dos instancias aisladas** (cada una ve solo sus cartas). Cada enfrentamiento es participante A contra participante B. | Fiel al Reglamento; el torneo es de 2 contendientes; el API sigue siendo por asiento | Técnicamente son 4 asientos por partida, no 2 |
| B | Igual que A, pero un bot controla **la pareja completa** con un único `decide` y ve las dos manos | Literalmente "2 jugadores" | Da a la pareja información que en el Mus real no tiene (los compañeros no ven sus cartas); desvirtúa el juego |
| C | "Mus a dos" (variante no reglamentaria) | Encaja literalmente | **Contradice el Reglamento FEM**; no lo recomendamos |

Además, ¿se acepta la composición de la interfaz pedida: **humano + compañero (humano o bot)
contra dos bots**?

## P2 — Requisito 1.2 con compañero

El Req 1.2 pide "una persona juega una partida completa contra un bot". ¿Cumple el requisito
con "humano + bot compañero contra pareja de bots"? En el MVP el compañero del humano será un
bot (dos humanos en la misma pareja requieren dos dispositivos, Riesgo R3).

## P3 — Dificultad del Mus para la Sección 3 ✅ resuelta

> **Respuesta del profesor:** *"La dificultad del MUS para 4 jugadores será de 5."* Con la
> puntuación de bots de 0.5 × dificultad, cada victoria vale **2.5**.

El Mus no aparece en la tabla de dificultades y la puntuación de bots es 0.5 × dificultad.
¿Qué dificultad se le asigna? (Tiene información oculta, azar, 4 jugadores, envites y faroles.)

## P4 — Duración de la partida

FEM (Intro E): partidas "a cinco juegos ganados", cada juego de 40 a 60 tantos. Proponemos
**1 juego a 40 tantos** por partida (configurable a N juegos y 40-60). ¿Es aceptable?

## P5 — Reglas que la FEM no especifica

El Reglamento no define el valor de las cartas ni de las jugadas. Proponemos las convenciones
del Mus tradicional (doc 03 §1.1 y §4.2): orden de grande y chica, valores para juego/punto,
par 1 / medias 2 / duples 3, juego 31 = 3 y resto = 2, punto 1, orden 31 > 32 > 40 > 37…33,
empates a favor del mano, descarte mínimo de 1 carta. ¿De acuerdo, o hay alguna variante preferida?

## P6 — "A falta de tanto" (FEM IV.7)

¿Se interpreta como "cuando a una pareja le falta 1 tanto" o como "cuando la pareja está
dentro (≤ 4)" (VII.7)? Proponemos ≤ 4, configurable.

## P7 — Reenvido

FEM VIII.8 define *reenvido* como "doblar el valor de la apuesta", aunque en la práctica se
sube "N más". Proponemos: subida libre de N ≥ 2 sobre la apuesta vigente, con un botón
"Reenvido" que dobla. ¿Correcto?

## P8 — Fin del juego durante la jugada y "deje"

a) Si una negada en el acto lleva a una pareja a 40, ¿termina inmediatamente? (Proponemos sí.)
b) Interpretación del *deje* (FEM VII.1, VIII.8): proponemos que, si se rechaza un revoque en
pares/juego/punto, la pareja que revocó gana el valor de la apuesta vigente y además cobra al
final el valor de sus propias jugadas. ¿Correcto?

## P9 — Señas

¿Se espera implementar señas (FEM VIII) en la versión evaluable? Proponemos dejarlas
preparadas (`SignalSystem`) y desactivadas en v1.

## P10 — Infraestructura

a) ✅ **Resuelta**: la web se publica en **GitHub Pages** y Python se ejecuta en el navegador
con **Pyodide** (ADR-011). El servidor FastAPI sigue disponible para uso local, invitaciones y
el torneo. Contrapartida aceptada: en el navegador las cartas de los bots están en la memoria
del propio jugador (ver ADR-011).
~~¿Es válido un backend FastAPI en un hosting gratuito (Render / HF Spaces) además de GitHub
Pages?~~
b) Los bots de otros equipos (Req 3.3): ¿se espera que respeten nuestro protocolo de sandbox
(subproceso + JSON), o basta con heredar de `Bot`?
