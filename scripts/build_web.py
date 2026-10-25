"""Genera la versión estática de MUS.ST para GitHub Pages (Python en el navegador con Pyodide).

    python scripts/build_web.py --out site

Resultado::

    site/index.html          frontend con <meta name="musst-backend" content="pyodide">
    site/static/             CSS, JS y worker.js
    site/static/musst.zip    el paquete ``musst`` (el mismo código que el servidor)

Probar en local: ``python -m http.server -d site 8000`` y abrir http://localhost:8000.
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "musst"
STATIC = PKG / "server" / "static"

BOOT_SCREEN = """  <div id="booting" class="booting" role="status">
    <span class="brand-mark" aria-hidden="true">M</span>
    <p>Cargando el motor…</p>
    <small>La primera vez descarga Python (unos 10 MB); después queda en caché.</small>
  </div>
"""


def build(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out / "static", ignore_errors=True)
    (out / "static").mkdir(parents=True, exist_ok=True)
    for f in STATIC.iterdir():
        if f.is_file() and f.name != "index.html":
            shutil.copy2(f, out / "static" / f.name)
    shutil.copy2(PKG / "web" / "worker.js", out / "static" / "worker.js")

    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = html.replace(
        '<meta charset="utf-8">',
        '<meta charset="utf-8">\n  <meta name="musst-backend" content="pyodide">',
        1,
    )
    html = html.replace("<body>\n", "<body>\n" + BOOT_SCREEN, 1)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / ".nojekyll").write_text("")

    with zipfile.ZipFile(out / "static" / "musst.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PKG.rglob("*")):
            rel = path.relative_to(PKG.parent)
            if path.is_dir() or "__pycache__" in rel.parts or "static" in rel.parts:
                continue
            if path.suffix in (".py", ".toml", ".typed"):
                zf.write(path, rel.as_posix())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    build(args.out)
    print(f"Web estática generada en {args.out}")


if __name__ == "__main__":
    main()
