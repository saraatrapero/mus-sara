# Bot `car_lu`

Autoras: **Carmen Cuerva y Lucía Argüello** (de ahí el nombre: *car*men + *lu*cía).

Juega con simulación Monte Carlo sobre las cartas que no ve y decide pensando en ganar la
partida entera, no solo el lance. Usa solo la `Observation` y el `toolkit` público.

## Estrategia (versión 2)

- **Mus**: sitúa su mano en el percentil de 3.000 manos aleatorias y corta desde el
  percentil 62. El umbral baja si es mano (gana los empates), si los rivales han pedido mus o
  si el rival está cerca de ganar; sube si su compañero ha pedido mus. Con 31 corta siempre.
- **Descarte**: prueba los 15 descartes posibles, simula 40 robos de las cartas no vistas para
  cada uno y se queda con el que deja mejor mano esperada.
- **Mundos simulados**: en cada decisión reparte 300 veces manos a los otros tres, compatibles
  con lo declarado (pares sí/no, juego sí/no), y pesa cada reparto según lo que ha hecho cada
  jugador en esta mano: quien envida o quiere pesa `(0,05 + fuerza)^5` y quien pasa,
  `1,05 − fuerza`.
- **Valor de la partida**: en cada mundo calcula quién gana el lance y cuántos tantos de
  jugada cobraría cada pareja. Para querer o no compara la probabilidad de ganar la partida en
  los dos casos, teniendo en cuenta que, tras un "no quiero" en pares, juego o punto, el rival
  cobra el deje **y además sus jugadas**.
- **Dejar hablar al compañero**: si el compañero todavía tiene que contestar al envite, solo
  quiere con lo que gana con su propia mano.
- **Envites**: envida desde un 64 % de probabilidad de ganar el lance, más tantos cuanto más
  clara es la mano; reenvida desde el 82 %. Con mano muy buena y un rival detrás, a veces
  pasa para cazar su envite. Va de farol de vez en cuando, sobre todo si habla el último.
- **Órdago**: no lo echa por iniciativa propia; acepta el del rival solo si eso mejora su
  probabilidad de ganar la partida frente a no quererlo.

Si algo falla dentro del bot, devuelve una acción legal prudente (pasar, no querer o cortar)
en lugar de lanzar una excepción. Cada decisión tarda menos de 0,2 s (el límite es 2 s).

## Cómo lo mejoramos (de la v1 a la v2)

1. **Calibración**: registramos, en cada decisión, la probabilidad que estimaba el bot y
   quién ganaba de verdad el lance. Al responder a un envite, la v1 era demasiado optimista:
   cuando creía ganar un 60-80 % de las veces, ganaba la mitad. Leía los envites rivales con
   muy poco peso. Con la lectura nueva, las estimaciones coinciden con lo que pasa en la mesa.
2. **Partida, no lance**: decidir querer o no con la probabilidad de ganar la partida y con
   los tantos de jugada que cobra cada pareja.
3. **Ablaciones**: probamos a quitar cada pieza por separado. Echar órdagos por iniciativa
   propia restaba unos 3-4 puntos, así que se quitó; dejar hablar al compañero sumaba.

Ideas de partida tomadas de la lectura del bot `reglas` (mus-cunef): decidir según la
partida, dejar al compañero y pasar para querer. La implementación (mundos simulados con
pesos, cálculo de tantos y calibración) es nuestra.

## Resultados

60 partidas contra cada bot (30 repartos jugados en los dos sentidos, mus duplicado), con las
mismas semillas para las dos versiones:

| rival | random | ejemplo | sencillo | medio | profesional | matematico | basico | reglas | inteligente | media |
|---|---|---|---|---|---|---|---|---|---|---|
| v1 | 78 % | 95 % | 48 % | 43 % | 38 % | 58 % | 58 % | 30 % | 28 % | 53 % |
| **v2** | **88 %** | 77 % | **60 %** | **50 %** | **53 %** | 57 % | **63 %** | **47 %** | **32 %** | **59 %** |

Con 60 partidas el margen de error ronda ±12 puntos por rival; la media sobre los nueve
rivales es bastante más fiable (±4 puntos).
