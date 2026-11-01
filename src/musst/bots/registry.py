"""Registro de bots: internos y externos (carpeta ``bots/`` con ``bot.toml``)."""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from musst.bots.api import Bot

REPO_BOTS_DIR = Path(__file__).resolve().parents[3] / "bots"


@dataclass(frozen=True)
class BotEntry:
    name: str
    author: str
    version: str
    level: str
    factory: Callable[[], Bot]
    external: bool = False
    description: str = ""


def builtin_entries() -> list[BotEntry]:
    from musst.bots.builtin.math import MathBot
    from musst.bots.builtin.medium import MediumBot
    from musst.bots.builtin.pro import ProBot
    from musst.bots.builtin.simple import RandomBot, SimpleBot

    return [
        BotEntry(
            "random", "MUS.ST", "1.0", "random", RandomBot, description="Acciones legales al azar"
        ),
        BotEntry("sencillo", "MUS.ST", "1.0", "sencillo", SimpleBot, description="Heurísticas"),
        BotEntry(
            "medio", "MUS.ST", "1.0", "medio", MediumBot, description="Monte Carlo + marcador"
        ),
        BotEntry(
            "profesional",
            "MUS.ST",
            "1.0",
            "profesional",
            ProBot,
            description="Multiagente + modelo de jugador",
        ),
        BotEntry(
            "matematico",
            "MUS.ST",
            "1.0",
            "matematico",
            MathBot,
            description="Bayes + Monte Carlo exacto + valor esperado de P(ganar la partida)",
        ),
    ]


def external_entries(bots_dir: Path | None = None, sandboxed: bool = True) -> list[BotEntry]:
    """Bots externos declarados en ``bots/<nombre>/bot.toml``."""
    from musst.bots.sandbox import SubprocessBot

    root = bots_dir or REPO_BOTS_DIR
    entries: list[BotEntry] = []
    if not root.is_dir():
        return entries
    for manifest in sorted(root.glob("*/bot.toml")):
        with open(manifest, "rb") as fh:
            meta = tomllib.load(fh)
        bot_dir = manifest.parent
        entry = str(meta["entrypoint"])
        name = str(meta["name"])

        def factory(bot_dir: Path = bot_dir, entry: str = entry, name: str = name) -> Bot:
            if sandboxed:
                return SubprocessBot(bot_dir, entry, name=name)
            return _load_inprocess(bot_dir, entry)

        entries.append(
            BotEntry(
                name,
                str(meta.get("author", "")),
                str(meta.get("version", "0.1")),
                "externo",
                factory,
                external=True,
                description=str(meta.get("description", "")),
            )
        )
    return entries


def _load_inprocess(bot_dir: Path, entrypoint: str) -> Bot:
    import importlib.util

    module_name, _, class_name = entrypoint.partition(":")
    spec = importlib.util.spec_from_file_location(
        f"musst_external_{bot_dir.name}_{module_name}", bot_dir / f"{module_name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bot: Bot = getattr(module, class_name)()
    return bot


def all_entries(bots_dir: Path | None = None, sandboxed: bool = True) -> list[BotEntry]:
    return builtin_entries() + external_entries(bots_dir, sandboxed)


def get_entry(name: str) -> BotEntry:
    for entry in all_entries():
        if entry.name == name:
            return entry
    raise KeyError(f"Bot desconocido: {name}")
