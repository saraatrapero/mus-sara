# Despliegue

## En local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[web]"
MUSST_SECURE_COOKIES=0 uvicorn musst.server.app:app --reload
# http://localhost:8000
```

Variables de entorno:

| Variable | Defecto | Uso |
|---|---|---|
| `MUSST_DB` | `musst.sqlite3` | Ruta de la base de datos SQLite |
| `MUSST_SECURE_COOKIES` | `1` | Cookie de sesión `Secure` (ponla a `0` en http local) |
| `MUSST_DEV_MODE` | sin definir | `1` activa `/api/dev/*` (estado completo). **Nunca en producción** |
| `MUSST_SCOREBOARD` | `scoreboard_out/scoreboard.json` | Clasificación mostrada en la Bot Arena |

## Producción (gratuita)

La interfaz necesita un servidor: si el motor se ejecutara en el navegador, las cartas de los
bots estarían en la memoria del cliente.

1. **Render** (plan gratuito), con el `Dockerfile` y el `render.yaml` del repositorio:
   *New → Blueprint → este repositorio*. Arranque en frío de unos 30-60 s tras inactividad.
2. Alternativa: **Hugging Face Spaces** (SDK Docker) con el mismo `Dockerfile`, puerto 8000.
3. El disco de Render gratuito es efímero: para conservar usuarios y estadísticas entre
   despliegues, usar una PostgreSQL gratuita (Neon o Supabase) implementando `Repository` con
   `psycopg` (ver ADR-006).

## Documentación (ReadTheDocs)

`.readthedocs.yaml` + `mkdocs.yml`. Importa el repositorio en readthedocs.org; cada push a
`main` publica la documentación.

## Scoreboard (GitHub Pages)

`.github/workflows/tournament.yml` ejecuta el torneo en cada push a `main` y cada noche, y
publica `scoreboard/` en GitHub Pages. Activa *Settings → Pages → Source: GitHub Actions*.
