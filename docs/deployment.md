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

## Cuentas de usuario

**Por defecto (solo GitHub Pages)**: usuario y contraseña guardados en el navegador (ADR-015).
La primera cuenta que se registra es la administradora y ve el menú **Admin**: usuarios
(crear, editar, borrar), actividad, resultados contra cada nivel, estilos que detecta la IA y
autocrítica de los bots.

### Cuentas compartidas entre dispositivos (Supabase)

Con Supabase las cuentas, los **campeonatos** (con inscripción desde cualquier móvil u ordenador)
y la **publicidad** de la mesa son los mismos para todo el mundo. Unos 10 minutos:

1. Crea un proyecto gratuito en https://supabase.com (*New project*; apunta la contraseña de la
   base de datos en un sitio seguro, no hace falta para nada de lo que sigue).
2. *Authentication → Sign In / Providers → Email*: desactiva **Confirm email** (los usuarios
   entran con nombre de usuario; el correo es interno).
3. *SQL Editor → New query*: pega **todo** `supabase/schema.sql` y pulsa **Run**. Es idempotente:
   cuando el esquema cambie, se vuelve a pegar y ejecutar entero.
4. En GitHub, *Settings → Secrets and variables → Actions → pestaña Variables → New repository
   variable*: crea `SUPABASE_URL` y `SUPABASE_ANON_KEY` con los valores de Supabase
   (*Project Settings → Data API / API Keys*: «Project URL» y la clave **anon public**). Son
   públicas por diseño; **nunca** uses la clave `service_role`.
5. En GitHub, *Actions → «Web, documentación (GitHub Pages) y scoreboard» → Run workflow*, para
   publicar la web con esas variables.
6. Entra en la web y crea tu cuenta (p. ej. `sara`). Después hazte administradora en el
   *SQL Editor* de Supabase:
   `update public.profiles set role = 'admin' where username = 'sara';`
   Desde entonces puedes hacer administradoras a otras cuentas desde el panel **Admin**.

Sin esas variables la web usa las cuentas del navegador.

### Publicidad en la mesa

En **Admin → Publicidad en la mesa** se elige la marca, el color o el logo del reverso de las
cartas de los bots, y la consumición (cerveza, refresco, café o agua) que cada jugador tiene al
lado de sus cartas, con su marca. Se guarda en la tabla `site_settings` y la ve todo el mundo,
también sin sesión; solo la cambia un administrador (`admin_set_ads` valida colores, textos y que
los logos sean PNG, JPEG o WebP de 290 KB como mucho). Sin Supabase se guarda en el navegador.

### Campeonatos

Eliminatorias de **8, 16 o 32 parejas** (mínimo 8: cuartos de final, semifinales y final; con
16, también octavos). Tablas `championships`, `champ_teams` y `champ_matches`; todos los cambios
pasan por funciones que comprueban quién llama (RLS).

1. La administración crea el campeonato en **Admin → Campeonatos**: nombre, fecha y hora de
   comienzo, número de parejas, a 30 o a 40 y con o sin señas.
2. Hasta esa fecha, cada persona se apunta en **Campeonatos** con un nombre de pareja: con un bot
   de compañero o con una plaza libre para otra persona («Unirme como compañero»).
3. Al llegar la fecha (o con «Empezar ya»), se sortea el cuadro y las plazas libres se llenan con
   parejas de bots. Los partidos entre bots se deciden solos.
4. Cada pareja pulsa **Jugar mi partido** en el cuadro; al terminar, el resultado se apunta solo y
   el ganador pasa de ronda. En la final los rivales bot son del nivel profesional.
5. Si se cruzan dos parejas de personas, lo juegan juntas y la administración apunta el resultado
   («Dar el partido»); lo mismo si una pareja no se presenta.

Límite conocido: como la partida se juega en el navegador (GitHub Pages no tiene servidor), el
resultado lo envía el navegador de quien juega; una persona con conocimientos técnicos podría
falsearlo. Para un campeonato con premios de verdad, mejor el servidor (abajo).

### Salas online (dos o cuatro personas)

Con **Dos personas** o **Cuatro personas** en «Jugar», la web abre una **sala con un código de
6 letras** (sin 0/O ni 1/I para que no se confundan). Los demás entran desde su móvil u ordenador
escribiendo el código en **Unirme a la sala**, o con el enlace `…/#sala/CÓDIGO`. Hay que tener
cuenta (Supabase) para crear o unirse.

- Asientos: primero el compañero/a (enfrente) y después los dos rivales. Quien crea la sala puede
  empezar en cuanto haya alguien más; los asientos vacíos los juegan bots.
- La partida corre en el navegador de quien crea la sala (GitHub Pages no tiene servidor). Tras
  cada cambio publica a cada persona **solo lo que ve su asiento** (`room_views`, cada fila la lee
  solo su dueño) y recoge lo que hacen los demás (`room_actions`). Quien crea la sala tiene que
  dejar la partida abierta hasta el final.
- Tablas `rooms`, `room_views` y `room_actions`, y funciones `room_*` en `supabase/schema.sql`:
  para activarlas, vuelve a pegar el `schema.sql` entero en el SQL Editor de Supabase.
- Las salas de más de 2 días se borran solas al crear otra.

Límite conocido: el navegador de quien crea la sala tiene la partida entera, así que una persona
con conocimientos técnicos podría ver las cartas de los demás desde ese navegador. Sin Supabase,
«Dos personas» y «Cuatro personas» se juegan pasándose el mismo dispositivo, como antes.

## Alternativa con servidor

El mismo `Dockerfile` y `render.yaml` permiten desplegar el servidor FastAPI en Render o Hugging
Face Spaces si se necesitan cuentas con contraseña, invitaciones o que las cartas de los bots no
lleguen nunca al navegador.

## Documentación

Se publica en GitHub Pages, en https://saraatrapero.github.io/mus-sara/docs/, con el mismo
workflow que la web (`mkdocs build --site-dir site/docs`).

También está preparada para ReadTheDocs:

`.readthedocs.yaml` + `mkdocs.yml`. Importa el repositorio en readthedocs.org; cada push a
`main` publica la documentación.

## Scoreboard (GitHub Pages)

El mismo workflow publica la clasificación en `scoreboard/`; la Bot Arena de la web la lee de ahí.
