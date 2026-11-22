# Bot `mi_bot`

De Daniela González y Marcos González. Bot de reglas sencillas:

- **Mus**: corta con juego de 31 o 32, con medias o duples, o si la mano es buena en general
  (`hand_value >= 0.45`). Si no, pide mus.
- **Descarte**: descarte clásico (`keep_heuristic_discard`): guarda reyes y parejas.
- **Probabilidad del lance**: con `estimate_lance_win` del toolkit simula 200 repartos de las
  cartas que no ve, compatibles con lo declarado (pares/juego), y calcula la probabilidad de que
  su pareja gane el lance. Así tiene en cuenta al compañero, a los rivales y quién es mano.
- **Envites**: envida 2 con probabilidad ≥ 0,70 y 4 con ≥ 0,85; reenvida con ≥ 0,90 y quiere
  con ≥ 0,55.
- **Órdago**: solo lo echa con ≥ 0,95 y a partir de media partida; lo acepta con ≥ 0,85.
- Si algo falla, devuelve siempre una acción legal prudente (pasar o no querer).
