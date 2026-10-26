// MUS.ST — Web Worker que ejecuta el motor de Python en el navegador con Pyodide.
// Recibe peticiones {id, method, path, body, token} y responde {id, status, data}.
// Corre fuera del hilo principal para que la mesa no se congele mientras piensan los bots.

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
importScripts(`${PYODIDE}pyodide.js`);

const progress = (text) => postMessage({ type: "progress", text });

async function boot() {
  progress("Cargando Python…");
  const pyodide = await loadPyodide({ indexURL: PYODIDE });
  progress("Cargando base de datos…");
  await pyodide.loadPackage(["sqlite3", "hashlib"]); // hashlib: scrypt para las contraseñas
  progress("Cargando el motor de Mus…");
  const zip = await fetch(new URL("musst.zip", self.location.href));
  if (!zip.ok) throw new Error(`musst.zip: HTTP ${zip.status}`);
  pyodide.unpackArchive(await zip.arrayBuffer(), "zip", { extractDir: "/home/pyodide/lib" });
  // Datos persistentes: SQLite sobre IndexedDB (solo en este navegador).
  const FS = pyodide.FS;
  try {
    FS.mkdir("/data");
    FS.mount(pyodide.FS.filesystems.IDBFS, {}, "/data");
    await new Promise((ok, ko) => FS.syncfs(true, (err) => (err ? ko(err) : ok())));
  } catch (err) {
    progress("Sin almacenamiento persistente: los datos se perderán al cerrar");
  }
  pyodide.runPython(`
import sys
sys.path.insert(0, "/home/pyodide/lib")
from musst.web.backend import handle_json
`);
  return { pyodide, handle: pyodide.globals.get("handle_json"), FS };
}

const ready = boot();
ready.then(() => postMessage({ type: "ready" }), (err) => postMessage({ type: "fatal", text: String(err) }));

let saving = Promise.resolve();
function persist(FS) {
  saving = saving.then(() => new Promise((ok) => FS.syncfs(false, () => ok())));
  return saving;
}

// Las peticiones se atienden de una en una (el motor no es reentrante).
let queue = Promise.resolve();
self.onmessage = ({ data }) => {
  queue = queue.then(async () => {
    const { id, method, path, body, token } = data;
    try {
      if (path === "/api/scoreboard") {
        const res = await fetch(new URL("../scoreboard/scoreboard.json", self.location.href));
        const board = res.ok ? await res.json() : { ranking: [], note: "Aún no se ha ejecutado el torneo" };
        postMessage({ id, status: 200, data: board });
        return;
      }
      const { handle, FS } = await ready;
      const out = JSON.parse(handle(method, path, body, token));
      if (method !== "GET") await persist(FS);
      postMessage({ id, ...out });
    } catch (err) {
      postMessage({ id, status: 500, data: { detail: `Error interno: ${err.message || err}` } });
    }
  });
};
