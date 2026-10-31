"""Motor probabilístico de MUS.ST: combinatoria, Monte Carlo, Bayes y valor esperado.

Todo trabaja **solo** con la información de la :class:`~musst.engine.observation.Observation`
de un asiento y con los evaluadores del motor (:mod:`musst.engine.evaluation`); no hay reglas
del mus duplicadas aquí. Python estándar (compatible con Pyodide). Fundamentos y fórmulas:
``docs/probabilidad.md``.
"""
