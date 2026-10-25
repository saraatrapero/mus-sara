"""Proceso hijo del sandbox: carga un bot y responde por stdin/stdout (JSON por líneas).

Uso interno: ``python -m musst.bots.sandbox_worker modulo:Clase``.
"""

from __future__ import annotations

import importlib
import io
import json
import sys
import traceback
from contextlib import redirect_stdout
from typing import Any

from musst.bots.api import Bot, GameEndInfo, GameStartInfo
from musst.engine.actions import action_to_dict
from musst.engine.observation import Observation


def load_bot(entrypoint: str) -> Bot:
    module_name, _, class_name = entrypoint.partition(":")
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    bot = cls()
    if not isinstance(bot, Bot):
        raise TypeError(f"{entrypoint} no hereda de musst.bots.api.Bot")
    return bot


def handle(bot: Bot, message: dict[str, Any]) -> dict[str, Any]:
    cmd = message.get("cmd")
    if cmd == "start":
        bot.on_game_start(GameStartInfo.from_dict(message["info"]))
        return {"ok": True}
    if cmd == "decide":
        action = bot.decide(Observation.from_dict(message["obs"]))
        return {"action": action_to_dict(action)}
    if cmd == "end":
        bot.on_game_end(GameEndInfo.from_dict(message["info"]))
        return {"ok": True}
    return {"error": f"comando desconocido {cmd!r}"}


def main() -> None:
    out = sys.stdout
    try:
        bot = load_bot(sys.argv[1])
    except Exception:
        bot = None
        load_error = traceback.format_exc(limit=3)
    for line in sys.stdin:
        try:
            if bot is None:
                reply: dict[str, Any] = {"error": f"no se pudo cargar el bot: {load_error}"}
            else:
                # Los print() del bot no deben corromper el protocolo.
                with redirect_stdout(io.StringIO()):
                    reply = handle(bot, json.loads(line))
        except Exception:
            reply = {"error": traceback.format_exc(limit=3)}
        out.write(json.dumps(reply) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
