"""Backend del navegador (Pyodide): mismo flujo que la API, sin servidor."""

import json

import pytest

from musst.web.backend import LocalBackend, handle_json


def play_until_end(b, game_id, token, obs, limit=600):
    for _ in range(limit):
        if obs["finished"]:
            return obs
        if obs.get("awaiting_deal"):
            status, obs = b.handle("POST", f"/api/games/{game_id}/deal", None, token)
            assert status == 200, obs
            continue
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
        status, obs = b.handle("POST", f"/api/games/{game_id}/action", {"action": action}, token)
        assert status == 200, obs
    raise AssertionError("la partida no terminó")


@pytest.fixture
def backend(tmp_path):
    return LocalBackend(tmp_path)


def test_partida_completa_con_perfil_y_estadisticas(backend):
    assert backend.handle("GET", "/api/me", None, None) == (200, None)
    status, _ = backend.handle(
        "POST", "/api/auth/register", {"username": "sara", "password": "contraseña-1"}, None
    )
    assert status == 200
    status, data = backend.handle(
        "POST",
        "/api/games",
        {"mode": "rapida", "rivals": "sencillo", "target": 10, "seed": 3},
        None,
    )
    assert status == 200
    obs = data["observation"]
    assert obs["awaiting_deal"] and obs["hand"] == []  # «¿Repartimos?» antes de ver las cartas
    status, obs = backend.handle(
        "POST", f"/api/games/{data['game_id']}/deal", None, data["seat_token"]
    )
    assert len(obs["hand"]) == 4
    assert "hands" not in obs and "deck" not in obs
    end = play_until_end(backend, data["game_id"], data["seat_token"], obs)
    assert end["finished"]
    status, stats = backend.handle("GET", "/api/players/me/statistics", None, None)
    assert status == 200 and stats["partidas"] == 1
    status, games = backend.handle("GET", "/api/history", None, None)
    assert [g["id"] for g in games] == [data["game_id"]]
    status, replay = backend.handle("GET", f"/api/games/{data['game_id']}/replay", None, None)
    assert status == 200 and replay["history"]


def test_token_ajeno_rechazado_y_accion_ilegal(backend):
    _, data = backend.handle("POST", "/api/games", {"seed": 1}, None)
    gid, token = data["game_id"], data["seat_token"]
    assert backend.handle("GET", f"/api/games/{gid}", None, "otro")[0] == 403
    status, err = backend.handle(
        "POST", f"/api/games/{gid}/action", {"action": {"type": "ordago"}}, token
    )
    assert status == 422 and "no válida" in err["detail"]


def test_sin_invitaciones_ni_bots_externos(backend):
    status, _ = backend.handle("POST", "/api/games", {"partner": "human"}, None)
    assert status == 422
    _, bots = backend.handle("GET", "/api/bots", None, None)
    assert bots and not any(b["external"] for b in bots)
    assert backend.handle("POST", "/api/games/x/join", {}, None)[0] == 422


def test_la_partida_sobrevive_a_recargar_la_pagina(tmp_path):
    first = LocalBackend(tmp_path)
    first.handle(
        "POST", "/api/auth/register", {"username": "sara", "password": "contraseña-1"}, None
    )
    _, data = first.handle("POST", "/api/games", {"seed": 5}, None)
    gid, token = data["game_id"], data["seat_token"]
    reloaded = LocalBackend(tmp_path)  # nuevo intérprete, misma base de datos en IndexedDB
    assert reloaded.user is not None and reloaded.user.username == "sara"
    status, obs = reloaded.handle("GET", f"/api/games/{gid}", None, token)
    assert status == 200
    assert obs["awaiting_deal"]
    status, obs = reloaded.handle("POST", f"/api/games/{gid}/deal", None, token)
    first.handle("POST", f"/api/games/{gid}/deal", None, token)
    assert obs["hand"] == first.handle("GET", f"/api/games/{gid}", None, token)[1]["hand"]


def test_perfil_local_no_permite_login_con_contrasena(backend):
    backend.handle("POST", "/api/auth/login", {"username": "viejo", "cloud": True}, None)
    assert backend.repo.authenticate("viejo", "!local") is None


def reg(b, name, pw="contraseña-1"):
    return b.handle("POST", "/api/auth/register", {"username": name, "password": pw}, None)


def test_cuentas_con_contrasena_y_primer_usuario_administrador(tmp_path):
    b = LocalBackend(tmp_path)
    status, first = reg(b, "sara")
    assert status == 200 and first["role"] == "admin"
    assert "contraseña-1" not in (tmp_path / "musst.sqlite3").read_bytes().decode("latin-1")
    b.handle("POST", "/api/auth/logout", None, None)
    status, second = reg(b, "ana")
    assert second["role"] == "player"
    assert reg(b, "ana")[0] == 409
    assert reg(b, "x")[0] == 422 and reg(b, "luis", "corta")[0] == 422
    b.handle("POST", "/api/auth/logout", None, None)
    assert (
        b.handle("POST", "/api/auth/login", {"username": "ana", "password": "mala-clave"}, None)[0]
        == 401
    )
    assert (
        b.handle("POST", "/api/auth/login", {"username": "ana", "password": "contraseña-1"}, None)[
            0
        ]
        == 200
    )
    assert b.handle("GET", "/api/me", None, None)[1]["username"] == "ana"
    # al recargar la página sigue la sesión
    assert LocalBackend(tmp_path).handle("GET", "/api/me", None, None)[1]["username"] == "ana"


def test_un_perfil_antiguo_sin_contrasena_puede_ponerse_una(backend):
    backend.handle("POST", "/api/auth/login", {"username": "vieja", "cloud": True}, None)
    backend.handle("POST", "/api/auth/logout", None, None)
    assert reg(backend, "vieja")[0] == 200
    assert backend.repo.authenticate("vieja", "contraseña-1") is not None


def test_panel_de_administracion(tmp_path):
    b = LocalBackend(tmp_path)
    reg(b, "sara")  # administradora
    _, data = b.handle(
        "POST", "/api/games", {"seed": 2, "target": 10, "rivals": "profesional"}, None
    )
    play_until_end(b, data["game_id"], data["seat_token"], data["observation"])
    status, created = b.handle(
        "POST", "/api/admin/users", {"username": "ana", "password": "contraseña-2"}, None
    )
    assert status == 200 and created["role"] == "player"
    uid = created["id"]
    assert (
        b.handle("POST", "/api/admin/users", {"username": "ana", "password": "contraseña-2"}, None)[
            0
        ]
        == 409
    )
    assert (
        b.handle("PUT", f"/api/admin/users/{uid}", {"username": "anabel", "role": "admin"}, None)[0]
        == 200
    )
    assert b.handle("PUT", f"/api/admin/users/{uid}", {"password": "nueva-clave-1"}, None)[0] == 200
    assert b.repo.authenticate("anabel", "nueva-clave-1").role == "admin"
    me = b.user.id
    assert b.handle("PUT", f"/api/admin/users/{me}", {"role": "player"}, None)[0] == 422
    assert b.handle("DELETE", f"/api/admin/users/{me}", None, None)[0] == 422
    status, overview = b.handle("GET", "/api/admin/overview", None, None)
    assert status == 200
    assert {u["username"] for u in overview["users"]} == {"sara", "anabel"}
    assert next(u for u in overview["users"] if u["username"] == "sara")["last_seen"]
    assert len(overview["games"]) == 1 and overview["games"][0]["rivals"] == "profesional"
    assert overview["models"] and overview["models"][0]["style"]
    assert overview["memory"] and overview["memory"][0]["key"] == "self:profesional"
    json.dumps(overview)
    assert b.handle("DELETE", f"/api/admin/users/{uid}", None, None)[0] == 200
    assert b.repo.get_user(uid) is None
    # un jugador normal no puede usar el panel
    b.handle("POST", "/api/auth/logout", None, None)
    reg(b, "luis")
    assert b.handle("GET", "/api/admin/overview", None, None)[0] == 403
    assert b.handle("DELETE", f"/api/admin/users/{me}", None, None)[0] == 403


def test_handle_json_y_errores():
    out = json.loads(handle_json("GET", "/api/nada", None, None))
    assert out["status"] == 404
    out = json.loads(
        handle_json(
            "POST",
            "/api/arena/watch",
            json.dumps({"team_a": "random", "team_b": "sencillo", "seed": 2}),
            None,
        )
    )
    assert out["status"] == 200 and out["data"]["winner"] in (0, 1)


def test_sincronizacion_con_la_nube(tmp_path):
    b = LocalBackend(tmp_path)
    b.handle("POST", "/api/auth/register", {"username": "sara", "password": "contraseña-1"}, None)
    _, data = b.handle(
        "POST", "/api/games", {"seed": 4, "target": 10, "rivals": "profesional"}, None
    )
    play_until_end(b, data["game_id"], data["seat_token"], data["observation"])
    status, out = b.handle("GET", f"/api/cloud/export/{data['game_id']}", None, None)
    assert status == 200, out
    assert out["game"]["id"] == data["game_id"] and isinstance(out["game"]["won"], bool)
    assert out["model"]["games"] == 1 and out["style"]
    assert "self:profesional" in out["bot_memory"]
    json.dumps(out)  # se puede enviar tal cual a Supabase

    # Otro navegador: al iniciar sesión recibe lo aprendido
    other = LocalBackend(tmp_path / "otro" if (tmp_path / "otro").mkdir() is None else None)
    other.handle("POST", "/api/auth/login", {"username": "sara", "cloud": True}, None)
    status, res = other.handle(
        "POST", "/api/cloud/import", {"model": out["model"], "bot_memory": out["bot_memory"]}, None
    )
    assert status == 200 and len(res["imported"]) == 2
    uid = other.user.id
    assert other.service.manager.learner.long_model(f"user:{uid}").games == 1
    assert other.repo.load_model("self:profesional")["extra"]["self_review"]["games"] >= 1
    assert other.handle("POST", "/api/cloud/import", {"bot_memory": {"hack": {}}}, None)[1] == {
        "imported": []
    }
