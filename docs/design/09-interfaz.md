# 09 — Interfaz e identidad visual

## 1. Identidad

- **Concepto**: "una mesa de Mus tradicional llevada al mundo digital". Universitaria, sobria; nada de casino.
- **Paleta**: tapete verde botella profundo (no verde neón), madera nogal, papel marfil para
  las cartas, acentos en granate y oro viejo apagado. Modo oscuro con la misma paleta, menos luminosa.
- **Tipografía**: serif clásica para títulos (aire académico, p. ej. *Cormorant* / *Source
  Serif*), sans legible para la interfaz (*Inter*). Tamaño base configurable (100-150 %).
- **Cartas**: baraja española con ilustración limpia y reversos personalizables (escudo
  universitario, liso, clásico).
- **Avatares**: humanos en estilo cómic (generado a partir de foto o elegido en un set); bots
  como robots con un rasgo por nivel (Sencillo, Medio, Profesional).
- **Logros**: sobrios, como sellos o lacres, no como medallas brillantes.

## 2. Pantalla de partida

```
┌──────────────────────────────────────────────────────────────────┐
│ GRANDE ▸ chica ▸ pares ▸ juego/punto     Pareja humana 24 ▮▮▮▮·   │
│                                          Pareja bots   31 ▮▮▮▮▮▮· │
├──────────────────────────────────────────────────────────────────┤
│                         🤖 BOT 1  [Medio]                         │
│                   ○ mano   Pares: sí   Juego: —                  │
│                          🂠 🂠 🂠 🂠                                │
│  🤖 BOT 2                ┌──────────────┐          🧑 COMPAÑERO  │
│  Pares: no               │ MESA DE MUS  │          Pares: sí      │
│  🂠🂠🂠🂠                   │ "Envido 4"   │          🂠🂠🂠🂠          │
│                          │  amarracos   │                        │
│                          └──────────────┘                        │
│                     [R♣] [R♦] [C♠] [5♥]   ← TUS CARTAS            │
│         [ PASO ] [ ENVIDO ▾ ] [ ÓRDAGO ]          [ ? ]          │
└──────────────────────────────────────────────────────────────────┘
```

- **Barra de lances** con el lance actual resaltado (icono + texto, no solo color).
- **Marcador** con número y amarracos (1 amarraco = 5 tantos) e indicador "dentro" a ≤ 4 tantos.
- **Avatar**: nombre, pareja (icono de forma, no solo color), indicador de mano, estado
  (pensando / ha hablado / desconectado), pares sí/no y juego sí/no **solo cuando se han declarado**.
- **Bocadillos de acción**: MUS · NO MUS/CORTO · PASO · ENVIDO · QUIERO · NO QUIERO · ÓRDAGO,
  con animaciones de 150-300 ms. Con `prefers-reduced-motion` o el ajuste correspondiente, sin animación.
- **Acciones**: solo se muestran las legales (desde `observation.legal_actions`); el envido
  tiene un selector de cantidad. El servidor revalida siempre.
- **Botón ?**: abre "¿Qué puedo hacer ahora?", con las acciones legales explicadas. Nunca
  recomienda, salvo con el "modo ayuda" activado explícitamente.
- **Responsive**: en móvil (vertical) la mesa se compacta: rivales arriba en una fila,
  compañero en una banda superior, cartas propias y acciones fijas abajo (zona del pulgar).

## 3. Mapa de pantallas

```
Inicio
 ├─ Jugar ─┬─ Partida rápida (M1)
 │         ├─ Personalizada (M3)
 │         ├─ Contra un bot (M5)
 │         └─ Entrenamiento (M2) ── Situaciones
 ├─ Aprender ─┬─ Tutorial interactivo
 │            └─ Aprender jugando
 ├─ Competir ── Bot Arena (M4) ── Clasificación / Observar Bot vs Bot
 ├─ Analizar ─┬─ Historial (M6) ── Replay ⏮ ◀ ▶ ⏭ ── Análisis post-partida
 │            └─ Estadísticas / Estilo de juego
 └─ Perfil ── Avatar, ajustes (mesa, fondo, reverso, sonido, velocidad, tema, texto)
```

## 4. Post-partida

1. **Resumen**: resultado, marcador y duración.
2. **Momentos clave**: decisiones con mayor |ΔP(ganar la partida)| (calculadas tras la partida).
3. **Estadísticas** de la partida.
4. **Aprendizaje del bot**: "El bot ha actualizado su modelo sobre tu forma de jugar" + 2-3
   frases sobre **ti** (nunca sobre las cartas privadas de otros jugadores que no se hayan revelado).
5. **¿Y si…?** Simulación contrafactual: se fija la información del momento, se cambia tu
   acción y se simula con Monte Carlo. Solo disponible con la partida en `FINISHED`.

## 5. Accesibilidad

WCAG 2.1 AA: contraste ≥ 4.5:1; palos con forma y letra además del color; navegación con
teclado (atajos: P paso, E envido, Q quiero, N no quiero, O órdago); ARIA live para anunciar
acciones; tamaño de texto configurable; reducción de animaciones; botón global de silencio.

## 6. Sonido (opcional, desactivable)

Repartir, cortar, apostar, aceptar, ganar tantos, fin de partida. Sonidos cortos (< 400 ms),
volumen independiente y silencio global.
