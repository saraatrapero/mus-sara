"""H8: el replay guardado es idéntico al log que se obtiene reejecutando seed + acciones."""

from musst.engine.config import RulesConfig
from musst.engine.game import MusGame
from musst.server.sessions import replay_actions
from musst.web.backend import LocalBackend
from tests.integration.test_web_backend import play_until_end


def test_replay_identico_al_log_reejecutado(tmp_path):
    b = LocalBackend(tmp_path)
    b.handle("POST", "/api/auth/login", {"username": "sara"}, None)
    _, data = b.handle(
        "POST", "/api/games", {"seed": 11, "target": 15, "rivals": "profesional"}, None
    )
    gid, token = data["game_id"], data["seat_token"]
    b.handle("POST", f"/api/games/{gid}/deal", None, token)
    for _ in range(3):
        _, obs = b.handle("POST", f"/api/games/{gid}/tick", None, token)
    play_until_end(b, gid, token, obs)
    status, replay = b.handle("GET", f"/api/games/{data['game_id']}/replay", None, None)
    assert status == 200

    stored = b.repo.load_game(data["game_id"])
    game = MusGame(seed=stored["seed"], config=RulesConfig.from_dict(stored["config"]))
    replay_actions(game, stored["actions"])
    assert any("tick" in a for a in stored["actions"])

    assert game.finished
    assert replay["history"] == [e.to_dict() for e in game.events if e.visible_to(None)]
    assert list(game.result.score) == list(replay["score"])
    assert game.result.winner == replay["winner"]
