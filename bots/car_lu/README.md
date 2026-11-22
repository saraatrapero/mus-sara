# Bot `car_lu`

Autoras: **Carmen Cuerva y Lucía Argüello** (de ahí el nombre: *car*men + *lu*cía).

Juega con simulación Monte Carlo sobre las cartas que no ve, usando solo la `Observation` y
el `toolkit` público:

- **Mus**: corta con 31, duples, medias, juego con pares o una mano global fuerte
  (`hand_value ≥ 0.5`); si no, pide mus.
- **Descarte**: prueba los 15 descartes posibles, simula 40 robos de las cartas no vistas para
  cada uno y se queda con el que deja mejor mano esperada.
- **Lances**: estima P(nuestra pareja gana el lance) con 400 mundos compatibles con las
  declaraciones de pares y juego. Envida 2 desde el 62 %, 4 desde el 82 %, reenvida desde el
  85 % y se tira algún farol suelto.
- **Lectura de la jugada**: cada mundo simulado pesa más si encaja con lo que han hecho los
  demás en esta mano: quien envida, sube o quiere suele ir fuerte en ese lance; quien pasa o
  no quiere, flojo. Sin esto ganaba bastante menos contra `medio` (36 % frente a 44-46 %).
- **Querer o no querer**: quiere solo si el valor esperado de aceptar (ganar o perder la
  apuesta) supera lo que cuesta el "no quiero", con un pequeño margen de prudencia.
- **Órdago**: lo echa con el lance prácticamente ganado (≥ 97 %) o cuando el rival está a
  punto de ganar la partida; lo acepta desde el 60 % (o antes si ya no hay nada que perder).

Si algo falla dentro del bot, devuelve una acción legal prudente (pasar, no querer o cortar)
en lugar de lanzar una excepción. Cada decisión tarda menos de 0,3 s (el límite es 2 s).

## Resultados

60 partidas contra cada bot (30 repartos jugados en los dos sentidos, mus duplicado):

| rival | random | ejemplo | sencillo | medio | profesional | matematico | basico | reglas | inteligente |
|---|---|---|---|---|---|---|---|---|---|
| % de victorias de `car_lu` | 78 % | 95 % | 48 % | 43 % | 38 % | 58 % | 58 % | 30 % | 28 % |

Con 60 partidas el margen de error ronda ±12 puntos, así que contra `sencillo` y `medio`
el resultado es prácticamente un empate.
