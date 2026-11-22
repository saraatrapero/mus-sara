# Bot `compi`

Autores: **Equipo CONECTA_CUATRO**. Reglas sencillas, pero jugando **en pareja** y mirando el **marcador**:

- **Mus**: corta con 31 o 32, con medias o duples, o con una mano global buena (`hand_value ≥ 0,5`); si no, pide mus.
- **Descarte**: va a por juego y pares. Guarda las figuras (sota, caballo y rey, que valen 10) y las parejas, y tira lo demás.
- **Pareja**: en pares y juego suma lo que ha cantado su compañero. Si los dos rivales han dicho que no tienen, sabe que el lance es suyo y envida.
- **Marcador**: se atreve más cuanto peor va la partida y es más prudente cuando va ganando.
- **Envites**: envida 2 desde 0,70 de fuerza y 4 desde 0,85; quiere desde 0,55 y sube desde 0,90.
- **Órdago**: lo echa con 0,90 de fuerza si el rival está a 5 tantos o menos de ganar; lo acepta con 0,85, o con 0,60 si el rival está a punto de ganar.

Es determinista y, si algo falla dentro del bot, responde con una acción legal prudente en vez de lanzar una excepción.
