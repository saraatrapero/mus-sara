"""Tests de conformidad que todo bot del repositorio debe pasar antes de fusionarse (Req 2.2).

Se parametrizan automáticamente con todos los bots registrados (internos y ``bots/*``).
"""

import pytest

from musst import play_game
from musst.bots.api import Bot
from musst.bots.builtin import RandomBot, SimpleBot
from musst.bots.registry import all_entries

ENTRIES = all_entries(sandboxed=True)
SEEDS = [101, 202, 303]


@pytest.fixture(params=ENTRIES, ids=[e.name for e in ENTRIES])
def entry(request):
    return request.param


def test_metadatos_validos(entry):
    assert (entry.name and entry.name.isidentifier()) or entry.name.replace("-", "_").isidentifier()
    bot = entry.factory()
    assert isinstance(bot, Bot)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("rival", [RandomBot, SimpleBot])
def test_juega_partidas_completas_sin_errores(entry, seed, rival):
    bots = [entry.factory(), rival(seed), entry.factory(), rival(seed + 1)]
    match = play_game(bots, seed=seed, mode="tournament", time_limit_s=5.0)
    assert not match.errors, f"{entry.name}: {match.errors}"
    assert match.result.reason in ("points", "ordago")


def test_respeta_el_limite_de_tiempo(entry):
    match = play_game(
        [entry.factory(), SimpleBot(1), entry.factory(), SimpleBot(2)], seed=9, mode="tournament"
    )
    times = sorted(t for seat in (0, 2) for t in match.decision_times[seat])
    if times:
        p99 = times[int(0.99 * (len(times) - 1))]
        assert p99 < 2.0
