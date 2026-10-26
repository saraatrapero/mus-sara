"""Ejecución aislada de bots en un subproceso (protocolo JSON por líneas).

El proceso del bot **nunca** recibe objetos del motor: solo la observación serializada.
Ver ``docs/bot-api.md`` (sección *Sandbox*) para las garantías y sus límites.
"""

from __future__ import annotations

import contextlib
import json
import os
import selectors
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from musst.bots.api import Action, Bot, GameEndInfo, GameStartInfo, Observation
from musst.engine.actions import action_from_dict
from musst.runtime.runner import BotFailure

PROTOCOL_VERSION = 1


def _limit_resources() -> None:  # pragma: no cover - se ejecuta en el hijo
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        if sys.platform.startswith("linux"):
            limit = 1024 * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except Exception:
        pass


class SubprocessBot(Bot):
    """Adaptador que ejecuta ``entrypoint`` (``"modulo:Clase"``) en otro proceso."""

    def __init__(
        self,
        bot_dir: str | Path,
        entrypoint: str,
        name: str | None = None,
        timeout_s: float = 2.0,
        start_timeout_s: float = 10.0,
    ) -> None:
        self.bot_dir = Path(bot_dir).resolve()
        self.entrypoint = entrypoint
        self.name = name or entrypoint
        self.timeout_s = timeout_s
        self.start_timeout_s = start_timeout_s
        self._proc: subprocess.Popen[str] | None = None
        self._workdir: tempfile.TemporaryDirectory[str] | None = None

    # ------------------------------------------------------------- ciclo de vida
    def _spawn(self) -> None:
        self._workdir = tempfile.TemporaryDirectory(prefix="musst-bot-")
        src_root = str(Path(__file__).resolve().parents[2])
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.pathsep.join([src_root, str(self.bot_dir)]),
            "PYTHONHASHSEED": "0",
        }
        self._proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "musst.bots.sandbox_worker", self.entrypoint],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=self._workdir.name,
            env=env,
            preexec_fn=_limit_resources if os.name == "posix" else None,
        )

    def _request(self, message: dict[str, Any], timeout: float) -> dict[str, Any]:
        if self._proc is None or self._proc.poll() is not None:
            raise BotFailure("crash", "el proceso del bot no está activo")
        assert self._proc.stdin is not None and self._proc.stdout is not None
        try:
            self._proc.stdin.write(json.dumps(message) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise BotFailure("crash", repr(exc)) from exc
        sel = selectors.DefaultSelector()
        sel.register(self._proc.stdout, selectors.EVENT_READ)
        ready = sel.select(timeout)
        sel.close()
        if not ready:
            self.close()
            raise BotFailure("timeout", f"sin respuesta en {timeout}s")
        line = self._proc.stdout.readline()
        if not line:
            raise BotFailure("crash", "el bot cerró la salida")
        try:
            reply = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BotFailure("illegal", f"respuesta no JSON: {line[:100]!r}") from exc
        if not isinstance(reply, dict):
            raise BotFailure("illegal", "respuesta no es un objeto")
        if "error" in reply:
            raise BotFailure("exception", str(reply["error"])[:500])
        return reply

    def close(self) -> None:
        if self._proc is not None:
            if self._proc.poll() is None:
                self._proc.kill()
            self._proc.wait(timeout=5)
            for stream in (self._proc.stdin, self._proc.stdout):
                if stream is not None:
                    stream.close()
            self._proc = None
        if self._workdir is not None:
            self._workdir.cleanup()
            self._workdir = None

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.close()

    # ------------------------------------------------------------- API Bot
    def on_game_start(self, info: GameStartInfo) -> None:
        self.close()
        self._spawn()
        self._request(
            {"cmd": "start", "protocol": PROTOCOL_VERSION, "info": info.to_dict()},
            self.start_timeout_s,
        )

    def decide(self, observation: Observation) -> Action:
        reply = self._request({"cmd": "decide", "obs": observation.to_dict()}, self.timeout_s)
        try:
            return action_from_dict(reply["action"])
        except (KeyError, ValueError) as exc:
            raise BotFailure("illegal", f"acción malformada: {exc}") from exc

    def on_game_end(self, info: GameEndInfo) -> None:
        try:
            self._request({"cmd": "end", "info": info.to_dict()}, self.timeout_s)
        except BotFailure:
            pass
        finally:
            self.close()
