"""H8: el replay guardado es idéntico al log que se obtiene reejecutando seed + acciones."""

from musst.engine.actions import action_from_dict
from musst.engine.config import RulesConfig
from musst.engine.game import MusGame
from musst.web.backend import LocalBackend
from tests.integration.test_web_backend import play_until_end


def test_replay_identico_al_log_reejecutado(tmp_path):
    b = LocalBackend(tmp_path)
    b.handle("POST", "/api/auth/login", {"username": "sara"}, None)
    _, data = b.handle(
        "POST", "/api/games", {"seed": 11, "target": 15, "rivals": "profesional"}, None
    )
    play_until_end(b, data["game_id"], data["seat_token"], data["observation"])
    status, replay = b.handle("GET", f"/api/games/{data['game_id']}/replay", None, None)
    assert status == 200

    stored = b.repo.load_game(data["game_id"])
    game = MusGame(seed=stored["seed"], config=RulesConfig.from_dict(stored["config"]))
    for item in stored["actions"]:
        game.apply(item["seat"], action_from_dict(item["action"]))

    assert game.finished
    assert replay["history"] == [e.to_dict() for e in game.events if e.visible_to(None)]
    assert list(game.result.score) == list(replay["score"])
    assert game.result.winner == replay["winner"]
