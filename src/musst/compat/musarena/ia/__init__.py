"""Bot inteligente: una red neuronal que decide a partir de la observación.

- :mod:`~musst.compat.musarena.ia.acciones`: catálogo fijo de acciones que puede elegir la red.
- :mod:`~musst.compat.musarena.ia.codificacion`: traduce una :class:`~musst.compat.musarena.observation.Observation` a
  un vector de números.
- :mod:`~musst.compat.musarena.ia.red`: la red neuronal, que para jugar solo necesita numpy.
- :mod:`~musst.compat.musarena.ia.entrenamiento`: generación de datos y entrenamiento (necesita PyTorch:
  ``pip install -e ".[ia]"``).

Jugar con el bot no requiere PyTorch; entrenarlo, sí.
"""
