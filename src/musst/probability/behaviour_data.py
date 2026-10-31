"""Modelo de decisiones P(acción | fuerza de la mano) = σ(a + b·s), ajustado por máxima
verosimilitud con ``scripts/behaviour_fit.py``. Generado automáticamente: no editar a mano.

Claves: (lance o ``*`` para todos, decisión) → (a, b, casos, casos positivos).
"""

GAMES = 1000
FIRST_SEED = 0
BOTS = "medio"
FITS: dict[tuple[str, str], tuple[float, float, int, int]] = {
    ("*", "envida"): (-2.8276, 4.65, 41064, 14651),
    ("*", "ordago_abre"): (-10.717, 11.1319, 41064, 2396),
    ("*", "ordago_responde"): (-11.9547, 11.5652, 19746, 512),
    ("*", "quiere"): (-2.3041, 4.8001, 19746, 8701),
    ("*", "quiere_ordago"): (-6.7425, 6.6141, 4964, 314),
    ("chica", "envida"): (-2.5345, 3.8385, 15251, 4333),
    ("chica", "ordago_abre"): (-9.7678, 10.2682, 15251, 615),
    ("chica", "ordago_responde"): (-12.0495, 12.2596, 6467, 126),
    ("chica", "quiere"): (-1.9605, 4.4261, 6467, 2639),
    ("chica", "quiere_ordago"): (-10.4759, 13.1919, 1449, 65),
    ("grande", "envida"): (-2.6282, 3.9786, 14964, 4718),
    ("grande", "ordago_abre"): (-10.1548, 11.0111, 14964, 786),
    ("grande", "ordago_responde"): (-12.0109, 12.5436, 6972, 199),
    ("grande", "quiere"): (-2.6085, 5.7849, 6972, 3092),
    ("grande", "quiere_ordago"): (-14.1595, 19.0627, 1898, 139),
    ("juego", "envida"): (-6.3472, 8.1807, 2183, 1028),
    ("juego", "ordago_abre"): (-54.9988, 55.6049, 2183, 505),
    ("juego", "quiere"): (-2.7065, 3.9935, 604, 291),
    ("juego", "quiere_ordago"): (-24.0295, 21.0425, 540, 9),
    ("pares", "envida"): (-5.1672, 10.0916, 7130, 3888),
    ("pares", "ordago_abre"): (-56.0435, 56.5163, 7130, 361),
    ("pares", "ordago_responde"): (-43.5926, 43.5492, 4714, 164),
    ("pares", "quiere"): (-3.7847, 7.1357, 4714, 2215),
    ("pares", "quiere_ordago"): (-9.2124, 10.1143, 792, 86),
    ("punto", "envida"): (-2.7888, 5.2539, 1536, 684),
    ("punto", "ordago_abre"): (-22.0574, 23.4296, 1536, 129),
    ("punto", "ordago_responde"): (-22.3216, 21.4127, 989, 19),
    ("punto", "quiere"): (-1.504, 3.2182, 989, 464),
    ("punto", "quiere_ordago"): (-19.1312, 20.2811, 285, 15),
}
