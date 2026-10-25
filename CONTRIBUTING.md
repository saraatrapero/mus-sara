# Contribuir a MUS.ST

## Flujo de trabajo

- `main` está protegida: solo recibe merges desde `develop` en los hitos.
- `develop` es la rama de integración (también protegida).
- Trabaja en `feature/<fase>-<descripcion>` y abre un Pull Request a `develop`.
- Cada PR ejecuta automáticamente lint, tipos y tests (`.github/workflows/ci.yml`).

## Entorno

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
mypy src/musst/engine
```

## Añadir un bot

Sigue el tutorial de [docs/bot-api.md](docs/bot-api.md). Resumen: crea `bots/<nombre>/`
con `bot.py`, `bot.toml` y `README.md`, y abre un PR. Los tests de conformidad se ejecutan
solos sobre tu bot.
