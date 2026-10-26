"""API web: flujo de partida, seguridad e información privada."""

import json

import pytest
from fastapi.testclient import TestClient

from musst.persistence.db import Repository
from musst.server.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app(Repository(":memory:"), dev_mode=False))


def play_until_end(client, game_id, token, obs, limit=600):
    headers = {"X-Seat-Token": token}
    for _ in range(limit):
        if obs["finished"]:
            return obs
        if obs.get("awaiting_deal"):
            r = client.post(f"/api/games/{game_id}/deal", headers=headers)
            assert r.status_code == 200, r.text
            obs = r.json()
            continue
        assert obs["turn"] == obs["seat"]
        types = [a["type"] for a in obs["legal_actions"]]
        if "cut" in types:
            action = {"type": "cut"}
        elif "discard" in types:
            action = {"type": "discard", "cards": [obs["hand"][0]]}
        elif "accept" in types:
            action = {"type": "accept"}
        elif "pass" in types:
            action = {"type": "pass"}
        else:
            action = {"type": types[0]}
        r = client.post(f"/api/games/{game_id}/action", json={"action": action}, headers=headers)
        assert r.status_code == 200, r.text
        obs = r.json()
    raise AssertionError("la partida no terminó")


def test_partida_completa_humano_contra_bots(client):
    r = client.post("/api/games", json={"rivals": "sencillo", "partner": "sencillo", "seed": 4})
    assert r.status_code == 200
    data = r.json()
    obs = play_until_end(client, data["game_id"], data["seat_token"], data["observation"])
    assert obs["winner"] in (0, 1)
    analysis = client.get(
        f"/api/games/{data['game_id']}/analysis", headers={"X-Seat-Token": data["seat_token"]}
    )
    assert analysis.status_code == 200
    assert "stats" in analysis.json()


def test_la_observacion_no_contiene_cartas_de_otros(client):
    r = client.post("/api/games", json={"rivals": "medio", "seed": 9})
    data = r.json()
    game = client.app.state.manager.get(data["game_id"]).game
    text = json.dumps(r.json())
    for seat in (1, 2, 3):
        for card in game.hands[seat]:
            assert f'"{card.code}"' not in text


def test_sin_token_no_hay_acceso(client):
    data = client.post("/api/games", json={"seed": 1}).json()
    assert client.get(f"/api/games/{data['game_id']}").status_code == 403
    assert (
        client.get(f"/api/games/{data['game_id']}", headers={"X-Seat-Token": "falso"}).status_code
        == 403
    )
    assert client.get("/api/games/noexiste", headers={"X-Seat-Token": "x"}).status_code == 404


def test_accion_ilegal_rechazada_y_estado_intacto(client):
    data = client.post("/api/games", json={"seed": 1}).json()
    headers = {"X-Seat-Token": data["seat_token"]}
    before = client.get(f"/api/games/{data['game_id']}", headers=headers).json()
    r = client.post(
        f"/api/games/{data['game_id']}/action",
        json={"action": {"type": "bet", "amount": 999}},
        headers=headers,
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/games/{data['game_id']}/action",
        json={"action": {"type": "hackear"}},
        headers=headers,
    )
    assert r.status_code == 422
    after = client.get(f"/api/games/{data['game_id']}", headers=headers).json()
    assert before["history"] == after["history"]


def test_analisis_y_replay_solo_al_terminar(client):
    data = client.post("/api/games", json={"seed": 1}).json()
    headers = {"X-Seat-Token": data["seat_token"]}
    assert client.get(f"/api/games/{data['game_id']}/analysis", headers=headers).status_code == 403
    assert client.get(f"/api/games/{data['game_id']}/replay", headers=headers).status_code == 403


def test_modo_desarrollo_no_existe_en_produccion(client):
    data = client.post("/api/games", json={"seed": 1}).json()
    assert client.get(f"/api/dev/games/{data['game_id']}").status_code == 404


def test_registro_login_hash_y_estadisticas(client):
    r = client.post(
        "/api/auth/register", json={"username": "sara", "password": "contraseña-segura"}
    )
    assert r.status_code == 200
    repo = client.app.state.repo
    with repo.conn() as c:
        stored = c.execute("SELECT password_hash FROM users WHERE username='sara'").fetchone()[0]
    assert "contraseña" not in stored and stored.startswith("scrypt$")
    assert client.get("/api/me").json()["username"] == "sara"
    data = client.post("/api/games", json={"rivals": "profesional", "seed": 2}).json()
    play_until_end(client, data["game_id"], data["seat_token"], data["observation"])
    stats = client.get("/api/players/me/statistics").json()
    assert stats["partidas"] == 1
    assert "primera_partida" in stats["logros"]
    assert "aggression" in stats["estilo"]
    assert client.get(f"/api/games/{data['game_id']}/replay").status_code == 200
    assert len(client.get("/api/history").json()) == 1
    client.post("/api/auth/logout")
    assert client.get("/api/players/me/statistics").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"username": "sara", "password": "incorrecta1"}
        ).status_code
        == 401
    )


def test_compañero_humano_por_invitacion(client):
    data = client.post("/api/games", json={"partner": "human", "seed": 3}).json()
    invite = data["observation"]["invite"]
    assert invite
    r = client.post(f"/api/games/{data['game_id']}/join", json={"invite": invite, "name": "Ana"})
    assert r.status_code == 200
    partner_obs = r.json()["observation"]
    assert partner_obs["seat"] == 2
    assert (
        client.post(f"/api/games/{data['game_id']}/join", json={"invite": invite}).status_code
        == 403
    )


def test_ayuda_entrenamiento_y_arena(client):
    data = client.post("/api/games", json={"seed": 1}).json()
    helpme = client.get(
        f"/api/games/{data['game_id']}/help", headers={"X-Seat-Token": data["seat_token"]}
    ).json()
    assert "actions" in helpme
    scenarios = client.get("/api/training/scenarios").json()
    assert scenarios
    sc = scenarios[0]
    res = client.post(f"/api/training/scenarios/{sc['id']}", json={"action": {"type": "reject"}})
    assert res.status_code == 200 and "recomendacion" in res.json()
    watch = client.post(
        "/api/arena/watch", json={"team_a": "sencillo", "team_b": "random", "seed": 1}
    )
    assert watch.status_code == 200 and watch.json()["history"]
    assert client.get("/api/bots").status_code == 200


def test_administracion_en_el_servidor():
    repo = Repository(":memory:")
    client = TestClient(create_app(repo, dev_mode=False))
    creds = {"username": "sara", "password": "contraseña-segura"}
    client.post("/api/auth/register", json=creds)
    assert client.get("/api/admin/overview").status_code == 403
    repo.set_role(repo.authenticate(**creds).id, "admin")
    assert client.get("/api/me").json()["role"] == "admin"
    r = client.post("/api/admin/users", json={"username": "ana", "password": "contraseña-2"})
    assert r.status_code == 200
    uid = r.json()["id"]
    assert client.put(f"/api/admin/users/{uid}", json={"role": "admin"}).status_code == 200
    assert client.put(f"/api/admin/users/{uid}", json={"role": "jefe"}).status_code == 422
    assert {u["username"] for u in client.get("/api/admin/overview").json()["users"]} == {
        "sara",
        "ana",
    }
    assert client.delete(f"/api/admin/users/{uid}").status_code == 200
