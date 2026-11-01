"""Análisis estratégico del mus, compartido por los bots.

- :mod:`~musst.compat.musarena.estrategia.tipos`: los 330 tipos de mano y sus propiedades precalculadas.
- :mod:`~musst.compat.musarena.estrategia.creencias`: qué manos puede tener cada jugador según lo visto.
- :mod:`~musst.compat.musarena.estrategia.evaluacion`: probabilidad de ganar cada lance, valor de una mano,
  descartes y probabilidad de ganar la vaca.

Todo trabaja a partir de una :class:`~musst.compat.musarena.observation.Observation`, así que no usa
información oculta: sirve igual para el bot heurístico que como entrada del bot entrenado.
"""
