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

## Producción: GitHub Pages con Pyodide

La web pública es estática: Python se ejecuta **en el navegador** con
[Pyodide](https://pyodide.org) (ADR-011).

```bash
python scripts/build_web.py --out site      # genera index.html, static/ y static/musst.zip
python -m http.server -d site 8001          # probar en http://localhost:8001
```

| Pieza | Qué hace |
|---|---|
| `scripts/build_web.py` | Copia el frontend, añade `<meta name="musst-backend" content="pyodide">` y empaqueta `musst` en `musst.zip` |
| `src/musst/web/worker.js` | Web Worker: carga Pyodide 0.26.4 y `sqlite3`, descomprime `musst.zip`, monta `/data` sobre IndexedDB y atiende las peticiones |
| `src/musst/web/backend.py` | Enruta `/api/...` a `MusService` (la misma lógica que el servidor) |

**Activar:** *Settings → Pages → Source: GitHub Actions*. El workflow
`.github/workflows/tournament.yml` genera la web, ejecuta el torneo y publica todo en cada push a
`main` y cada noche. URL: https://saraatrapero.github.io/mus-sara/

Diferencias con el servidor: perfil local sin contraseña, sin compañero humano por invitación y
sin bots externos en subproceso (el torneo los ejecuta en GitHub Actions).

## Alternativa con servidor

El mismo `Dockerfile` y `render.yaml` permiten desplegar el servidor FastAPI en Render o Hugging
Face Spaces si se necesitan cuentas con contraseña, invitaciones o que las cartas de los bots no
lleguen nunca al navegador.

## Documentación (ReadTheDocs)

`.readthedocs.yaml` + `mkdocs.yml`. Importa el repositorio en readthedocs.org; cada push a
`main` publica la documentación.

## Scoreboard (GitHub Pages)

El mismo workflow publica la clasificación en `scoreboard/`; la Bot Arena de la web la lee de ahí.
