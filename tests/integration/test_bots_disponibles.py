"""Todos los bots aceptados se pueden elegir para jugar y entran (una vez) en el ranking."""

import zipfile
from pathlib import Path

from musst.bots import registry
from musst.web.backend import LocalBackend

ROOT = Path(__file__).resolve().parents[2]


def test_la_portada_ofrece_todos_los_bots_del_repo(tmp_path: Path):
    _, bots = LocalBackend(tmp_path).handle("GET", "/api/bots", None, None)
    names = {b["name"] for b in bots}
    aceptados = {p.parent.name for p in (ROOT / "bots").glob("*/bot.toml")}
    assert aceptados <= names  # car_lu, compi, mi_bot, ejemplo…
    assert {"sencillo", "medio", "experto", "basico"} <= names
    assert [b["name"] for b in bots if b["alias"]] == ["profesional"]


def test_el_ranking_no_repite_alias():
    entries = [e for e in registry.all_entries(sandboxed=True) if not e.alias]
    names = [e.name for e in entries]
    assert len(names) == len(set(names))
    assert "experto" in names and "profesional" not in names


def test_la_web_empaqueta_los_bots_aceptados(tmp_path: Path):
    import subprocess
    import sys

    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_web.py"), "--out", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    with zipfile.ZipFile(tmp_path / "static" / "musst.zip") as zf:
        files = set(zf.namelist())
    for bot in (ROOT / "bots").glob("*/bot.toml"):
        assert f"musst_bots/{bot.parent.name}/bot.toml" in files
    assert any(f.endswith("inteligente.npz") for f in files)


def test_bots_externos_sin_subproceso(tmp_path: Path, monkeypatch):
    # Como en el navegador: sin la carpeta bots/ del repo, desde musst_bots/ y en el mismo proceso.
    bundled = tmp_path / "musst_bots"
    bundled.mkdir()
    for f in (ROOT / "bots" / "ejemplo").glob("*"):
        if f.suffix in (".py", ".toml"):
            (bundled / "ejemplo").mkdir(exist_ok=True)
            (bundled / "ejemplo" / f.name).write_text(f.read_text())
    monkeypatch.setattr(registry, "REPO_BOTS_DIR", tmp_path / "no-existe")
    monkeypatch.setattr(registry, "BUNDLED_BOTS_DIR", bundled)
    monkeypatch.setattr(registry, "SANDBOX_DEFAULT", False)
    entry = next(e for e in registry.all_entries() if e.name == "ejemplo")
    assert type(entry.factory()).__name__ == "EjemploBot"
