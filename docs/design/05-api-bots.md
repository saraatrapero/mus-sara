# 05 — API de bots, sandbox, torneo y scoreboard

## 1. Contrato público (Req 2.1)

```python
# musst/bots/api.py — la ÚNICA superficie que un bot externo necesita importar
from abc import ABC, abstractmethod

class Bot(ABC):
    """Jugador autónomo de Mus. Controla UN asiento."""

    name: str = "unnamed"
    author: str = ""
    version: str = "0.1"

    def on_game_start(self, info: GameStartInfo) -> None:
        """Opcional. Asiento, pareja, configuración pública."""

    @abstractmethod
    def decide(self, observation: Observation) -> Action:
        """Devuelve una acción de observation.legal_actions. Obligatorio."""

    def on_event(self, event: PublicEventView) -> None:
        """Opcional. Recibe cada evento público (y los privados dirigidos a este asiento)."""

    def on_game_end(self, result: GameResultView) -> None:
        """Opcional. Incluye las manos reveladas: útil para aprender."""
```

Bot mínimo:

```python
from musst.bots.api import Bot, Observation, Action
import random

class RandomBot(Bot):
    name = "random"
    def decide(self, observation: Observation) -> Action:
        return random.choice(observation.legal_actions).sample()
```

Utilidades públicas (`musst.bots.toolkit`): evaluar la mano propia en cada lance, enumerar
manos rivales compatibles, simular Monte Carlo **sobre las cartas no vistas**. Son funciones
puras que trabajan sobre la `Observation`, nunca sobre el estado.

## 2. Ciclo de vida y protocolo

```
GameRunner                         SandboxRunner                     Proceso del bot
    │ necesita acción del asiento 2     │                                  │
    │──Observation────────────────────► │──JSON línea por stdin──────────► │ decide()
    │                                   │ ◄──JSON acción por stdout────────│
    │                                   │ (timeout: 2 s por defecto)       │
    │◄──Action | BotFailure─────────────│                                  │
    │ RulesEngine.validate              │                                  │
```

- Protocolo JSON por líneas, versionado (`"protocol": 1`).
- Si el bot devuelve una acción ilegal, excede el timeout, lanza una excepción o muere →
  `BotFailure(kind)`.
- **Fuera del torneo** (partida con humanos): se registra el fallo y el asiento juega con un
  `FallbackBot` (el legal más conservador: paso / no quiero / cortar mus / descartar 1) para no
  arruinar la partida del humano.
- **En el torneo**: la pareja de ese bot **pierde la partida** (Req 4.1) y se registra el error.

## 3. Sandbox — qué se garantiza y qué no

Python no tiene un sandbox seguro dentro del mismo proceso. Por eso **no se finge**: la
protección es por capas y está documentada.

| Capa | Mecanismo | Protege contra |
|---|---|---|
| Separación de información | El bot solo recibe la `Observation` JSON; nunca hay objetos del motor en su proceso | Leer el estado secreto, manipular el marcador |
| Proceso separado | `subprocess` con un intérprete limpio (`python -I`), cwd temporal vacío, entorno mínimo sin secretos | Acceso a memoria del motor, variables de entorno |
| Límites | `resource.setrlimit` (CPU, memoria, ficheros abiertos) en Linux; timeout de pared por decisión | Bucles infinitos, consumo de memoria |
| Revisión | Los bots externos entran **solo por PR revisado**; `bot-pr.yml` ejecuta los tests y un análisis estático (prohibidos `os.system`, `subprocess`, `socket`, `open` fuera de su carpeta…) | Código malicioso evidente |
| Entorno de torneo | GitHub Actions: contenedor efímero, sin secretos en el job del torneo, permisos `contents: read` | Daño persistente |
| Producción web | El servidor solo ejecuta bots **fusionados en `main`**; nunca sube código de usuarios en caliente | Ejecución arbitraria en el servidor |

Limitación declarada: un bot malicioso podría intentar leer ficheros del contenedor del CI.
Se mitiga con la revisión del PR y con que el job no tiene nada valioso. Si hiciera falta
aislamiento fuerte, la evolución sería ejecutar cada bot en un contenedor sin red (Docker con
`--network none`).

## 4. Registro y tests de conformidad (Req 2.2)

```
bots/
└── mi_bot/
    ├── bot.py          # define una clase que hereda de musst.bots.api.Bot
    ├── bot.toml        # name, author, entrypoint = "bot:MiBot", version
    └── README.md       # estrategia en 5-10 líneas
```

`tests/bot_conformance/` se parametriza automáticamente con todos los bots registrados:

1. Se importa y se instancia sin errores, con metadatos válidos.
2. Juega 20 partidas completas (seeds fijas) contra `RandomBot` y `SimpleBot` sin acciones ilegales.
3. Respeta el timeout en el percentil 99.
4. Es determinista si declara `deterministic = true`.
5. No modifica la `Observation` (es inmutable; se comprueba igualmente).
6. Supera la serialización por el protocolo de sandbox.

El workflow `bot-pr.yml` se dispara en los PR que tocan `bots/**` y publica un resumen en el PR.

## 5. Torneo (Req 4.1)

**Unidad de competición: la pareja.** Cada participante del torneo es un bot que ocupa **los
dos asientos de su pareja** como **dos instancias independientes** (dos procesos que no
comparten memoria; cada uno ve solo sus cartas). Así:

- un enfrentamiento es **participante A contra participante B**: un emparejamiento de
  dos contendientes, como pide la práctica (ver P1);
- no se rompe la información privada entre compañeros.

**Formato**

- Liga todos contra todos. Para cada par (A, B), `N` partidas (por defecto 20) con seeds fijas.
- **Mus duplicado** para reducir la suerte: cada seed se juega dos veces cambiando a las
  parejas de asiento, de modo que cada participante recibe las cartas que tuvo el otro.
- Resultado de un fallo: derrota de la pareja infractora, error anotado; el torneo sigue.
- Reproducible: `musst-arena run --seed 2026 --games 20`.

## 6. Clasificación y publicación (Req 4.2)

| Columna | Definición |
|---|---|
| Bot | nombre@versión |
| Partidas | jugadas |
| Victorias / Derrotas | |
| % Victorias | con intervalo de confianza de Wilson al 95 % |
| Tantos | a favor − en contra (media por partida) |
| Errores | ilegales + timeouts + crashes |
| Elo | opcional, para ordenar con muchos bots |

`tournament.yml` se ejecuta al hacer merge en `main` y cada noche. Genera `scoreboard.json` y
`scoreboard.html` y los publica en GitHub Pages. La web de MUS.ST lee ese JSON en la pantalla
de la Bot Arena.
