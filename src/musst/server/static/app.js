// MUS.ST — frontend sin dependencias. Solo renderiza observaciones y envía intenciones.
// La legalidad la decide siempre el motor (RulesEngine); aquí solo se ocultan botones.
// Dos backends con la misma API: el servidor FastAPI o, en GitHub Pages, el mismo Python
// ejecutándose en este navegador con Pyodide (worker.js). Lo decide <meta name="musst-backend">.

import * as cloud from "./cloud.js";

const $main = document.getElementById("main");
const $live = document.getElementById("live");
const $modal = document.getElementById("modal");
const $modalBody = document.getElementById("modal-body");

// ------------------------------------------------------------------ ajustes
const DEFAULT_SETTINGS = {
  theme: "auto", text_size: 1, reduce_motion: false, sound: true, voice: true, speed: 1, table: "verde", card_back: "rayas",
};
const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* sin almacenamiento */ } },
};
let settings = { ...DEFAULT_SETTINGS, ...store.get("musst.settings", {}) };
let user = null;
let current = null; // partida en curso

function applySettings() {
  const root = document.documentElement;
  if (settings.theme === "auto") root.removeAttribute("data-theme"); else root.dataset.theme = settings.theme;
  root.dataset.motion = settings.reduce_motion ? "reduce" : "normal";
  root.dataset.table = settings.table;
  root.dataset.back = settings.card_back;
  root.style.setProperty("--text-scale", settings.text_size);
  root.style.setProperty("--speed", settings.speed);
  const mute = document.getElementById("mute");
  mute.textContent = settings.sound ? "🔊" : "🔇";
  mute.setAttribute("aria-pressed", String(!settings.sound));
}
function saveSettings() {
  store.set("musst.settings", settings);
  applySettings();
  if (user) api("/api/me", { method: "PUT", body: { avatar: user.avatar, settings } }).catch(() => {});
}

// ------------------------------------------------------------------ sonido (WebAudio, sin ficheros)
let audio;
const SOUNDS = {
  deal: [[520, 0.04], [620, 0.04]], cut: [[300, 0.08]], bet: [[440, 0.09], [660, 0.09]],
  accept: [[523, 0.08], [784, 0.12]], reject: [[330, 0.12]], points: [[880, 0.06], [988, 0.06]],
  ordago: [[220, 0.12], [330, 0.12], [440, 0.2]], end: [[523, 0.12], [659, 0.12], [784, 0.24]],
};
function play(name) {
  if (!settings.sound || !SOUNDS[name]) return;
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    let t = audio.currentTime;
    for (const [freq, dur] of SOUNDS[name]) {
      const osc = audio.createOscillator(); const gain = audio.createGain();
      osc.frequency.value = freq; osc.type = "triangle";
      gain.gain.setValueAtTime(0.06, t); gain.gain.exponentialRampToValueAtTime(0.001, t + dur);
      osc.connect(gain).connect(audio.destination); osc.start(t); osc.stop(t + dur); t += dur;
    }
  } catch { /* sin audio */ }
}

// ------------------------------------------------------------------ utilidades
const LOCAL = document.querySelector('meta[name="musst-backend"]')?.content === "pyodide";
let worker = null;
let workerReady = null;
const pending = new Map();
function startWorker() {
  if (workerReady) return workerReady;
  worker = new Worker(new URL("worker.js", import.meta.url));
  const $boot = document.getElementById("booting");
  workerReady = new Promise((resolve, reject) => {
    worker.onmessage = ({ data }) => {
      if (data.type === "progress") { if ($boot) $boot.querySelector("p").textContent = data.text; return; }
      if (data.type === "ready") { $boot?.remove(); resolve(); return; }
      if (data.type === "fatal") {
        if ($boot) $boot.querySelector("p").textContent = `No se pudo cargar el motor: ${data.text}`;
        reject(new Error(data.text));
        return;
      }
      const p = pending.get(data.id);
      if (p) { pending.delete(data.id); p(data); }
    };
  });
  return workerReady;
}
let nextId = 0;
async function localApi(path, method, body, token) {
  await startWorker();
  const id = ++nextId;
  const reply = await new Promise((resolve) => {
    pending.set(id, resolve);
    worker.postMessage({ id, method, path, body: body ? JSON.stringify(body) : null, token: token || null });
  });
  if (reply.status >= 400) throw new Error(typeof reply.data?.detail === "string" ? reply.data.detail : "Error del motor");
  return reply.data;
}

async function api(path, { method = "GET", body, token } = {}) {
  if (LOCAL) return localApi(path, method, body, token);
  const headers = { "Content-Type": "application/json" };
  if (token) headers["X-Seat-Token"] = token;
  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined, credentials: "same-origin" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Error del servidor");
  return data;
}
const fmtOutcome = (c, v) => (c.ordago && Math.abs(v) === c.envite ? (v > 0 ? "ganas la partida" : "pierdes la partida") : `${v > 0 ? "+" : ""}${v} tantos`);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms * (settings.reduce_motion ? 0.2 : settings.speed)));
const announce = (msg) => { $live.textContent = msg; };
function toast(msg) {
  const el = document.createElement("div"); el.className = "toast"; el.role = "status"; el.textContent = msg;
  document.body.append(el); setTimeout(() => el.remove(), 2600);
}
function openModal(html) { $modalBody.innerHTML = html; $modal.showModal(); }
$modal.addEventListener("click", (e) => { if (e.target === $modal || e.target.dataset.close !== undefined) $modal.close(); });

// ------------------------------------------------------------------ naipes
const SUITS = { O: "Oros", C: "Copas", E: "Espadas", B: "Bastos" };
const RANK_LABEL = { 1: "A", 10: "S", 11: "C", 12: "R" };
const SUIT_SVG = {
  // Oros: moneda de oro labrada
  O: '<svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="13" fill="#e8b830" stroke="#8a5e0b" stroke-width="1.6"/><circle cx="16" cy="16" r="9.5" fill="#f4cf5a" stroke="#a87410" stroke-width="1.1"/><path d="M16 9.5l1.8 4.7 4.7 1.8-4.7 1.8L16 22.5l-1.8-4.7-4.7-1.8 4.7-1.8z" fill="#c4392f"/><circle cx="16" cy="16" r="1.6" fill="#8a5e0b"/></svg>',
  // Copas: cáliz rojo con borde dorado
  C: '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M7 4h18c0 7-3 11.5-9 11.5S7 11 7 4z" fill="#c8313f" stroke="#6e1520" stroke-width="1.4"/><path d="M7 4h18" stroke="#e8b830" stroke-width="2.4"/><path d="M14 15.5h4l-.8 6h-2.4z" fill="#e8b830" stroke="#8a5e0b" stroke-width=".9"/><ellipse cx="16" cy="24" rx="5.5" ry="2.2" fill="#e8b830" stroke="#8a5e0b" stroke-width=".9"/><path d="M10 27.5h12" stroke="#8a5e0b" stroke-width="2.2" stroke-linecap="round"/></svg>',
  // Espadas: hoja azul, guarda y pomo dorados
  E: '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 1.5l2.6 4V21h-5.2V5.5z" fill="#6c95c6" stroke="#1f3b5e" stroke-width="1.2"/><path d="M16 4v16" stroke="#e7f0fb" stroke-width=".9"/><path d="M8 21.5h16" stroke="#c9961e" stroke-width="2.8" stroke-linecap="round"/><path d="M16 22.5v6" stroke="#5b3a1c" stroke-width="2.8"/><circle cx="16" cy="29.5" r="1.9" fill="#c9961e"/></svg>',
  // Bastos: garrote verde con nudos
  B: '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M12 30.5l1.6-25c.4-4 6.4-4 6.8 0L18 30.5z" fill="#6a9a3e" stroke="#2d4719" stroke-width="1.3"/><path d="M14.3 9.5c1.4.8 2.5.8 3.8 0M14.1 15c1.4.8 2.6.8 3.9 0M13.8 21c1.5.8 2.8.8 4.2 0" stroke="#2d4719" stroke-width="1.1" fill="none"/><path d="M19.6 7l3-2.2M12.6 12.5L9.5 11" stroke="#2d4719" stroke-width="1.4" stroke-linecap="round"/><ellipse cx="22.9" cy="4.6" rx="1.6" ry="1" fill="#4f7d2c"/><ellipse cx="9.2" cy="10.8" rx="1.6" ry="1" fill="#4f7d2c"/></svg>',
};
function parseCard(code) { return { rank: Number(code.slice(0, -1)), suit: code.slice(-1) }; }
function cardLabel(code) {
  const { rank, suit } = parseCard(code);
  const names = { 1: "As", 2: "Dos", 3: "Tres", 4: "Cuatro", 5: "Cinco", 6: "Seis", 7: "Siete", 10: "Sota", 11: "Caballo", 12: "Rey" };
  const extra = rank === 3 ? " (cuenta como rey)" : rank === 2 ? " (cuenta como as)" : "";
  return `${names[rank]} de ${SUITS[suit].toLowerCase()}${extra}`;
}
// Naipe español dibujado en SVG: índice grande en las esquinas, pintas en el marco (huecos
// según el palo, como en la baraja española) y figuras reconocibles.
const PINTAS = { O: 0, C: 1, E: 2, B: 3 };
const SUIT_COLOR = { O: "#b8860b", C: "#b8323f", E: "#2f5d8a", B: "#3f6b2a" };
const PIP_LAYOUT = {
  1: [[30, 46, 2.2]], 2: [[30, 28], [30, 64]], 3: [[30, 24], [30, 46], [30, 68]],
  4: [[21, 28], [39, 28], [21, 64], [39, 64]], 5: [[21, 26], [39, 26], [30, 46], [21, 66], [39, 66]],
  6: [[21, 24], [39, 24], [21, 46], [39, 46], [21, 68], [39, 68]],
  7: [[21, 22], [39, 22], [30, 35], [21, 48], [39, 48], [21, 70], [39, 70]],
};
const FIGURE = { 10: "SOTA", 11: "CABALLO", 12: "REY" };
function suitUse(suit, x, y, scale = 1) {
  const s = 11 * scale;
  return `<svg x="${x - s / 2}" y="${y - s / 2}" width="${s}" height="${s}" viewBox="0 0 32 32">${SUIT_SVG[suit].replace(/^<svg[^>]*>|<\/svg>$/g, "")}</svg>`;
}
// Figuras de cuerpo entero, como en la baraja española: sota (paje de pie), caballo (jinete)
// y rey (corona, barba y manto). Cada palo tiñe la ropa.
const ROBE = { O: ["#c8862a", "#7a3f12"], C: ["#b8323f", "#5e1018"], E: ["#3d6ea5", "#1d3553"], B: ["#5f8a3a", "#2c4318"] };
function figureSVG(rank, suit) {
  const [robe, dark] = ROBE[suit];
  const skin = "#f1d0ae";
  const frame = `<rect x="14" y="11" width="32" height="68" rx="3" fill="#fbf3df" stroke="${dark}" stroke-width="1"/>`;
  if (rank === 11) {
    // Caballo: jinete sobre caballo, sosteniendo el palo
    return `${frame}
      <path d="M14 66q2-14 14-16 10-2 16 4l4 6-3 2-3-3v13h-4v-9h-12v9h-4z" fill="#9a6a3a" stroke="#4a2f14" stroke-width=".9"/>
      <path d="M41 52q4-6 1-12l-4 2q2 5-1 9z" fill="#9a6a3a" stroke="#4a2f14" stroke-width=".9"/>
      <circle cx="42.5" cy="45.5" r=".9" fill="#1d1612"/>
      <path d="M23 50l3-14h10l2 14z" fill="${robe}" stroke="${dark}" stroke-width=".9"/>
      <circle cx="31" cy="31" r="4.6" fill="${skin}" stroke="#7a5a3a" stroke-width=".6"/>
      <path d="M26.5 29q4.5-6 9 0z" fill="${dark}"/>
      ${suitUse(suit, 20, 38, 1.05)}`;
  }
  const crown = rank === 12 ? `<path d="M23.5 23l2.5-4.5 2.5 3 2.5-4.5 2.5 4.5 2.5-3 2.5 4.5z" fill="#e8b830" stroke="#8a5e0b" stroke-width=".7"/>` : `<path d="M24 25q6-7 12 0z" fill="${dark}"/><circle cx="36" cy="22" r="1.4" fill="#e8b830"/>`;
  const beard = rank === 12 ? `<path d="M26.5 30q3.5 7 7 0z" fill="#8c8478"/>` : "";
  const cape = rank === 12 ? `<path d="M19 72l4-34h14l4 34z" fill="${dark}" opacity=".9"/>` : "";
  return `${frame}${cape}
    <path d="M22 72l3-34h10l3 34z" fill="${robe}" stroke="${dark}" stroke-width=".9"/>
    <path d="M25 46h10" stroke="#e8b830" stroke-width="1.6"/>
    <path d="M26 72v4M34 72v4" stroke="#3a2a1a" stroke-width="2.4"/>
    <circle cx="30" cy="30" r="5.2" fill="${skin}" stroke="#7a5a3a" stroke-width=".6"/>
    <circle cx="28.2" cy="29.5" r=".7" fill="#1d1612"/><circle cx="31.8" cy="29.5" r=".7" fill="#1d1612"/>
    ${crown}${beard}
    <path d="M35 44l7-2" stroke="${skin}" stroke-width="2.2" stroke-linecap="round"/>
    ${suitUse(suit, 43, 40, 1.1)}`;
}
function cardFace(code) {
  const { rank, suit } = parseCard(code);
  const c = SUIT_COLOR[suit];
  const gaps = PINTAS[suit];
  const frame = gaps === 0 ? `<rect x="3" y="3" width="54" height="84" rx="4" fill="none" stroke="${c}" stroke-width="1.4"/>`
    : `<path d="${[...Array(gaps + 1)].map((_, i) => `M${4 + i * (52 / (gaps + 1)) + (i ? 3 : 0)} 3h${52 / (gaps + 1) - 3}`).join("")}" stroke="${c}" stroke-width="1.4"/>
       <path d="${[...Array(gaps + 1)].map((_, i) => `M${4 + i * (52 / (gaps + 1)) + (i ? 3 : 0)} 87h${52 / (gaps + 1) - 3}`).join("")}" stroke="${c}" stroke-width="1.4"/>
       <path d="M3 6v78M57 6v78" stroke="${c}" stroke-width="1.4"/>`;
  const pip = rank <= 3 ? 1.7 : rank <= 5 ? 1.45 : 1.25;
  const body = FIGURE[rank] ? figureSVG(rank, suit) : PIP_LAYOUT[rank].map(([x, y, k]) => suitUse(suit, x, y, k ? k * 1.4 : pip)).join("");
  const idx = `<text x="6.5" y="14" font-family="Georgia,serif" font-weight="700" font-size="12.5" fill="${c}">${rank}</text>${suitUse(suit, 10.5, 19.5, 0.62)}`;
  const idx2 = `<g transform="rotate(180 30 45)">${idx}</g>`;
  const fig = FIGURE[rank] ? `<text x="30" y="85" font-size="5.5" text-anchor="middle" fill="#5d625b" letter-spacing=".5">${FIGURE[rank]}</text>` : "";
  return `<svg class="face" viewBox="0 0 60 90" aria-hidden="true"><rect width="60" height="90" rx="5" fill="#fffdf6"/>${frame}${body}${idx}${idx2}${fig}</svg>`;
}
function cardHTML(code, { small = false, button = false, pressed = false } = {}) {
  const { rank } = parseCard(code);
  const tag = button ? "button" : "div";
  const equiv = rank === 3 ? '<span class="equiv">=R</span>' : rank === 2 ? '<span class="equiv">=A</span>' : "";
  const attrs = button ? ` type="button" data-card="${code}" aria-pressed="${pressed}"` : ' role="img"';
  return `<${tag} class="card${small ? " small" : ""}"${attrs} aria-label="${cardLabel(code)}">${cardFace(code)}${equiv}</${tag}>`;
}

// ------------------------------------------------------------------ textos de eventos
const LANCE = { grande: "Grande", chica: "Chica", pares: "Pares", juego: "Juego", punto: "Punto", mus: "Mus" };
function eventText(e, names) {
  const who = e.actor != null ? names[e.actor] ?? `Asiento ${e.actor}` : "";
  const p = e.payload || {};
  switch (e.kind) {
    case "DealerAssigned": return `Jugada ${e.round}: reparte ${names[p.dealer]}, es mano ${names[p.mano]}`;
    case "MusRequested": return `${who}: «Mus»`;
    case "MusCut": return `${who}: «No hay mus»`;
    case "CardsDiscarded": return p.count != null ? `${who} se descarta de ${p.count}` : null;
    case "DeckReshuffled": return "Se baraja el descarte";
    case "LanceStarted": return `— ${LANCE[p.lance]} —`;
    case "PairsDeclared": return `${who}: pares ${p.has ? "sí" : "no"}`;
    case "GameDeclared": return `${who}: juego ${p.has ? "sí" : "no"}`;
    case "Passed": return `${who}: «Paso»`;
    case "BetPlaced": return `${who}: «Envido ${p.amount}» a ${LANCE[p.lance]}`;
    case "BetRaised": return `${who}: «${p.amount} más» (total ${p.total})`;
    case "OrdagoDeclared": return `${who}: «¡Órdago!» a ${LANCE[p.lance]}`;
    case "BetAccepted": return `${who}: «Quiero»`;
    case "OrdagoAccepted": return `${who}: «Quiero» al órdago${p.no_lose ? " (y no pierdo)" : ""}`;
    case "BetRejected": return `${who}: «No quiero»`;
    case "HandsRevealed": return "Se enseñan las cartas";
    case "LanceResolved": return p.winner_seat != null ? `${LANCE[p.lance]}: gana ${names[p.winner_seat]}` : null;
    case "PointsAwarded": return `+${p.points} pareja ${p.team === 0 ? "A" : "B"} (${p.concept}, ${LANCE[p.lance] ?? p.lance})`;
    case "TeamIsIn": return `Pareja ${p.team === 0 ? "A" : "B"}: «¡Estamos dentro!»`;
    case "RoundFinished": return `Fin de la jugada: ${p.score[0]} – ${p.score[1]}`;
    case "GameFinished": return `Fin de la partida: gana la pareja ${p.winner === 0 ? "A" : "B"}`;
    default: return null;
  }
}
const BUBBLE = {
  MusRequested: "MUS", MusCut: "CORTO", Passed: "PASO", BetPlaced: "ENVIDO", BetRaised: "REENVÍO",
  BetAccepted: "QUIERO", OrdagoAccepted: "QUIERO", BetRejected: "NO QUIERO", OrdagoDeclared: "ÓRDAGO",
  PairsDeclared: "PARES", GameDeclared: "JUEGO",
};
// Lo que dicen los bots en la mesa (varía para que no suene a máquina).
const TALK = {
  MusRequested: ["Mus", "Mus, que estas no valen", "Dame mus"],
  MusCut: ["No hay mus", "Corto", "Aquí no hay mus"],
  Passed: ["Paso", "Paso", "Paso, a ver qué decís"],
  BetPlaced: (p) => (p.amount === 2 ? ["Envido", "Dos a " + LANCE[p.lance].toLowerCase(), "Envido, ¿qué hacéis?"] : [`Envido ${p.amount}`, `${p.amount} a ${LANCE[p.lance].toLowerCase()}`]),
  BetRaised: (p) => [`${p.amount} más`, `Subo ${p.amount}`, `Y ${p.amount} más`],
  OrdagoDeclared: () => ["¡ÓRDAGO!", "¡Órdago a " + "la mesa!"],
  BetAccepted: ["Quiero", "Lo quiero", "Venga, quiero"],
  OrdagoAccepted: ["¡Quiero!", "¡Lo veo!"],
  BetRejected: ["No quiero", "Para vosotros", "No, no quiero"],
  PairsDeclared: (p) => [p.has ? "Pares sí" : "Pares no"],
  GameDeclared: (p) => [p.has ? "Juego sí" : "Juego no"],
};
function talk(e) {
  const t = TALK[e.kind];
  const opts = typeof t === "function" ? t(e.payload || {}) : t;
  if (!opts) return BUBBLE[e.kind];
  return opts[(e.seq * 7 + (e.actor ?? 0)) % opts.length];
}
const BANTER_WIN = ["¡Esa era nuestra!", "Buena jugada, compañero", "Así se juega"];
const BANTER_LOSE = ["La próxima es nuestra", "Qué cartas más malas…", "Uf, no hubo suerte"];

// Señas oficiales (FEM VIII.2): gesto y significado.
const SIGNAL_ICON = {
  dos_reyes: "😬", dos_ases: "😛", pares: "↪️", medias_reyes: "😏", medias_ases: "😜", medias: "😏",
  duples: "🤨", juego: "😗", treinta_y_una: "😉", treinta: "🤷", veintinueve: "🤷‍♂️", ciego: "😑",
};
const SIGNALS = {
  dos_reyes: ["Morderse el labio inferior", "dos reyes"], dos_ases: ["Sacar la lengua de frente", "dos ases"],
  pares: ["Girar la cabeza a un lado", "pares"], medias_reyes: ["Labios cerrados hacia un lado", "medias de reyes"],
  medias_ases: ["Sacar la lengua hacia un lado", "medias de ases"], medias: ["Labios cerrados hacia un lado", "medias"],
  duples: ["Levantar las cejas", "duples"], juego: ["Labios cerrados hacia afuera", "juego"],
  treinta_y_una: ["Guiñar un ojo", "la 31"], treinta: ["Alzar los dos hombros", "30 de punto"],
  veintinueve: ["Alzar un hombro", "29 de punto"], ciego: ["Cerrar los dos ojos", "ciego (nada)"],
};

// Cartas ordenadas como se cogen en la mano: de mayor (izquierda) a menor (derecha).
const GRANDE_ORDER = (code) => { const r = parseCard(code).rank; return r === 3 ? 12 : r === 2 ? 1 : r; };
const sortHand = (codes) => [...codes].sort((a, b) => GRANDE_ORDER(b) - GRANDE_ORDER(a) || parseCard(a).suit.localeCompare(parseCard(b).suit));
// Qué llevas: para que se vea de un vistazo (pares, medias, duples, juego, punto).
function jugadaChips(codes) {
  if (!codes || codes.length !== 4) return "";
  const { pares, total } = evalHand(codes);
  const chips = [];
  chips.push(pares === "sin pares" ? ["Sin pares", "off"] : [pares.charAt(0).toUpperCase() + pares.slice(1), "on"]);
  if (total === 31) chips.push(["31 · la mejor jugada de juego", "gold"]);
  else if (total === 32) chips.push(["Juego: 32", "on"]);
  else if (total > 31) chips.push([`Juego: ${total}`, "on"]);
  else chips.push([`Sin juego · punto ${total}`, "off"]);
  return chips.map(([t, c]) => `<span class="jugada ${c}">${esc(t)}</span>`).join("");
}
// Jugadas de una mano (para explicar el conteo).
function evalHand(codes) {
  const cards = codes.map(parseCard).map(({ rank, suit }) => ({ rank: rank === 3 ? 12 : rank === 2 ? 1 : rank, suit }));
  const counts = {};
  cards.forEach((c) => { counts[c.rank] = (counts[c.rank] || 0) + 1; });
  const groups = Object.entries(counts).filter(([, n]) => n >= 2).map(([r, n]) => [Number(r), n]);
  const rankName = { 1: "ases", 4: "cuatros", 5: "cincos", 6: "seises", 7: "sietes", 10: "sotas", 11: "caballos", 12: "reyes" };
  let pares = "sin pares";
  if (groups.length === 2 || groups.some(([, n]) => n === 4)) pares = "duples";
  else if (groups.some(([, n]) => n === 3)) pares = `medias de ${rankName[groups[0][0]]}`;
  else if (groups.length === 1) pares = `par de ${rankName[groups[0][0]]}`;
  const total = cards.reduce((t, c) => t + (c.rank >= 10 ? 10 : c.rank), 0);
  return { pares, total };
}
const SOUND_OF = {
  MusCut: "cut", BetPlaced: "bet", BetRaised: "bet", BetAccepted: "accept", OrdagoAccepted: "accept",
  BetRejected: "reject", OrdagoDeclared: "ordago", PointsAwarded: "points", GameFinished: "end", DealerAssigned: "deal",
};

// ------------------------------------------------------------------ navegación
const views = { home, learn, arena, stats, settings: settingsView, game: () => renderGame(), tutorial, training, admin: adminView };
function go(name, ...args) {
  document.querySelectorAll(".topnav button").forEach((b) => b.setAttribute("aria-current", b.dataset.nav === name ? "page" : "false"));
  $main.innerHTML = "";
  (views[name] || home)(...args);
  $main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}
document.addEventListener("click", (e) => {
  const nav = e.target.closest("[data-nav]");
  if (nav) { e.preventDefault(); go(nav.dataset.nav); }
});
document.getElementById("mute").addEventListener("click", () => { settings.sound = !settings.sound; saveSettings(); });
document.getElementById("account").addEventListener("click", () => (user ? accountMenu() : loginDialog()));

// ------------------------------------------------------------------ inicio (JUGAR)
function home() {
  $main.append(h(`
  <div class="page">
    <section class="hero">
      <div>
        <p class="kicker muted">Reglamento de la Federación Española de Mus</p>
        <h1>El Mus que aprende cómo juegas.</h1>
        <p>Una mesa de Mus tradicional llevada al mundo digital: juega, aprende, compite y analiza tu estilo frente a bots que se adaptan a ti.</p>
        <div class="row">
          <button class="btn primary" id="quick">Partida rápida</button>
          <button class="btn" data-nav="tutorial">¿No sabes jugar? Empieza aquí</button>
        </div>
      </div>
      <div class="hero-table" aria-hidden="true"><div class="hand">${["12O", "3C", "1E", "11B"].map((c) => cardHTML(c)).join("")}</div></div>
    </section>
    <section class="pillars" aria-label="Modos de juego">
      <div class="panel stack">
        <span class="kicker">Jugar</span><h2 class="card-title">Personalizada</h2>
        <form id="custom" class="stack">
          <fieldset class="players-choice"><legend>Jugadores</legend>
            <label><input type="radio" name="players" value="bot" checked> Yo con un bot contra 2 bots</label>
            <label><input type="radio" name="players" value="pareja"> Yo y otra persona contra 2 bots</label>
            <label><input type="radio" name="players" value="cuatro"> 4 personas</label>
            <small class="muted">Varias personas juegan en este mismo dispositivo: al cambiar de turno se tapan las cartas.</small>
          </fieldset>
          <div class="form-grid">
            <label class="field">Rivales<select name="rivals"><option value="sencillo">Sencillo</option><option value="medio" selected>Medio</option><option value="profesional">Profesional</option></select></label>
            <label class="field">Compañero<select name="partner"><option value="sencillo">Bot sencillo</option><option value="medio">Bot medio</option><option value="profesional">Bot profesional</option>${LOCAL ? "" : '<option value="human">Humano (invitación)</option>'}</select></label>
            <label class="field">Tantos<select name="target"><option>40</option><option>30</option><option>20</option><option>60</option></select></label>
            <label class="field">Tu nombre<input name="name" maxlength="24" value="Tú"></label>
            <label class="field">Nombre compañero/a<input name="n2" maxlength="24" placeholder="Compañero"></label>
            <label class="field">Nombre rival 1<input name="n1" maxlength="24" placeholder="Bot 1"></label>
            <label class="field">Nombre rival 2<input name="n3" maxlength="24" placeholder="Bot 2"></label>
            <label class="field">Avatar<select name="avatar"><option>🧑</option><option>👩</option><option>👨</option><option>🧔</option><option>👩‍🎓</option><option>🧑‍🏫</option></select></label>
            <label class="field">Semilla (opcional)<input name="seed" inputmode="numeric" pattern="[0-9]*"></label>
          </div>
          <button class="btn primary">Empezar</button>
        </form>
      </div>
      <div class="panel stack">
        <span class="kicker">Entrenar</span><h2 class="card-title">Contra un bot</h2>
        <p class="muted">Elige un bot concreto y enfréntate a él tantas veces como quieras.</p>
        <label class="field">Bot<select id="vs-bot"><option value="sencillo">Sencillo</option><option value="medio">Medio</option><option value="profesional">Profesional</option></select></label>
        <button class="btn" id="vs-start">Jugar contra este bot</button>
        <hr style="border:0;border-top:1px solid var(--line);width:100%">
        <h2 class="card-title">Entrenamiento</h2>
        <p class="muted">Sin presión: con el asistente de reglas abierto y análisis al terminar.</p>
        <button class="btn" id="train-game">Partida de entrenamiento</button>
        <button class="btn ghost" data-nav="training">Situaciones de entrenamiento</button>
      </div>
      <div class="panel stack">
        <span class="kicker">Continuar</span><h2 class="card-title">Tus partidas</h2>
        <div id="resume" class="stack muted">Inicia sesión para guardar tu historial, estadísticas y logros.</div>
      </div>
    </section>
  </div>`));
  document.getElementById("quick").onclick = () => startGame({ mode: "rapida", rivals: "medio", partner: "sencillo" });
  document.getElementById("vs-start").onclick = () => {
    const b = document.getElementById("vs-bot").value;
    startGame({ mode: "contra_bot", rivals: b, partner: "sencillo" });
  };
  document.getElementById("train-game").onclick = () => startGame({ mode: "entrenamiento", rivals: "sencillo", partner: "sencillo" }, { help: true });
  document.getElementById("custom").onsubmit = (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const names = {};
    if (f.get("n1")) names["1"] = f.get("n1");
    if (f.get("n3")) names["3"] = f.get("n3");
    if (f.get("n2")) names["2"] = f.get("n2");
    startGame({
      mode: "personalizada", players: f.get("players"), rivals: f.get("rivals"), partner: f.get("partner"), target: Number(f.get("target")),
      name: f.get("name") || "Tú", names, avatar: f.get("avatar"), seed: f.get("seed") ? Number(f.get("seed")) : null,
    });
  };
  if (user) {
    api("/api/history").then((games) => {
      const el = document.getElementById("resume");
      if (!games.length) { el.textContent = "Aún no has jugado ninguna partida."; return; }
      el.innerHTML = games.slice(0, 6).map((g) => `<div class="row" style="justify-content:space-between">
        <span>${new Date(g.started_at * 1000).toLocaleDateString()} · ${esc(g.mode)}</span>
        <span>${g.status === "FINISHED" ? (g.won ? "✔ Victoria" : "✘ Derrota") : `<button class="btn ghost" data-resume="${g.id}">Continuar</button>`}
        ${g.status === "FINISHED" ? `<button class="btn ghost" data-replay="${g.id}">▶ Replay</button>` : ""}</span></div>`).join("");
      el.querySelectorAll("[data-replay]").forEach((b) => (b.onclick = () => openReplay(b.dataset.replay)));
      el.querySelectorAll("[data-resume]").forEach((b) => (b.onclick = () => resumeGame(b.dataset.resume)));
    }).catch(() => {});
  }
}

// ------------------------------------------------------------------ partida
async function startGame(body, opts = {}) {
  try {
    const data = await api("/api/games", { method: "POST", body });
    current = {
      id: data.game_id, token: data.seat_token, tokens: data.seat_tokens || {}, obs: data.observation, seen: 0,
      help: Boolean(opts.help), discard: new Set(), amount: 2, busy: false, bubbles: {}, gestures: {},
    };
    current.seen = maxSeq(current.obs);
    store.set("musst.current", { id: current.id, token: current.token, tokens: current.tokens });
    play("deal");
    go("game");
  } catch (err) { toast(err.message); }
}
async function resumeGame(id) {
  try {
    const { seat_token } = await api(`/api/games/${id}/reclaim`, { method: "POST" });
    const obs = await api(`/api/games/${id}`, { token: seat_token });
    current = { id, token: seat_token, obs, seen: maxSeq(obs), help: false, discard: new Set(), amount: 2, busy: false };
    go("game");
  } catch (err) { toast(err.message); }
}
const maxSeq = (obs) => obs.history.reduce((m, e) => Math.max(m, e.seq), -1);

function seatPosition(seat, me) {
  // Orden antihorario: el jugador a mi derecha es (me+1). Compañero enfrente.
  return { 0: "bottom", 1: "right", 2: "top", 3: "left" }[(seat - me + 4) % 4];
}

// ------------------------------------------------------------------ caras, voz y conteo
// Caras dibujadas: miran hacia donde mira cada jugador y hacen los gestos oficiales de las
// señas (FEM VIII.2) cuando las ves. Cada asiento tiene un aspecto distinto.
const LOOKS = [
  { skin: "#f1c9a5", hair: "#3b2a1e", style: "corto" }, { skin: "#e0ac85", hair: "#7a4a24", style: "boina" },
  { skin: "#f5d6b8", hair: "#a8a39a", style: "calvo" }, { skin: "#c98f68", hair: "#1d1612", style: "rizado" },
];
const POS_VEC = { bottom: [0, 1], right: [1, 0], top: [0, -1], left: [-1, 0] };
function faceSVG(seat, { pos, lookPos, gesture = null, team = 0, bot = true }) {
  const L = LOOKS[seat % 4];
  const me = POS_VEC[pos] || [0, 1];
  const to = lookPos === "mesa" ? [0, 0] : POS_VEC[lookPos] || [0, 0];
  let dx = to[0] - me[0], dy = to[1] - me[1];
  const n = Math.hypot(dx, dy) || 1; dx = (dx / n) * 2.4; dy = (dy / n) * 1.8;
  if (lookPos === "mesa") dy = 2;
  const g = gesture;
  const closedL = g === "treinta_y_una" || g === "ciego", closedR = g === "ciego";
  const eye = (x, closed) => (closed ? `<path d="M${x - 4} 30q4 2 8 0" stroke="#2a1d14" stroke-width="1.6" fill="none"/>`
    : `<ellipse cx="${x}" cy="30" rx="4" ry="3.4" fill="#fff"/><circle cx="${x + dx}" cy="${30 + dy}" r="1.9" fill="#2a1d14"/>`);
  const browY = g === "duples" ? 21 : 24;
  const mouth = {
    dos_reyes: '<path d="M26 44q6 3 12 0" stroke="#7a2a2a" stroke-width="2" fill="none"/><rect x="28" y="41.5" width="8" height="2.4" rx="1" fill="#fff"/>',
    dos_ases: '<path d="M27 43q5 3 10 0" stroke="#7a2a2a" stroke-width="1.8" fill="none"/><path d="M29.5 44h5v4a2.5 2.5 0 0 1-5 0z" fill="#e46b7a"/>',
    medias_ases: '<path d="M27 43q5 3 10 0" stroke="#7a2a2a" stroke-width="1.8" fill="none"/><path d="M34 44h5v3.5a2.5 2.5 0 0 1-5 0z" fill="#e46b7a"/>',
    medias: '<path d="M32 44q4 1.5 8-1" stroke="#7a2a2a" stroke-width="2" fill="none"/>',
    medias_reyes: '<path d="M32 44q4 1.5 8-1" stroke="#7a2a2a" stroke-width="2" fill="none"/>',
    juego: '<ellipse cx="32" cy="44" rx="3" ry="2.4" fill="#b8475a"/>',
  }[g] || '<path d="M27 43q5 3 10 0" stroke="#7a2a2a" stroke-width="1.8" fill="none"/>';
  const hair = {
    corto: `<path d="M18 26q0-14 14-14t14 14q-4-7-14-7t-14 7z" fill="${L.hair}"/>`,
    boina: `<ellipse cx="32" cy="16" rx="15" ry="5" fill="#2d2d38"/><circle cx="32" cy="11" r="1.6" fill="#2d2d38"/>`,
    calvo: `<path d="M17 30q-1-6 3-9M47 30q1-6-3-9" stroke="${L.hair}" stroke-width="3" fill="none"/>`,
    rizado: `<path d="M17 27q-2-15 15-15t15 15q-3-3-5-1-2-4-5-2-2-3-5-1-3-3-5 0-3-2-5 1-2-2-5 3z" fill="${L.hair}"/>`,
  }[L.style];
  const shL = g === "treinta" || g === "veintinueve" ? -4 : 0, shR = g === "treinta" ? -4 : 0;
  const tilt = g === "pares" ? "rotate(-12 32 34)" : "";
  const color = team === 0 ? "var(--team-a)" : "var(--team-b)";
  return `<svg class="face ${g ? "gesturing" : ""}" viewBox="0 0 64 64" aria-hidden="true">
    <path d="M6 64q2-${12 - shL / 2} 14-${14 - shL}h24q12 ${2 + shR} 14 ${14 + shR / 2}z" fill="${color}"/>
    <g transform="${tilt}"><rect x="28" y="44" width="8" height="8" fill="${L.skin}"/>
    <ellipse cx="32" cy="32" rx="14" ry="16" fill="${L.skin}"/>${hair}
    <path d="M23 ${browY}h6M35 ${browY}h6" stroke="${L.hair === "#a8a39a" ? "#6b665e" : L.hair}" stroke-width="2" stroke-linecap="round"/>
    ${eye(26, closedL)}${eye(38, closedR)}<path d="M32 32v5" stroke="#00000033" stroke-width="1.4"/>${mouth}</g>
    ${bot ? "" : ""}</svg>`;
}

// Voz de los bots (síntesis de voz del navegador, en español).
let voices = [];
try { speechSynthesis.onvoiceschanged = () => { voices = speechSynthesis.getVoices(); }; voices = speechSynthesis.getVoices(); } catch { /* sin voz */ }
function voiceOn() { return settings.voice && settings.sound && typeof speechSynthesis !== "undefined"; }
// Habla y bocadillo van juntos: el bocadillo aparece cuando empieza la voz y se espera a que acabe.
function speakWithBubble(text, seat, minMs = 900) {
  const show = () => { current.bubbles = { ...(current.bubbles || {}), [seat]: text }; renderGame(); };
  if (!voiceOn() || !text) { show(); return sleep(minMs); }
  return new Promise((resolve) => {
    let started = false, done = false;
    const finish = () => { if (done) return; done = true; if (!started) show(); setTimeout(resolve, 250); };
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text.replace(/[«»¡!¿?]/g, ""));
      const es = voices.filter((v) => v.lang && v.lang.startsWith("es"));
      if (es.length) u.voice = es[seat % es.length];
      u.lang = "es-ES"; u.pitch = [1, 0.8, 1.2, 0.9][seat % 4]; u.rate = Math.min(1.4, 1.05 / Math.max(0.6, settings.speed));
      u.onstart = () => { started = true; show(); };
      u.onend = finish; u.onerror = finish;
      speechSynthesis.speak(u);
      setTimeout(() => { if (!started) { started = true; show(); } }, 700); // sin voces instaladas
      setTimeout(finish, 6000);
    } catch { finish(); }
  });
}
// Lo que digo yo al jugar (mi voz).
function myPhrase(action) {
  return {
    mus: "Mus", cut: "No hay mus", pass: "Paso", accept: "Quiero", accept_no_lose: "Quiero y no pierdo",
    reject: "No quiero", ordago: "¡Órdago!",
  }[action.type] ?? (action.type === "bet" ? (action.amount === 2 ? "Envido" : `Envido ${action.amount}`)
    : action.type === "raise" ? `${action.amount} más` : action.type === "discard" ? `Dame ${action.cards.length}` : "");
}
// Jugar hablando: reconocimiento de voz del navegador (Chrome, Edge, Safari).
const VOICE_CMDS = [
  [/no hay mus|corto|cortar/, { type: "cut" }], [/\bmus\b/, { type: "mus" }], [/no quiero/, { type: "reject" }],
  [/quiero/, { type: "accept" }], [/órdago|ordago/, { type: "ordago" }], [/paso/, { type: "pass" }],
  [/envido|envid/, { type: "bet" }], [/repart/, { type: "deal" }],
];
function listen() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { toast("Tu navegador no permite jugar hablando (prueba con Chrome)"); return; }
  const rec = new SR();
  rec.lang = "es-ES"; rec.interimResults = false; rec.maxAlternatives = 3;
  toast("🎤 Te escucho: di «mus», «no hay mus», «paso», «envido», «quiero», «no quiero», «órdago» o «repartir»");
  rec.onresult = (ev) => {
    const said = [...ev.results[0]].map((r) => r.transcript.toLowerCase()).join(" | ");
    const hit = VOICE_CMDS.find(([re]) => re.test(said));
    if (!hit) { toast(`No he entendido: «${said.split(" | ")[0]}»`); return; }
    const action = { ...hit[1] };
    if (action.type === "deal") { document.getElementById("deal-btn")?.click(); return; }
    const n = said.match(/\b(\d+)\b/);
    const spec = current.obs.legal_actions.find((x) => x.type === action.type || (action.type === "bet" && x.type === "raise"));
    if (!spec) { toast("Eso no se puede hacer ahora"); return; }
    if (spec.type === "raise" || spec.type === "bet") { action.type = spec.type; action.amount = Math.min(spec.max, Math.max(spec.min, n ? Number(n[1]) : 2)); }
    send(action);
  };
  rec.onerror = (e) => toast(e.error === "not-allowed" ? "Permite el micrófono para jugar hablando" : "No se ha podido escuchar");
  rec.start();
}

// Amarracos (5 tantos) y piedras (1 tanto), como en la mesa real.
function stonesHTML(points) {
  const am = Math.floor(points / 5), st = points % 5;
  return `<span class="am-row">${'<span class="am"></span>'.repeat(am)}</span><span class="st-row">${'<span class="st"></span>'.repeat(st)}</span>`;
}

// Conteo de la jugada, paso a paso, en el centro de la mesa.
const shortRank = (code) => { const { rank } = parseCard(code); return { 1: "A", 2: "A", 3: "R", 10: "S", 11: "C", 12: "R" }[rank] ?? String(rank); };
function buildReview(obs, round) {
  const names = obs.seats.map((s) => s.name);
  const ev = obs.history.filter((e) => e.round === round);
  const hands = ev.find((e) => e.kind === "HandsRevealed")?.payload.hands;
  if (!hands) return null;
  const teamName = (t) => (t === obs.team ? "tu pareja" : "la pareja rival");
  const pts = (lance) => ev.filter((e) => e.kind === "PointsAwarded" && e.payload.lance === lance);
  const steps = [{ title: "Se enseñan las cartas", text: "Ahora se cuenta la jugada, lance a lance, en el orden del reglamento: grande, chica, pares y juego (o punto).", seats: [] }];
  const resolved = ev.filter((e) => e.kind === "LanceResolved");
  for (const r of resolved) {
    const lance = r.payload.lance, w = r.payload.winner_seat, status = r.payload.status;
    const award = pts(lance);
    const lines = [];
    const order = (code) => { const r = parseCard(code).rank; return r === 3 ? 12 : r === 2 ? 1 : r; };
    const hand = (s) => [...hands[String(s)]].sort((a, b) => order(b) - order(a)).map(shortRank).join(" ");
    if (lance === "pares") obs.seats.forEach((s) => lines.push(`${names[s.seat]}: ${evalHand(hands[String(s.seat)]).pares}`));
    if (lance === "juego" || lance === "punto") obs.seats.forEach((s) => lines.push(`${names[s.seat]}: ${evalHand(hands[String(s.seat)]).total}${lance === "juego" && evalHand(hands[String(s.seat)]).total >= 31 ? " (juego)" : ""}`));
    let head;
    if (w == null) head = lance === "pares" ? "Nadie tiene pares." : "Nadie lleva este lance.";
    else head = `Gana ${names[w]} (${hand(w)})${lance === "grande" ? ": la mejor grande, las cartas más altas" : lance === "chica" ? ": la mejor chica, las cartas más bajas" : ""}.`;
    const how = { passed: "Se pasó.", accepted: "Hubo envite y se quiso.", rejected: "Hubo envite y no se quiso.", no_bet: "Sin envites (solo una pareja podía jugarlo).", ordago: "Órdago." }[status] || "";
    const points = award.map((a) => `+${a.payload.points} para ${teamName(a.payload.team)} (${{ paso: "en paso", envite: "envite querido", negada: "no quisieron: en el acto", envite_no_querido: "reenvite no querido: en el acto", pares: "sus pares", juego: "su juego", punto: "el punto" }[a.payload.concept] ?? a.payload.concept})`);
    steps.push({ title: LANCE[lance], text: [head, how, ...lines].filter(Boolean).join(" · "), points, seats: w == null ? [] : (lance === "grande" || lance === "chica" || lance === "punto" ? [w] : [w, (w + 2) % 4]) });
  }
  const mine = ev.filter((e) => e.kind === "PointsAwarded" && e.payload.team === obs.team).reduce((t, e) => t + e.payload.points, 0);
  const theirs = ev.filter((e) => e.kind === "PointsAwarded" && e.payload.team !== obs.team).reduce((t, e) => t + e.payload.points, 0);
  const score = ev.filter((e) => e.kind === "RoundFinished").pop()?.payload.score || obs.score;
  steps.push({ title: "Total de la jugada", text: `Tu pareja +${mine} · rivales +${theirs}. Marcador: ${score[obs.team]} – ${score[1 - obs.team]} (se gana a ${obs.target}).`, seats: [], last: true });
  return { round, hands, steps };
}

function renderGame(bubbles = current?.bubbles || {}) {
  if (!current) { go("home"); return; }
  const obs = current.obs;
  const me = obs.seat;
  const names = obs.seats.map((s) => s.name);
  const lances = ["grande", "chica", "pares", "juego", "punto"];
  const doneIdx = lances.indexOf(obs.phase);
  const lanceBar = lances.map((l, i) => {
    if (l === "juego" && obs.phase === "punto") return "";
    if (l === "punto" && obs.phase !== "punto") return "";
    const cls = l === obs.phase ? "current" : doneIdx > i ? "done" : "";
    return `<span class="lance ${cls}">${LANCE[l]}</span>`;
  }).join("");
  const phaseName = { mus: "Mus", discard: "Descarte", game_over: "Fin" }[obs.phase] ?? LANCE[obs.phase];
  const myTeam = obs.team;
  const humanTeam = (t) => obs.seats.filter((s) => s.team === t).every((s) => s.kind === "human");
  const teamLabel = (t) => (t === myTeam ? "Tu pareja" : humanTeam(t) ? "Pareja rival" : "Pareja bots");
  // Conteo paso a paso antes de repartir la jugada siguiente
  if (obs.awaiting_deal && obs.round > 1 && (!current.review || current.review.round !== obs.round - 1)) {
    const r = buildReview(obs, obs.round - 1);
    current.review = r ? { ...r, step: 0 } : { round: obs.round - 1, steps: [], step: 0, done: true };
  }
  const review = obs.awaiting_deal && current.review && !current.review.done && current.review.steps.length ? current.review : null;
  const step = review ? review.steps[review.step] : null;
  const scoreLine = (t) => {
    const pts = obs.score[t];
    const left = obs.target - pts;
    return `<div class="score-line"><span class="team-dot" style="background:var(${t === 0 ? "--team-a" : "--team-b"})"></span>
      <span>${teamLabel(t)}</span>${left > 0 && left <= 4 ? '<span class="dentro">dentro</span>' : ""}
      <strong aria-label="${pts} tantos">${pts}</strong></div>`;
  };
  const tableScore = (t, where) => `<div class="table-score ${where}" aria-label="${teamLabel(t)}: ${obs.score[t]} tantos">
      <small>${teamLabel(t)}</small><div class="stones">${stonesHTML(obs.score[t])}</div><strong>${obs.score[t]}</strong></div>`;
  const seatHTML = (s) => {
    const pos = seatPosition(s.seat, me);
    const decl = (k) => (obs.declarations[k] && obs.declarations[k][String(s.seat)] !== undefined
      ? `<span class="chip ${obs.declarations[k][String(s.seat)] ? "si" : "no"}">${k === "pares" ? "Pares" : "Juego"}: ${obs.declarations[k][String(s.seat)] ? "sí ✔" : "no ✘"}</span>` : "");
    const shown = review ? review.hands[String(s.seat)] : obs.revealed_hands && obs.revealed_hands[String(s.seat)];
    const lit = step && step.seats.includes(s.seat);
    const cards = s.seat === me && !review ? "" : shown
      ? `<div class="hand ${lit ? "lit" : ""}">${sortHand(shown).map((c) => cardHTML(c, { small: true })).join("")}</div>`
      : `<div class="backs" role="img" aria-label="4 cartas ocultas">${'<span class="back"></span>'.repeat(4)}</div>`;
    const bubble = bubbles[s.seat] ? `<span class="bubble ${/ÓRDAGO/i.test(bubbles[s.seat]) ? "ordago" : ""}">${esc(bubbles[s.seat])}</span>` : "";
    const status = s.waiting ? '<span class="chip">esperando…</span>' : !s.connected ? '<span class="chip">desconectado</span>' : "";
    const target = obs.gazes && obs.gazes.length ? obs.gazes[s.seat] : undefined;
    const lookPos = target == null ? "mesa" : seatPosition(target, me);
    const gaze = target === undefined ? "" : `<span class="chip gaze ${target === me && s.seat !== me ? "on-me" : ""}">👀 ${target == null ? "la mesa" : target === me ? (s.seat === me ? "" : "te mira") : esc(names[target])}</span>`;
    const face = faceSVG(s.seat, { pos, lookPos, gesture: current.gestures?.[s.seat], team: s.team, bot: s.kind === "bot" });
    const canLook = obs.gazes && obs.gazes.length && s.seat !== me && !obs.finished;
    const avatar = canLook
      ? `<button class="avatar face-btn ${obs.gazes[me] === s.seat ? "watched" : ""}" data-look="${s.seat}" aria-label="Mirar a ${esc(s.name)}" title="Mirar a ${esc(s.name)}">${face}</button>`
      : `<div class="avatar" aria-hidden="true">${face}</div>`;
    return `<div class="seat ${pos} ${obs.turn === s.seat && !obs.awaiting_deal ? "turn" : ""} ${lit ? "lit" : ""}" style="--team-color:var(${s.team === 0 ? "--team-a" : "--team-b"})">
      ${bubble}${avatar}
      <div class="seat-name">${esc(s.name)}${s.seat === me ? " (tú)" : ""}${s.level ? ` <span class="chip">${esc(s.level)}</span>` : ""}</div>
      <div class="seat-meta"><span class="chip">${s.team === 0 ? "◆ Pareja A" : "● Pareja B"}</span>${obs.mano === s.seat ? '<span class="chip mano">mano</span>' : ""}${decl("pares")}${decl("juego")}${status}${gaze}</div>
      ${pos === "bottom" && !review ? "" : cards}</div>`;
  };
  const bet = obs.current_bet;
  const betInfo = bet ? (bet.is_ordago ? `Órdago de la pareja ${bet.bettor_team === 0 ? "A" : "B"}` : `En juego: ${bet.stake} tantos`) : "";
  const finished = obs.finished;
  const handoff = current.handoff;
  const myTurn = obs.turn === me && !finished && !obs.awaiting_deal && handoff == null;
  const dealerPos = seatPosition(obs.dealer, me);
  const deck = `<div class="deck deck-${dealerPos}" aria-label="Baraja, a la derecha de ${esc(names[obs.dealer])} (reparte)" role="img">
    ${'<span class="back"></span>'.repeat(4)}<small>Reparte ${esc(names[obs.dealer])}</small></div>`;
  let center;
  if (review) {
    center = `<div class="review" role="region" aria-label="Conteo de la jugada ${review.round}">
      <small>Conteo de la jugada ${review.round} · ${review.step + 1}/${review.steps.length}</small>
      <div class="lance-title">${esc(step.title)}</div><p>${esc(step.text)}</p>
      ${step.points?.length ? `<ul>${step.points.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>` : step.last ? "" : '<p class="muted">Sin tantos en este lance.</p>'}
      <div class="row">${review.step > 0 ? '<button class="btn small-btn" id="rev-prev">◀ Anterior</button>' : ""}
        ${step.last ? `<button class="btn primary" id="deal-btn">${obs.dealer === me ? "Repartir" : "¿Repartimos? Sí"}</button>` : '<button class="btn primary" id="rev-next">Siguiente ▶</button>'}</div></div>`;
  } else if (obs.awaiting_deal) {
    center = `<div><div class="lance-title">Reparto</div><p>${obs.dealer === me ? "Te toca repartir." : `Reparte ${esc(names[obs.dealer])}; la baraja está a su derecha.`} Es mano ${esc(names[obs.mano])}.</p>
      <button class="btn primary" id="deal-btn">${obs.dealer === me ? "Repartir" : "¿Repartimos? Sí"}</button></div>`;
  } else {
    center = `<div><div class="lance-title">${esc(phaseName)}</div><div class="bet-info">${esc(betInfo)}</div>
      <div class="bet-info">${finished ? (obs.winner === myTeam ? "¡Habéis ganado!" : "Ha ganado la pareja rival") : myTurn ? "Te toca" : `Habla ${esc(names[obs.turn] ?? "")}`}</div></div>`;
  }
  const watching = (obs.gazes || []).map((g, s) => (g === me && s !== me ? s : null)).filter((s) => s != null);
  const seen = Object.entries(obs.signals_seen || {}).filter(([s]) => Number(s) !== me);
  const myLook = obs.gazes && obs.gazes.length ? obs.gazes[me] : undefined;
  const partnerWatching = watching.includes(obs.partner);
  const rivalWatching = watching.some((x) => x % 2 !== myTeam);
  const moment = partnerWatching && !rivalWatching ? ["good", "✅ Buen momento: te mira tu compañero y ningún rival."]
    : rivalWatching ? ["bad", `⚠️ Cuidado: te mira ${watching.filter((x) => x % 2 !== myTeam).map((x) => esc(names[x])).join(" y ")} (rival). Si haces la seña, la verá.`]
      : ["off", "😶 Nadie te mira: si haces la seña ahora, no la verá nadie."];
  const signalPanel = obs.gazes && obs.gazes.length && !finished && !handoff ? `<section class="signals panel" aria-label="Señas">
      <div class="sig-col">
        <h2 class="card-title">👀 Ver señas</h2>
        <p>${myLook == null ? "Ahora miras a la mesa." : `Ahora miras a <strong>${esc(names[myLook])}</strong>${myLook === obs.partner ? " (tu compañero)" : " (rival)"}.`}</p>
        <p class="muted">Pulsa la cara de un jugador para mirarle. Solo verás sus señas mientras le mires: lo normal es mirar a tu compañero.</p>
        ${myLook !== obs.partner ? `<button class="btn small-btn" data-look="${obs.partner}">Mirar a mi compañero</button>` : ""}
        ${seen.length ? `<div class="seen-list">${seen.map(([x, list]) => `<div class="seen ${Number(x) === obs.partner ? "ally" : "foe"}"><strong>${esc(names[x])}</strong> ${Number(x) === obs.partner ? "(compañero)" : "(rival)"}:
          ${list.map((g) => `<span class="sig-chip">${SIGNAL_ICON[g] ?? "✋"} ${esc(SIGNALS[g]?.[1] ?? g)}</span>`).join(" ")}</div>`).join("")}</div>` : '<p class="muted">Aún no has visto ninguna seña en esta jugada.</p>'}
      </div>
      <div class="sig-col">
        <h2 class="card-title">✋ Hacer una seña</h2>
        ${(obs.available_signals || []).length ? `<p class="moment ${moment[0]}">${moment[1]}</p>
          <div class="sig-buttons">${obs.available_signals.map((x) => `<button class="sig-btn" data-signal="${x}"><span class="sig-icon" aria-hidden="true">${SIGNAL_ICON[x] ?? "✋"}</span><strong>${esc(SIGNALS[x]?.[1] ?? x)}</strong><small>${esc(SIGNALS[x]?.[0] ?? "")}</small></button>`).join("")}</div>
          <p class="muted">Solo puedes hacer señas verdaderas, después de cortar el mus.</p>`
        : `<p class="muted">${obs.phase === "mus" || obs.phase === "discard" ? "Las señas se hacen después de cortar el mus." : "Ya has hecho tus señas en esta jugada."}</p>`}
      </div>
    </section>` : "";
  const curtain = handoff != null ? `<div class="curtain panel stack" role="dialog" aria-label="Cambio de jugador">
      <h2 class="card-title">Turno de ${esc(names[handoff])}</h2><p>Pasa el dispositivo a ${esc(names[handoff])}. Las cartas están tapadas.</p>
      <button class="btn primary" id="handoff-btn">Soy ${esc(names[handoff])}: ver mis cartas</button></div>` : "";
  $main.innerHTML = "";
  $main.append(h(`
  <div class="game">
    <h1 class="sr-only">Mesa de juego</h1>
    <div class="scorebar" role="region" aria-label="Marcador">
      <div><div class="lances" aria-label="Lances">${lanceBar}</div><small class="muted">Jugada ${obs.round} · a ${obs.target} tantos · ${current.obs.mode}</small></div>
      <div class="scores">${scoreLine(myTeam)}${scoreLine(1 - myTeam)}</div>
    </div>
    ${obs.invite ? `<div class="invite">Invita a tu compañero: comparte este enlace <code>${location.origin}${location.pathname}#join/${obs.game_id}/${obs.invite}</code></div>` : ""}
    <div class="table ${review ? "reviewing" : ""}" role="region" aria-label="Mesa de Mus">
      ${obs.seats.filter((s) => s.seat !== me).map(seatHTML).join("")}
      <div class="center">${center}</div>
      ${seatHTML(obs.seats[me])}
      ${tableScore(myTeam, "mine")}${tableScore(1 - myTeam, "theirs")}
      ${finished ? "" : deck}
    </div>
    ${curtain}
    ${handoff != null || review ? "" : `<div class="my-cards"><div class="hand" id="my-hand" aria-label="Tus cartas, de mayor a menor">${sortHand(obs.hand).map((c) => cardHTML(c, { button: obs.phase === "discard" && myTurn, pressed: current.discard.has(c) })).join("")}</div>
      <div class="jugadas" aria-label="Lo que llevas">${jugadaChips(obs.hand)}</div></div>`}
    <div class="status-line" id="status"></div>
    <div class="actions" id="actions" role="group" aria-label="Acciones disponibles"></div>
    ${signalPanel}
    <div class="row" style="justify-content:center">
      <button class="btn ghost" id="help-btn" aria-expanded="${current.help}">? ¿Qué puedo hacer?</button>
      ${finished ? '<button class="btn primary" id="summary-btn">Ver resumen</button>' : ""}
      <button class="btn ghost" id="log-btn">Historial de la jugada</button>
      ${finished ? "" : '<button class="btn ghost" id="mic-btn" title="Di tu jugada en voz alta">🎤 Jugar hablando</button>'}
    </div>
    <div id="help" class="help-panel" ${current.help ? "" : "hidden"}></div>
  </div>`));
  document.getElementById("mic-btn")?.addEventListener("click", listen);
  renderActions();
  document.getElementById("deal-btn")?.addEventListener("click", () => { if (current.review) current.review.done = true; dealCards(); });
  document.getElementById("rev-next")?.addEventListener("click", () => { current.review.step += 1; renderGame(); });
  document.getElementById("rev-prev")?.addEventListener("click", () => { current.review.step -= 1; renderGame(); });
  document.getElementById("handoff-btn")?.addEventListener("click", () => switchViewer(handoff));
  document.querySelectorAll("[data-look]").forEach((b) => (b.onclick = () => lookAt(Number(b.dataset.look))));
  document.querySelectorAll("[data-signal]").forEach((b) => (b.onclick = () => makeSignal(b.dataset.signal)));
  scheduleTick();
  document.getElementById("help-btn").onclick = () => { current.help = !current.help; renderGame(); };
  document.getElementById("log-btn").onclick = () => showLog();
  if (finished) document.getElementById("summary-btn").onclick = () => showSummary();
  if (current.help) loadHelp();
  document.querySelectorAll("#my-hand button.card").forEach((b) => (b.onclick = () => {
    const code = b.dataset.card;
    if (current.discard.has(code)) current.discard.delete(code); else current.discard.add(code);
    b.setAttribute("aria-pressed", String(current.discard.has(code)));
    renderActions();
  }));
  if (!myTurn && !finished) schedulePoll();
}

function renderActions() {
  const obs = current.obs;
  const $a = document.getElementById("actions");
  if (!$a) return;
  $a.innerHTML = "";
  if (obs.finished || obs.turn !== obs.seat || obs.awaiting_deal || current.handoff != null) return;
  const specs = Object.fromEntries(obs.legal_actions.map((s) => [s.type, s]));
  const add = (label, cls, action, key) => {
    const b = document.createElement("button");
    b.className = `act ${cls}`; b.textContent = label; b.type = "button";
    if (key) b.setAttribute("aria-keyshortcuts", key);
    b.onclick = () => send(action);
    $a.append(b);
  };
  if (specs.mus) add("MUS", "", { type: "mus" }, "M");
  if (specs.cut) add("NO MUS · CORTO", "", { type: "cut" }, "C");
  if (specs.discard) {
    const n = current.discard.size;
    const b = document.createElement("button");
    b.className = "act"; b.type = "button";
    b.textContent = n ? `DESCARTAR ${n}` : "Elige cartas para descartar";
    b.disabled = n < (specs.discard.min ?? 1);
    b.onclick = () => { const cards = [...current.discard]; current.discard = new Set(); send({ type: "discard", cards }); };
    $a.append(b);
  }
  if (specs.pass) add("PASO", "", { type: "pass" }, "P");
  const amountSpec = specs.bet || specs.raise;
  if (amountSpec) {
    current.amount = Math.min(Math.max(current.amount, amountSpec.min), amountSpec.max);
    const wrap = document.createElement("div");
    wrap.className = "amount";
    wrap.innerHTML = `<button type="button" aria-label="Menos">−</button><output aria-live="polite">${current.amount}</output><button type="button" aria-label="Más">+</button>`;
    const [minus, , plus] = wrap.children;
    minus.onclick = () => { current.amount = Math.max(amountSpec.min, current.amount - 1); renderActions(); };
    plus.onclick = () => { current.amount = Math.min(amountSpec.max, current.amount + 1); renderActions(); };
    const kind = specs.bet ? "bet" : "raise";
    const b = document.createElement("button");
    b.className = "act"; b.type = "button";
    b.textContent = kind === "bet" ? (current.amount === 2 ? "ENVIDO" : `ENVIDO ${current.amount}`) : `REENVÍO +${current.amount}`;
    b.setAttribute("aria-keyshortcuts", "E");
    b.onclick = () => send({ type: kind, amount: current.amount });
    $a.append(wrap, b);
  }
  if (specs.accept) add("QUIERO", "quiero", { type: "accept" }, "Q");
  if (specs.accept_no_lose) add("QUIERO Y NO PIERDO", "quiero", { type: "accept_no_lose" });
  if (specs.reject) add("NO QUIERO", "noquiero", { type: "reject" }, "N");
  if (specs.ordago) add("ÓRDAGO", "ordago", { type: "ordago" }, "O");
}

document.addEventListener("keydown", (e) => {
  if (!current || e.target.closest("input, select, textarea, dialog")) return;
  const map = { p: "pass", q: "accept", n: "reject", o: "ordago", m: "mus", c: "cut", e: "bet" };
  const type = map[e.key.toLowerCase()];
  if (!type || current.obs.turn !== current.obs.seat) return;
  const spec = current.obs.legal_actions.find((s) => s.type === type);
  if (spec) send(type === "bet" ? { type, amount: current.amount } : { type });
});

async function send(action) {
  if (current.busy) return;
  current.busy = true;
  try {
    const mine = myPhrase(action);
    if (mine) await speakWithBubble(mine, current.obs.seat, 500);
    const obs = await api(`/api/games/${current.id}/action`, { method: "POST", body: { action }, token: current.token });
    await animateTo(obs);
  } catch (err) {
    toast(err.message);
  } finally {
    current.busy = false;
  }
}

async function animateTo(obs) {
  if (current.animating) { current.pendingObs = obs; return; }
  current.animating = true;
  try {
    const names = obs.seats.map((s) => s.name);
    const fresh = obs.history.filter((e) => e.seq > current.seen);
    const prevRound = current.obs.round;
    current.bubbles = current.bubbles || {};
    for (const e of fresh) {
      const bubble = BUBBLE[e.kind];
      if (SOUND_OF[e.kind]) play(SOUND_OF[e.kind]);
      const text = eventText(e, names);
      if (text) announce(text);
      if (e.kind === "LanceStarted" || e.kind === "DealerAssigned") current.bubbles = {};
      const human = obs.seats[e.actor]?.kind === "human";
      if (bubble && e.round === prevRound && e.actor !== obs.seat) {
        // Lo que dice cada jugador se queda en su bocadillo hasta el siguiente lance.
        const phrase = human ? myPhrase({ type: { BetPlaced: "bet", BetRaised: "raise", OrdagoDeclared: "ordago", BetAccepted: "accept", OrdagoAccepted: "accept", BetRejected: "reject", Passed: "pass", MusRequested: "mus", MusCut: "cut" }[e.kind] ?? "", amount: e.payload.amount }) || BUBBLE[e.kind] : talk(e);
        setStatus(text);
        await speakWithBubble(phrase, e.actor, e.kind === "PairsDeclared" || e.kind === "GameDeclared" ? 650 : 1100);
      } else if (e.kind === "HandsRevealed" && e.round === prevRound) {
        setStatus("Se enseñan las cartas");
        current.obs = { ...current.obs, revealed_hands: e.payload.hands };
        renderGame();
        await sleep(1500);
      } else if (e.kind === "SignalSeen" || (e.kind === "SignalMade" && e.actor !== obs.seat)) {
        // La seña se ve en su cara: el gesto oficial durante unos segundos.
        const from = e.payload.seat;
        current.gestures = { ...(current.gestures || {}), [from]: e.payload.signal };
        renderGame();
        toast(`👁 ${names[from]} ${SIGNALS[e.payload.signal]?.[0]?.toLowerCase() ?? "hace una seña"}: ${SIGNALS[e.payload.signal]?.[1] ?? ""}`);
        await sleep(1800);
        delete current.gestures[from];
      } else if (e.kind === "SignalMade" && e.actor === obs.seat) {
        current.gestures = { ...(current.gestures || {}), [obs.seat]: e.payload.signal };
        setTimeout(() => { delete current.gestures[obs.seat]; }, 1800);
      } else if (e.kind === "RoundFinished" && e.round === prevRound) {
        const lastPts = obs.history.filter((x) => x.round === prevRound && x.kind === "PointsAwarded");
        const mine = lastPts.filter((x) => x.payload.team === obs.team).reduce((t, x) => t + x.payload.points, 0);
        const theirs = lastPts.filter((x) => x.payload.team !== obs.team).reduce((t, x) => t + x.payload.points, 0);
        const bot = obs.seats.find((s) => s.kind === "bot" && s.team !== obs.team) || obs.seats.find((s) => s.kind === "bot");
        if (bot) {
          const pool = (bot.team === obs.team ? mine >= theirs : theirs > mine) ? BANTER_WIN : BANTER_LOSE;
          const phrase = pool[e.seq % pool.length];
          current.bubbles = {};
          await speakWithBubble(phrase, bot.seat, 1100);
        }
        current.bubbles = {};
      }
    }
    current.seen = maxSeq(obs);
    current.obs = obs;
    checkHandoff();
    renderGame();
    if (obs.finished) { store.set("musst.current", null); setTimeout(showSummary, 600); syncFinishedGame(obs.game_id); }
  } finally {
    current.animating = false;
  }
  if (current.pendingObs) { const next = current.pendingObs; current.pendingObs = null; await animateTo(next); }
}

// Varias personas en el mismo dispositivo: al tocarle a otra persona se tapan las cartas.
function checkHandoff() {
  const obs = current.obs;
  const tokens = current.tokens || {};
  const t = obs.turn;
  current.handoff = !obs.finished && !obs.awaiting_deal && t != null && t !== obs.seat && tokens[String(t)] ? t : null;
}
async function switchViewer(seat) {
  const token = current.tokens?.[String(seat)];
  if (!token) return;
  try {
    const obs = await api(`/api/games/${current.id}`, { token });
    current.token = token; current.obs = obs; current.seen = maxSeq(obs); current.handoff = null;
    current.discard = new Set(); current.bubbles = {};
    store.set("musst.current", { id: current.id, token, tokens: current.tokens });
    renderGame();
  } catch (err) { toast(err.message); }
}
async function lookAt(seat) {
  try {
    const target = current.obs.gazes[current.obs.seat] === seat ? null : seat;
    const obs = await api(`/api/games/${current.id}/look`, { method: "POST", body: { target }, token: current.token });
    await animateTo(obs);
  } catch (err) { toast(err.message); }
}
// Reparto: se pregunta antes y se ve cómo van saliendo las cartas de la baraja, de una en
// una y en sentido antihorario empezando por el mano (FEM III.2).
async function dealCards() {
  if (current.busy) return;
  current.busy = true;
  try {
    const obs = await api(`/api/games/${current.id}/deal`, { method: "POST", token: current.token });
    play("deal");
    await animateDeal(obs);
    // Mis cartas se ven nada más repartir; después hablan los que van antes que yo.
    current.obs = { ...current.obs, hand: obs.hand, awaiting_deal: false, legal_actions: [], dealer: obs.dealer, mano: obs.mano };
    renderGame();
    current.busy = false;
    await animateTo(obs);
  } catch (err) { toast(err.message); } finally { current.busy = false; }
}
async function animateDeal(obs) {
  const table = document.querySelector(".table");
  const deck = document.querySelector(".deck");
  if (!table || !deck || settings.reduce_motion) return;
  const me = obs.seat;
  const from = deck.getBoundingClientRect();
  const origin = table.getBoundingClientRect();
  const order = [0, 1, 2, 3].map((i) => (obs.mano + i) % 4);
  for (let round = 0; round < 4; round += 1) {
    for (const seat of order) {
      const target = document.querySelector(`.seat.${seatPosition(seat, me)} .avatar`);
      if (!target) continue;
      const to = target.getBoundingClientRect();
      const card = document.createElement("span");
      card.className = "back flying";
      card.style.left = `${from.left - origin.left}px`;
      card.style.top = `${from.top - origin.top}px`;
      table.append(card);
      requestAnimationFrame(() => {
        card.style.transform = `translate(${to.left - from.left + round * 6}px, ${to.top - from.top + 20}px) rotate(${round * 8 - 12}deg)`;
      });
      await sleep(110);
    }
  }
  await sleep(500);
  table.querySelectorAll(".flying").forEach((c) => c.remove());
}

async function makeSignal(signal) {
  try {
    const obs = await api(`/api/games/${current.id}/signal`, { method: "POST", body: { signal }, token: current.token });
    const made = obs.history.filter((e) => e.kind === "SignalMade" && e.actor === obs.seat).pop();
    const names = obs.seats.map((s) => s.name);
    const seenBy = made ? made.payload.seen_by : [];
    toast(seenBy.length ? `Te han visto: ${seenBy.map((s) => names[s] + (s === obs.partner ? " (compañero)" : " (rival)")).join(", ")}` : "Nadie te miraba: la seña se ha perdido");
    current.obs = obs; current.seen = maxSeq(obs);
    renderGame();
  } catch (err) { toast(err.message); }
}

// Reloj de la mesa: las miradas cambian con el tiempo y los bots pueden hacer señas.
let tickTimer;
function scheduleTick() {
  clearTimeout(tickTimer);
  const obs = current?.obs;
  if (!obs || obs.finished || obs.awaiting_deal || !obs.gazes || !obs.gazes.length) return;
  tickTimer = setTimeout(async () => {
    if (!current || !document.querySelector(".game")) return;
    if (current.busy || current.animating || current.handoff != null) { scheduleTick(); return; }
    try {
      const fresh = await api(`/api/games/${current.id}/tick`, { method: "POST", token: current.token });
      if (!current.busy) await animateTo(fresh); else scheduleTick();
    } catch { scheduleTick(); }
  }, 2200 * settings.speed);
}

function setStatus(text) { const el = document.getElementById("status"); if (el && text) el.textContent = text; }

let pollTimer;
function schedulePoll() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    if (!current || current.obs.finished || current.obs.turn === current.obs.seat || !document.querySelector(".game")) return;
    try { await animateTo(await api(`/api/games/${current.id}`, { token: current.token })); } catch { schedulePoll(); }
  }, 1500);
}

async function loadHelp() {
  try {
    const data = await api(`/api/games/${current.id}/help`, { token: current.token });
    const el = document.getElementById("help");
    if (!el) return;
    el.innerHTML = `<strong>${esc(data.phase)}</strong>${data.note ? `<p>${esc(data.note)}</p>` : ""}
      ${data.actions.length ? `<ul>${data.actions.map((a) => `<li>${esc(a.text)}</li>`).join("")}</ul>` : `<p>${esc(data.note || "Espera tu turno.")}</p>`}
      <p class="muted">El asistente solo explica las acciones legales. La decisión es tuya.</p>`;
  } catch { /* sin ayuda */ }
}

function showLog() {
  const obs = current.obs;
  const names = obs.seats.map((s) => s.name);
  const lines = obs.history.filter((e) => e.round === obs.round).map((e) => eventText(e, names)).filter(Boolean);
  openModal(`<h2 id="modal-title">Jugada ${obs.round}</h2><div class="event-log"><ol>${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ol></div>
    <div class="row" style="margin-top:12px"><button class="btn" data-close>Cerrar</button></div>`);
}

async function showSummary() {
  try {
    const a = await api(`/api/games/${current.id}/analysis`, { token: current.token });
    const won = a.result.winner === a.result.my_team;
    const s = a.stats;
    openModal(`
      <h2 id="modal-title">${won ? "Victoria" : "Derrota"} · ${a.result.reason === "ordago" ? "por órdago" : `${a.result.score[a.result.my_team]} – ${a.result.score[1 - a.result.my_team]}`}</h2>
      <h3>Momentos clave</h3>
      <ul>${a.key_moments.map((m) => `<li>Jugada ${m.round_no}: ${esc(m.description)}</li>`).join("") || "<li>Partida tranquila.</li>"}</ul>
      <h3>Tu partida</h3>
      <div class="table-wrap"><table class="data"><tbody>
        <tr><td>Envites</td><td>${s.envites}</td></tr><tr><td>Órdagos</td><td>${s.ordagos}</td></tr>
        <tr><td>Aceptaciones / rechazos</td><td>${s.aceptaciones} / ${s.rechazos}</td></tr>
        <tr><td>Mus / cortes</td><td>${s.mus} / ${s.cortes}</td></tr>
        <tr><td>Envites con mano débil</td><td>${s.frecuencia_farol == null ? "—" : Math.round(s.frecuencia_farol * 100) + " %"}</td></tr>
      </tbody></table></div>
      ${(a.counterfactuals || []).length ? `<h3>¿Y si hubieras elegido lo contrario?</h3><ul>${a.counterfactuals.map((c) => `<li>Jugada ${c.jugada}, ${esc(c.lance)} ${c.ordago ? "(órdago)" : `(envite de ${c.envite})`}: elegiste <strong>${c.elegiste}</strong> → ${fmtOutcome(c, c.tantos)}; lo contrario → ${fmtOutcome(c, c.alternativa)}. ${c.acierto ? "✓ Buena decisión" : "✗ Lo contrario era mejor"}</li>`).join("")}</ul><p class="muted">Calculado con las manos ya reveladas, solo al terminar la partida.</p>` : ""}
      ${a.learning.length ? `<h3>Aprendizaje del bot</h3><ul>${a.learning.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : ""}
      <div class="row" style="margin-top:12px">
        <button class="btn primary" id="again">Otra partida</button>
        <button class="btn" id="to-replay">▶ Replay</button>
        <button class="btn ghost" data-close>Cerrar</button>
      </div>`);
    document.getElementById("again").onclick = () => { $modal.close(); startGame({ mode: current.obs.mode, rivals: current.obs.seats[1].level || "medio", partner: current.obs.seats[2].level || "sencillo" }); };
    document.getElementById("to-replay").onclick = () => { $modal.close(); replayFromHistory(a.history, current.obs.seats); };
  } catch (err) { toast(err.message); }
}

// ------------------------------------------------------------------ replay
async function openReplay(id) {
  try {
    const data = await api(`/api/games/${id}/replay`);
    replayFromHistory(data.history, data.seats);
  } catch (err) { toast(err.message); }
}
function replayFromHistory(history, seats) {
  const names = seats.map((s) => s.name);
  const steps = history.filter((e) => eventText(e, names));
  let i = 0; let timer = null;
  $main.innerHTML = "";
  $main.append(h(`<div class="page stack">
    <div class="row" style="justify-content:space-between;align-items:center">
      <h1 class="page-title">Replay</h1>
      <div class="row"><button class="btn" id="r-exit">← Salir del replay</button><button class="btn primary" id="r-new">Jugar otra partida</button></div>
    </div>
    <div class="table" style="min-height:260px" id="replay-table"></div>
    <div class="replay-controls" role="group" aria-label="Controles de reproducción">
      <button class="btn" id="r-first" aria-label="Principio">⏮</button><button class="btn" id="r-prev" aria-label="Anterior">◀</button>
      <button class="btn primary" id="r-play" aria-label="Reproducir">▶ REPRODUCIR</button>
      <button class="btn" id="r-next" aria-label="Siguiente">▶</button><button class="btn" id="r-last" aria-label="Final">⏭</button>
    </div>
    <div class="event-log"><ol id="r-log"></ol></div></div>`));
  const draw = () => {
    const upto = steps.slice(0, i + 1);
    const cur = steps[i];
    let score = [0, 0]; let hands = null; let lance = "";
    for (const e of upto) {
      if (e.kind === "PointsAwarded") score = e.payload.score;
      if (e.kind === "LanceStarted") lance = LANCE[e.payload.lance];
      if (e.kind === "DealerAssigned") { hands = null; lance = "Mus"; }
      if (e.kind === "HandsRevealed") hands = e.payload.hands;
    }
    const seatsHTML = seats.map((s) => `<div class="seat ${seatPosition(s.seat, 0)}">
      ${cur && cur.actor === s.seat && BUBBLE[cur.kind] ? `<span class="bubble">${BUBBLE[cur.kind]}</span>` : ""}
      <div class="avatar">${faceSVG(s.seat, { pos: seatPosition(s.seat, 0), lookPos: "mesa", team: s.seat % 2 })}</div><div class="seat-name">${esc(s.name)}</div>
      ${hands ? `<div class="hand">${hands[String(s.seat)].map((c) => cardHTML(c, { small: true })).join("")}</div>` : '<div class="backs" role="img" aria-label="Mano no revelada">' + '<span class="back"></span>'.repeat(4) + "</div>"}</div>`).join("");
    document.getElementById("replay-table").innerHTML = seatsHTML +
      `<div class="center"><div><div class="lance-title">${esc(lance)}</div><div class="bet-info">A ${score[0]} – B ${score[1]}</div><div class="bet-info">${esc(cur ? eventText(cur, names) : "")}</div></div></div>`;
    const log = document.getElementById("r-log");
    log.innerHTML = upto.slice(-40).map((e, k, arr) => `<li class="${k === arr.length - 1 ? "now" : ""}">${esc(eventText(e, names))}</li>`).join("");
    log.lastElementChild?.scrollIntoView({ block: "nearest" });
  };
  const stop = () => { clearInterval(timer); timer = null; const b = document.getElementById("r-play"); if (b) b.textContent = "▶ REPRODUCIR"; };
  document.getElementById("r-exit").onclick = () => { stop(); go(user ? "stats" : "home"); };
  document.getElementById("r-new").onclick = () => { stop(); current = null; go("home"); };
  document.getElementById("r-first").onclick = () => { stop(); i = 0; draw(); };
  document.getElementById("r-last").onclick = () => { stop(); i = steps.length - 1; draw(); };
  document.getElementById("r-prev").onclick = () => { stop(); i = Math.max(0, i - 1); draw(); };
  document.getElementById("r-next").onclick = () => { stop(); i = Math.min(steps.length - 1, i + 1); draw(); };
  document.getElementById("r-play").onclick = (e) => {
    if (timer) { stop(); return; }
    e.target.textContent = "⏸ PAUSA";
    timer = setInterval(() => { if (i >= steps.length - 1 || !document.getElementById("r-log")) { stop(); return; } i += 1; draw(); }, 700 * settings.speed);
  };
  draw();
}

// ------------------------------------------------------------------ APRENDER
function learn() {
  $main.append(h(`<div class="page stack">
    <h1 class="page-title">Aprender</h1>
    <div class="pillars">
      <div class="panel stack"><span class="kicker">Desde cero</span><h2 class="card-title">Tutorial interactivo</h2>
        <p class="muted">Cartas, mano, mus, grande, chica, pares, juego, punto, envites, órdago y tanteo, con ejemplos.</p>
        <button class="btn primary" data-nav="tutorial">Empezar el tutorial</button></div>
      <div class="panel stack"><span class="kicker">Practicando</span><h2 class="card-title">Aprender jugando</h2>
        <p class="muted">Una partida tranquila contra bots sencillos con el asistente de reglas siempre abierto.</p>
        <button class="btn" id="learn-play">Jugar aprendiendo</button></div>
      <div class="panel stack"><span class="kicker">Decisiones</span><h2 class="card-title">Situaciones de entrenamiento</h2>
        <p class="muted">Situaciones concretas («vas 35-38, te envidan 4…»). Decide y mira el análisis.</p>
        <button class="btn" data-nav="training">Ver situaciones</button></div>
    </div></div>`));
  document.getElementById("learn-play").onclick = () => startGame({ mode: "entrenamiento", rivals: "sencillo", partner: "sencillo" }, { help: true });
}

const TUTORIAL = [
  { t: "La baraja", c: ["1O", "2C", "3E", "4B", "5O", "6C", "7E", "10B", "11O", "12C"],
    p: "Se juega con la baraja española de 40 cartas (sin 8 ni 9) y la modalidad de <strong>ocho reyes y ocho ases</strong>: los treses cuentan como reyes y los doses como ases (Reglamento FEM, cap. II art. 3)." },
  { t: "Parejas y mano", c: [],
    p: "Juegan cuatro personas en dos parejas; los compañeros se sientan enfrente. Se habla en sentido antihorario. El <strong>mano</strong> es el jugador a la derecha del que reparte: habla primero y gana los empates." },
  { t: "El mus", c: ["7O", "6C", "5E", "4B"],
    p: "Con las cuatro cartas, cada jugador dice <strong>«mus»</strong> (quiere cambiar cartas) o <strong>«no hay mus»</strong> (corta). Solo hay descarte si los cuatro dan mus: cada uno cambia de 1 a 4 cartas." },
  { t: "Grande", c: ["12O", "3C", "11E", "7B"],
    p: "Gana quien tenga las cartas más altas, comparando de la más alta a la más baja: rey (y tres), caballo, sota, 7, 6, 5, 4, as (y dos). Esta mano es muy buena a grande: dos reyes." },
  { t: "Chica", c: ["1O", "2C", "4E", "5B"],
    p: "Al revés que la grande: gana quien tenga las cartas más bajas. Dos ases (as y dos) son lo mejor para la chica." },
  { t: "Pares", c: ["12O", "12C", "1E", "1B"],
    p: "<strong>Par</strong>: dos cartas iguales. <strong>Medias</strong>: tres iguales. <strong>Duples</strong>: dos parejas (o cuatro iguales). Duples > medias > par. Antes de jugar, todos dicen «pares sí» o «pares no»; solo hablan quienes tienen." },
  { t: "Juego", c: ["12O", "11C", "10E", "1B"],
    p: "Las figuras valen 10, el as 1 y el resto su número. Hay <strong>juego</strong> con 31 o más. La mejor es la 31, luego 32, 40, 37, 36, 35, 34 y 33. Esta mano suma 31." },
  { t: "Punto", c: ["7O", "7C", "6E", "10B"],
    p: "Si nadie tiene juego, se juega al <strong>punto</strong>: gana quien más se acerque a 30. Esta mano tiene 30, el mejor punto." },
  { t: "Envites", c: [],
    p: "En cada lance se puede <strong>pasar</strong> o <strong>envidar</strong> (envido = 2 tantos). La otra pareja responde <strong>quiero</strong>, <strong>no quiero</strong> o sube. Si no quieren, cobras 1 tanto (la negada) en el acto. Si quieren, los tantos se cuentan al final de la jugada." },
  { t: "Órdago", c: [],
    p: "El <strong>órdago</strong> es apostar la partida entera. Si te lo quieren, se enseñan las cartas y quien gane ese lance gana la partida. Si no, cobras lo que hubiera en juego." },
  { t: "Tanteo", c: [],
    p: "Al final de la jugada se cuentan los tantos en orden: grande, chica, pares, juego o punto. Gana la primera pareja que llega a 40. Los tantos se representan con <strong>amarracos</strong> (cada uno vale 5)." },
];
function tutorial(step = 0) {
  const s = TUTORIAL[step];
  $main.innerHTML = "";
  $main.append(h(`<div class="page"><div class="panel tutorial-step">
    <span class="kicker">Paso ${step + 1} de ${TUTORIAL.length}</span><h1 class="page-title">${s.t}</h1>
    ${s.c.length ? `<div class="example">${s.c.map((c) => cardHTML(c)).join("")}</div>` : ""}
    <p>${s.p}</p>
    <div class="row"><button class="btn" id="t-prev" ${step === 0 ? "disabled" : ""}>Anterior</button>
    ${step < TUTORIAL.length - 1 ? '<button class="btn primary" id="t-next">Siguiente</button>' : '<button class="btn primary" id="t-play">¡A jugar aprendiendo!</button>'}</div>
  </div></div>`));
  document.getElementById("t-prev").onclick = () => tutorial(step - 1);
  const next = document.getElementById("t-next");
  if (next) next.onclick = () => tutorial(step + 1);
  const playBtn = document.getElementById("t-play");
  if (playBtn) playBtn.onclick = () => startGame({ mode: "entrenamiento", rivals: "sencillo", partner: "sencillo" }, { help: true });
}

async function training() {
  $main.append(h('<div class="page stack"><h1 class="page-title">Situaciones de entrenamiento</h1><div id="sc" class="stack"></div></div>'));
  try {
    const list = await api("/api/training/scenarios");
    const box = document.getElementById("sc");
    box.innerHTML = list.map((sc) => {
      const o = sc.observation;
      const opts = o.legal_actions.map((a) => {
        const label = { pass: "PASO", bet: "ENVIDO", accept: "QUIERO", reject: "NO QUIERO", raise: "REENVÍO", ordago: "ÓRDAGO" }[a.type];
        const action = a.type === "bet" || a.type === "raise" ? { type: a.type, amount: 2 } : { type: a.type };
        return `<button class="act ${a.type === "ordago" ? "ordago" : ""}" data-sc="${sc.id}" data-action='${JSON.stringify(action)}'>${label}</button>`;
      }).join("");
      return `<div class="panel stack"><h2 class="card-title">${esc(sc.title)}</h2><p>${esc(sc.prompt)}</p>
        <div class="hand">${o.hand.map((c) => cardHTML(c)).join("")}</div>
        <p class="muted">Marcador ${o.score[0]} – ${o.score[1]} · ${o.mano === 0 ? "eres mano" : "no eres mano"}</p>
        <div class="actions">${opts}</div><div class="result" id="res-${sc.id}"></div></div>`;
    }).join("");
    box.querySelectorAll("[data-sc]").forEach((b) => (b.onclick = async () => {
      const res = await api(`/api/training/scenarios/${b.dataset.sc}`, { method: "POST", body: { action: JSON.parse(b.dataset.action) } });
      document.getElementById(`res-${b.dataset.sc}`).innerHTML = `<div class="help-panel">
        <p><strong>Análisis del agente profesional:</strong> recomienda <strong>${esc(res.recomendacion)}</strong>
        (confianza ${Math.round(res.confianza * 100)} %). Probabilidad estimada de ganar el lance: ${Math.round(res.p_ganar_lance * 100)} %.</p>
        <table class="data"><thead><tr><th>Opción</th><th>Valor esperado</th><th>Riesgo</th></tr></thead><tbody>
        ${res.alternativas.map((a) => `<tr><td>${esc(a.action)}</td><td>${a.ev.toFixed(2)}</td><td>${a.risk.toFixed(2)}</td></tr>`).join("")}</tbody></table>
        <p class="muted">${esc(res.nota)}</p></div>`;
    }));
  } catch (err) { toast(err.message); }
}

// ------------------------------------------------------------------ COMPETIR
async function arena() {
  $main.append(h(`<div class="page stack">
    <h1 class="page-title">Bot Arena</h1>
    <div class="panel stack"><h2 class="card-title">Clasificación</h2><div class="table-wrap" id="board">Cargando…</div>
      <p class="muted">Torneo automático (todos contra todos, mus duplicado). Un bot que falla pierde la partida sin romper el torneo.</p></div>
    <div class="panel stack"><h2 class="card-title">Observar Bot vs Bot</h2>
      <div class="form-grid"><label class="field">Pareja A<select id="wa"></select></label><label class="field">Pareja B<select id="wb"></select></label></div>
      <button class="btn primary" id="watch">Ver partida</button>
      <p class="muted">Solo se muestra información pública: las cartas, al final de cada jugada.</p></div>
  </div>`));
  try {
    const bots = (await api("/api/bots")).filter((b) => !b.external);
    for (const id of ["wa", "wb"]) document.getElementById(id).innerHTML = bots.map((b) => `<option>${esc(b.name)}</option>`).join("");
    document.getElementById("wb").selectedIndex = Math.min(2, bots.length - 1);
    document.getElementById("watch").onclick = async () => {
      const a = document.getElementById("wa").value; const b = document.getElementById("wb").value;
      const data = await api("/api/arena/watch", { method: "POST", body: { team_a: a, team_b: b } });
      replayFromHistory(data.history, data.names.map((n, i) => ({ seat: i, name: `${n} ${i % 2 ? "B" : "A"}`, kind: "bot" })));
    };
    const board = await api("/api/scoreboard");
    document.getElementById("board").innerHTML = board.ranking.length ? `<table class="data"><thead><tr><th class="l">Bot</th><th>Partidas</th><th>V</th><th>D</th><th>% V</th><th>Tantos ±</th><th>Errores</th></tr></thead><tbody>
      ${board.ranking.map((s) => `<tr><td>${esc(s.name)}</td><td>${s.games}</td><td>${s.wins}</td><td>${s.losses}</td><td>${Math.round(s.win_rate * 100)} %</td><td>${s.point_diff_per_game.toFixed(1)}</td><td>${s.errors}</td></tr>`).join("")}</tbody></table>`
      : `<p class="muted">${esc(board.note || "Sin datos")}</p>`;
  } catch (err) { toast(err.message); }
}

// ------------------------------------------------------------------ ANALIZAR
const STYLE_LABEL = {
  bet_with_strong: "Envida con mano buena", bet_with_weak: "Envida con mano floja", accept_with_weak: "Acepta con mano floja",
  aggression: "Agresividad", risk_tolerance: "Riesgo", bluff_frequency: "Farol", acceptance_rate: "Aceptación",
  rejection_rate: "Rechazo", raise_rate: "Reenvites", ordago_rate: "Órdagos", mus_rate: "Mus",
};
async function stats() {
  if (!user) {
    $main.append(h('<div class="page"><div class="panel stack"><h1 class="page-title">Analizar</h1><p>Inicia sesión para guardar tus partidas y ver tu estilo de juego.</p><button class="btn primary" id="go-login">Entrar o registrarse</button></div></div>'));
    document.getElementById("go-login").onclick = loginDialog;
    return;
  }
  try {
    const s = await api("/api/players/me/statistics");
    const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)} %`);
    const spark = s.evolucion.length > 1 ? (() => {
      const w = 300, hgt = 60, max = Math.max(...s.evolucion.map((e) => e.tantos), 1);
      const pts = s.evolucion.map((e, k) => `${(k / (s.evolucion.length - 1)) * w},${hgt - (e.tantos / max) * hgt}`).join(" ");
      return `<svg viewBox="0 0 ${w} ${hgt}" width="100%" height="60" role="img" aria-label="Tantos por partida"><polyline fill="none" stroke="var(--accent)" stroke-width="2" points="${pts}"/></svg>`;
    })() : '<p class="muted">Juega más partidas para ver tu evolución.</p>';
    $main.append(h(`<div class="page stack">
      <h1 class="page-title">Tu estilo de juego</h1>
      <div class="grid-2">
        <div class="panel"><h2 class="card-title">Resumen</h2><table class="data"><tbody>
          <tr><td>Partidas</td><td>${s.partidas}</td></tr><tr><td>Victorias / derrotas</td><td>${s.victorias} / ${s.derrotas}</td></tr>
          <tr><td>% victorias</td><td>${pct(s.porcentaje_victorias)}</td></tr><tr><td>Tantos medios</td><td>${s.tantos_medios == null ? "—" : s.tantos_medios.toFixed(1)}</td></tr>
          <tr><td>Envites / órdagos</td><td>${s.totales.envites ?? 0} / ${s.totales.ordagos ?? 0}</td></tr>
          <tr><td>Aceptaciones / rechazos</td><td>${s.totales.aceptaciones ?? 0} / ${s.totales.rechazos ?? 0}</td></tr>
          <tr><td>Mus</td><td>${s.totales.mus ?? 0}</td></tr></tbody></table></div>
        <div class="panel stack"><h2 class="card-title">Estilo (estimaciones)</h2>
          ${s.perfil ? `<p>La IA te ve como <strong>${esc(s.perfil.label)}</strong> (confianza ${esc(String(s.perfil.confidence).toLowerCase())}).</p>` : ""}
          ${Object.entries(s.estilo).map(([k, v]) => `<div><div class="row" style="justify-content:space-between"><span>${STYLE_LABEL[k] ?? k}</span><span class="muted">${Math.round(v.value * 100)} % · confianza ${v.confidence.toLowerCase()}</span></div><div class="bar"><span style="width:${Math.round(v.value * 100)}%"></span></div></div>`).join("")}
          <p class="muted">Son estadísticas descriptivas con su incertidumbre, no una nota sobre lo bueno que eres.</p></div>
      </div>
      <div class="panel"><h2 class="card-title">Por lance</h2><div class="table-wrap"><table class="data"><thead><tr><th class="l">Lance</th><th>Envites</th><th>Aceptados</th><th>Rechazados</th><th>Pasos</th></tr></thead><tbody>
        ${Object.entries(s.por_lance).map(([l, d]) => `<tr><td>${LANCE[l]}</td><td>${d.envites ?? 0}</td><td>${d.aceptados ?? 0}</td><td>${d.rechazados ?? 0}</td><td>${d.pasos ?? 0}</td></tr>`).join("")}</tbody></table></div></div>
      <div class="panel"><h2 class="card-title">Evolución</h2>${spark}</div>
      <div class="panel"><h2 class="card-title">Logros</h2>${s.logros.length ? s.logros.map((l) => `<span class="badge">🏅 ${esc(l.replaceAll("_", " "))}</span> `).join("") : '<p class="muted">Todavía ninguno.</p>'}</div>
      <div class="panel"><h2 class="card-title">Historial</h2><div id="hist" class="stack"></div></div>
    </div>`));
    const games = await api("/api/history");
    document.getElementById("hist").innerHTML = games.map((g) => `<div class="row" style="justify-content:space-between"><span>${new Date(g.started_at * 1000).toLocaleString()} · ${esc(g.mode)} · ${g.score ? g.score.join("–") : ""}</span>
      ${g.status === "FINISHED" ? `<button class="btn ghost" data-replay="${g.id}">▶ Replay</button>` : `<button class="btn ghost" data-resume="${g.id}">Continuar</button>`}</div>`).join("") || '<p class="muted">Sin partidas.</p>';
    document.querySelectorAll("[data-replay]").forEach((b) => (b.onclick = () => openReplay(b.dataset.replay)));
    document.querySelectorAll("[data-resume]").forEach((b) => (b.onclick = () => resumeGame(b.dataset.resume)));
  } catch (err) { toast(err.message); }
}

// ------------------------------------------------------------------ ajustes y cuenta
function settingsView() {
  const opt = (name, values, cur) => values.map(([v, l]) => `<option value="${v}" ${String(cur) === String(v) ? "selected" : ""}>${l}</option>`).join("");
  $main.append(h(`<div class="page"><div class="panel stack"><h1 class="page-title">Ajustes</h1>
    <form id="sf" class="form-grid">
      <label class="field">Tema<select name="theme">${opt("theme", [["auto", "Automático"], ["light", "Claro"], ["dark", "Oscuro"]], settings.theme)}</select></label>
      <label class="field">Tamaño de texto<select name="text_size">${opt("t", [[0.9, "Pequeño"], [1, "Normal"], [1.15, "Grande"], [1.3, "Muy grande"]], settings.text_size)}</select></label>
      <label class="field">Velocidad de animaciones<select name="speed">${opt("s", [[0.5, "Rápida"], [1, "Normal"], [1.6, "Lenta"]], settings.speed)}</select></label>
      <label class="field">Mesa<select name="table">${opt("m", [["verde", "Tapete verde"], ["granate", "Granate"], ["azul", "Azul"]], settings.table)}</select></label>
      <label class="field">Reverso de cartas<select name="card_back">${opt("b", [["rayas", "Clásico"], ["liso", "Liso"], ["escudo", "Escudo"]], settings.card_back)}</select></label>
      <label class="field"><span><input type="checkbox" name="reduce_motion" ${settings.reduce_motion ? "checked" : ""}> Reducir animaciones</span></label>
      <label class="field"><span><input type="checkbox" name="sound" ${settings.sound ? "checked" : ""}> Efectos de sonido</span></label>
      <label class="field"><span><input type="checkbox" name="voice" ${settings.voice ? "checked" : ""}> Voz de los bots</span></label>
    </form></div></div>`));
  document.getElementById("sf").onchange = (e) => {
    const f = new FormData(e.currentTarget);
    settings = {
      ...settings, theme: f.get("theme"), text_size: Number(f.get("text_size")), speed: Number(f.get("speed")),
      table: f.get("table"), card_back: f.get("card_back"), reduce_motion: f.get("reduce_motion") === "on", sound: f.get("sound") === "on", voice: f.get("voice") === "on",
    };
    saveSettings();
  };
}

function loginDialog() {
  openModal(`<h2 id="modal-title">Entrar</h2>
    <form id="lf" class="stack">
      <label class="field">Usuario<input name="username" autocomplete="username" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_.\\-]+"></label>
      ${LOCAL && cloud.cloudEnabled() ? `<label class="field">Contraseña<input name="password" type="password" autocomplete="current-password" required minlength="8"></label>
      <p class="muted">Tu cuenta guarda tus partidas y lo que la IA aprende de tu forma de jugar, en cualquier dispositivo.</p>
      <div class="row"><button class="btn primary" value="login">Entrar</button><button class="btn" value="register">Crear cuenta</button><button class="btn ghost" type="button" data-close>Cancelar</button></div>`
      : `<label class="field">Contraseña<input name="password" type="password" autocomplete="current-password" required minlength="8"></label>
      <p class="muted">${LOCAL ? "Las cuentas se guardan en este navegador. La primera que se crea es la de administración." : "Solo guardamos tu usuario y un hash de la contraseña. Nada más."}</p>
      <div class="row"><button class="btn primary" value="login">Entrar</button><button class="btn" value="register">Crear cuenta</button><button class="btn ghost" type="button" data-close>Cancelar</button></div>`}
    </form>`);
  document.getElementById("lf").onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const kind = e.submitter?.value === "register" ? "register" : "login";
    try {
      if (LOCAL && cloud.cloudEnabled()) {
        const prof = kind === "register"
          ? await cloud.signUp(f.get("username"), f.get("password"))
          : await cloud.signIn(f.get("username"), f.get("password"));
        await attachCloudProfile(prof);
      } else {
        await api(`/api/auth/${kind}`, { method: "POST", body: { username: f.get("username"), password: f.get("password") } });
      }
      $modal.close();
      await loadUser();
      toast(kind === "register" ? (canAdmin() ? "Cuenta creada: eres administrador/a" : "Cuenta creada") : `Hola, ${user ? user.username : ""}`);
      go("home");
    } catch (err) { toast(err.message); }
  };
}
function accountMenu() {
  openModal(`<h2 id="modal-title">${esc(user.username)}</h2><div class="row">
    <button class="btn" id="to-stats">Mis estadísticas</button><button class="btn" id="logout">Salir</button><button class="btn ghost" data-close>Cerrar</button></div>`);
  document.getElementById("to-stats").onclick = () => { $modal.close(); go("stats"); };
  document.getElementById("logout").onclick = async () => {
    if (cloud.cloudEnabled()) await cloud.signOut();
    await api("/api/auth/logout", { method: "POST" }); user = null; $modal.close(); updateAccount(); go("home");
  };
}
function updateAccount() {
  document.getElementById("account").textContent = user ? user.username : "Entrar";
  const nav = document.querySelector(".topnav");
  let admin = nav.querySelector('[data-nav="admin"]');
  if (canAdmin() && !admin) {
    admin = document.createElement("button"); admin.dataset.nav = "admin"; admin.textContent = "Admin"; nav.append(admin);
  } else if (!canAdmin() && admin) admin.remove();
}
const canAdmin = () => (cloud.cloudEnabled() ? cloud.isAdmin() : user?.role === "admin");
// El panel funciona igual con Supabase o con las cuentas del propio navegador / servidor.
const adminApi = {
  data: () => (cloud.cloudEnabled() ? cloud.adminData() : api("/api/admin/overview")),
  create: (username, password, role) => (cloud.cloudEnabled() ? cloud.adminCreateUser(username, password, role)
    : api("/api/admin/users", { method: "POST", body: { username, password, role } })),
  update: (id, changes) => (cloud.cloudEnabled() ? cloud.adminUpdateUser(id, changes)
    : api(`/api/admin/users/${id}`, { method: "PUT", body: Object.fromEntries(Object.entries(changes).filter(([, v]) => v)) })),
  remove: (id) => (cloud.cloudEnabled() ? cloud.adminDeleteUser(id) : api(`/api/admin/users/${id}`, { method: "DELETE" })),
};
// Cuenta en Supabase → perfil local del motor (mismo nombre) + lo que la IA ya sabía.
async function attachCloudProfile(prof) {
  if (!prof) return;
  await api("/api/auth/login", { method: "POST", body: { username: prof.username, cloud: true } });
  try {
    const memory = await cloud.pullMemory();
    await api("/api/cloud/import", { method: "POST", body: memory });
  } catch (err) { toast(`No se pudo traer tu historial: ${err.message}`); }
}
const synced = new Set();
async function syncFinishedGame(gameId) {
  if (synced.has(gameId)) return;
  synced.add(gameId);
  if (!LOCAL || !cloud.cloudEnabled() || !cloud.cloudProfile() || !user) return;
  try {
    const exported = await api(`/api/cloud/export/${gameId}`);
    await cloud.pushGame(exported);
    toast("Partida guardada en tu cuenta");
  } catch (err) { toast(`No se pudo guardar en la nube: ${err.message}`); }
}
async function loadUser() {
  try { user = await api("/api/me"); } catch { user = null; }
  if (user && user.settings && Object.keys(user.settings).length) { settings = { ...settings, ...user.settings }; applySettings(); }
  updateAccount();
}

// ------------------------------------------------------------------ administración
// Panel del administrador: usuarios (crear, editar, borrar), actividad, resultados contra cada
// nivel de bot, estilos de juego que la IA ha detectado y autocrítica de los bots.
const pct = (v) => (v == null || Number.isNaN(v) ? "—" : `${Math.round(v * 100)} %`);
const fmtDate = (d) => (d ? new Date(d).toLocaleDateString("es-ES", { day: "2-digit", month: "short", year: "numeric" }) : "—");
function barChart(rows, { label, unit = "", max } = {}) {
  // Una sola serie: barras con extremo redondeado, valor al pasar el ratón (title) y tabla equivalente.
  const top = max ?? Math.max(1, ...rows.map((r) => r.value));
  const w = 640, hgt = 160, gap = 2, bw = Math.max(4, (w - gap * rows.length) / Math.max(1, rows.length));
  const bars = rows.map((r, i) => {
    const bh = Math.round((r.value / top) * (hgt - 20));
    return `<g><title>${esc(r.label)}: ${r.value}${unit}</title><rect class="hit" x="${i * (bw + gap)}" y="0" width="${bw}" height="${hgt}" fill="transparent"/>
      <rect x="${i * (bw + gap)}" y="${hgt - bh}" width="${bw}" height="${bh}" rx="${Math.min(4, bw / 2)}" fill="var(--accent)"/></g>`;
  }).join("");
  return `<figure class="chart"><svg viewBox="0 0 ${w} ${hgt}" width="100%" role="img" aria-label="${esc(label)}">
    <line x1="0" x2="${w}" y1="${hgt - 0.5}" y2="${hgt - 0.5}" stroke="var(--line)"/>${bars}</svg>
    <figcaption class="muted">${esc(label)} · máximo ${top}${unit}</figcaption></figure>`;
}
async function adminView() {
  if (!canAdmin()) { go("home"); return; }
  $main.append(h('<div class="page stack"><h1 class="page-title">Administración</h1><div id="adm">Cargando…</div></div>'));
  let d;
  try { d = await adminApi.data(); } catch (err) { document.getElementById("adm").textContent = err.message; return; }
  const byUser = Object.fromEntries(d.users.map((u) => [u.id, { ...u, games: [], model: null }]));
  d.games.forEach((g) => byUser[g.user_id]?.games.push(g));
  d.models.forEach((m) => { if (byUser[m.user_id]) byUser[m.user_id].model = m; });
  const users = Object.values(byUser);
  const wins = d.games.filter((g) => g.won).length;
  const week = Date.now() - 7 * 864e5;
  const active = users.filter((u) => u.games.some((g) => new Date(g.created_at) > week)).length;
  // actividad: partidas por día, últimos 30 días
  const days = [...Array(30)].map((_, i) => { const t = new Date(Date.now() - (29 - i) * 864e5); return t.toISOString().slice(0, 10); });
  const perDay = days.map((day) => ({ label: day, value: d.games.filter((g) => g.created_at.slice(0, 10) === day).length }));
  const levels = ["sencillo", "medio", "profesional"].map((lv) => {
    const gs = d.games.filter((g) => g.rivals === lv);
    return { lv, n: gs.length, rate: gs.length ? gs.filter((g) => g.won).length / gs.length : null };
  });
  const styles = {};
  users.forEach((u) => { const s = u.model?.style || "sin datos aún"; styles[s] = (styles[s] || 0) + 1; });
  const review = d.memory.find((m) => m.key === "self:profesional")?.data;
  const mistakeRows = review ? Object.entries(review.mistakes).map(([k, [e, n]]) => { const [lance, kind] = k.split("|"); return { lance, kind, e, n }; }).filter((r) => r.kind !== "pass").sort((a, b) => b.n - a.n) : [];
  const calib = review ? Object.entries(review.calibration).reduce((acc, [k, [w, n]]) => { const b = Number(k.split("|")[1]); acc[b] = acc[b] || [0, 0]; acc[b][0] += w; acc[b][1] += n; return acc; }, {}) : {};
  const el = document.getElementById("adm");
  el.innerHTML = `
    <div class="tiles">
      <div class="tile"><span>Usuarios</span><strong>${users.length}</strong><small>${users.filter((u) => u.role === "admin").length} admin</small></div>
      <div class="tile"><span>Activos 7 días</span><strong>${active}</strong></div>
      <div class="tile"><span>Partidas</span><strong>${d.games.length}</strong></div>
      <div class="tile"><span>Victorias de humanos</span><strong>${pct(d.games.length ? wins / d.games.length : null)}</strong></div>
      <div class="tile"><span>Decisiones revisadas por el bot</span><strong>${review ? Object.values(review.calibration).reduce((t, [, n]) => t + n, 0) : 0}</strong><small>${review ? review.games : 0} revisiones</small></div>
    </div>
    <div class="panel"><h2 class="card-title">Partidas por día (30 días)</h2>${barChart(perDay, { label: "Partidas por día" })}</div>
    <div class="grid-2">
      <div class="panel"><h2 class="card-title">Humanos contra cada nivel</h2><table class="data"><thead><tr><th class="l">Rivales</th><th>Partidas</th><th>% victorias humanas</th></tr></thead>
        <tbody>${levels.map((l) => `<tr><td class="l">${l.lv}</td><td>${l.n}</td><td>${pct(l.rate)}</td></tr>`).join("")}</tbody></table></div>
      <div class="panel"><h2 class="card-title">Estilos detectados por la IA</h2><table class="data"><tbody>${Object.entries(styles).map(([s, n]) => `<tr><td class="l">${esc(s)}</td><td>${n}</td></tr>`).join("")}</tbody></table></div>
    </div>
    <div class="panel stack"><div class="row" style="justify-content:space-between"><h2 class="card-title">Usuarios</h2><button class="btn primary" id="adm-new">Crear usuario</button></div>
      <div class="table-wrap"><table class="data" id="adm-users"><thead><tr><th class="l">Usuario</th><th>Rol</th><th>Alta</th><th>Última vez</th><th>Partidas</th><th>% victorias</th><th class="l">Estilo</th><th></th></tr></thead><tbody>
      ${users.map((u) => `<tr><td class="l"><button class="link" data-detail="${u.id}">${esc(u.username)}</button></td><td>${u.role}</td><td>${fmtDate(u.created_at)}</td><td>${fmtDate(u.last_seen)}</td>
        <td>${u.games.length}</td><td>${pct(u.games.length ? u.games.filter((g) => g.won).length / u.games.length : null)}</td><td class="l">${esc(u.model?.style || "—")}</td>
        <td><button class="btn small-btn" data-edit="${u.id}">Editar</button> <button class="btn small-btn" data-del="${u.id}">Borrar</button></td></tr>`).join("")}
      </tbody></table></div></div>
    <div class="grid-2">
      <div class="panel"><h2 class="card-title">Autocrítica del bot profesional: errores por lance</h2>${mistakeRows.length ? `<table class="data"><thead><tr><th class="l">Lance</th><th class="l">Decisión</th><th>Veces</th><th>% errores</th></tr></thead><tbody>
        ${mistakeRows.slice(0, 12).map((r) => `<tr><td class="l">${r.lance}</td><td class="l">${r.kind}</td><td>${Math.round(r.n)}</td><td>${pct(r.e / r.n)}</td></tr>`).join("")}</tbody></table>` : '<p class="muted">Aún no hay partidas revisadas.</p>'}</div>
      <div class="panel"><h2 class="card-title">Calibración: lo que creía vs. lo que pasó</h2>${Object.keys(calib).length ? `<table class="data"><thead><tr><th class="l">Creía ganar</th><th>Ganó de verdad</th><th>Casos</th></tr></thead><tbody>
        ${Object.entries(calib).sort((a, b) => a[0] - b[0]).map(([b, [w, n]]) => `<tr><td class="l">${b * 10}–${b * 10 + 10} %</td><td>${pct(w / n)}</td><td>${Math.round(n)}</td></tr>`).join("")}</tbody></table>
        <p class="muted">Si "ganó de verdad" se aleja del tramo, el bot corrige sus estimaciones en las siguientes partidas.</p>` : '<p class="muted">Sin datos todavía.</p>'}</div>
    </div>`;
  document.getElementById("adm-new").onclick = () => userDialog();
  el.querySelectorAll("[data-edit]").forEach((b) => (b.onclick = () => userDialog(byUser[b.dataset.edit])));
  el.querySelectorAll("[data-del]").forEach((b) => (b.onclick = () => deleteDialog(byUser[b.dataset.del])));
  el.querySelectorAll("[data-detail]").forEach((b) => (b.onclick = () => userDetail(byUser[b.dataset.detail])));
}
function userDialog(u = null) {
  openModal(`<h2 id="modal-title">${u ? `Editar ${esc(u.username)}` : "Crear usuario"}</h2>
    <form id="uf" class="stack">
      <label class="field">Usuario<input name="username" value="${u ? esc(u.username) : ""}" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_.\\-]+"></label>
      <label class="field">Rol<select name="role"><option value="player" ${u?.role === "player" ? "selected" : ""}>Jugador</option><option value="admin" ${u?.role === "admin" ? "selected" : ""}>Administrador</option></select></label>
      <label class="field">${u ? "Nueva contraseña (vacío = no cambiar)" : "Contraseña"}<input name="password" type="password" ${u ? "" : "required"} minlength="8" autocomplete="new-password"></label>
      <div class="row"><button class="btn primary">${u ? "Guardar" : "Crear"}</button><button class="btn ghost" type="button" data-close>Cancelar</button></div>
    </form>`);
  document.getElementById("uf").onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      if (u) await adminApi.update(u.id, { username: f.get("username") !== u.username ? f.get("username") : null, role: f.get("role") !== u.role ? f.get("role") : null, password: f.get("password") || null });
      else await adminApi.create(f.get("username"), f.get("password"), f.get("role"));
      $modal.close(); toast(u ? "Usuario actualizado" : "Usuario creado"); go("admin");
    } catch (err) { toast(err.message); }
  };
}
function deleteDialog(u) {
  openModal(`<h2 id="modal-title">¿Borrar a ${esc(u.username)}?</h2><p>Se borran su cuenta, sus ${u.games.length} partidas y lo que la IA había aprendido de su juego. No se puede deshacer.</p>
    <div class="row"><button class="btn primary" id="del-yes">Borrar definitivamente</button><button class="btn ghost" data-close>Cancelar</button></div>`);
  document.getElementById("del-yes").onclick = async () => {
    try { await adminApi.remove(u.id); $modal.close(); toast("Usuario borrado"); go("admin"); } catch (err) { toast(err.message); }
  };
}
function userDetail(u) {
  const rates = u.model?.model?.rates || {};
  const rate = (m) => { const r = rates[`${m}|*|*`]; return r && r[1] ? r[0] / r[1] : null; };
  const stake = (b) => { const s = u.model?.model?.stakes?.[`*|${b}`]; return s && s[1] ? (s[0] / s[1]).toFixed(1) : "—"; };
  const metrics = [["Agresividad (envida cuando abre)", "aggression"], ["Envida con mano buena", "bet_with_strong"], ["Envida con mano floja (farol)", "bet_with_weak"],
    ["Acepta envites", "acceptance_rate"], ["Acepta con mano floja", "accept_with_weak"], ["Sube / reenvida", "raise_rate"], ["Órdagos", "ordago_rate"], ["Pide mus", "mus_rate"]];
  openModal(`<h2 id="modal-title">${esc(u.username)} · ${esc(u.model?.style || "sin datos aún")}</h2>
    <table class="data"><tbody>${metrics.map(([t, m]) => `<tr><td class="l">${t}</td><td>${pct(rate(m))}</td></tr>`).join("")}
      <tr><td class="l">Piedras medias con mano buena / floja</td><td>${stake("fuerte")} / ${stake("floja")}</td></tr>
      <tr><td class="l">Partidas que conoce la IA</td><td>${u.model?.model?.games ?? 0}</td></tr></tbody></table>
    <h3>Últimas partidas</h3><ul>${u.games.slice(-8).reverse().map((g) => `<li>${fmtDate(g.created_at)} · ${g.won ? "Victoria" : "Derrota"} ${g.score[0]}–${g.score[1]} contra ${esc(g.rivals || "?")}</li>`).join("") || "<li>Ninguna</li>"}</ul>
    <div class="row"><button class="btn ghost" data-close>Cerrar</button></div>`);
}

// ------------------------------------------------------------------ arranque
async function boot() {
  applySettings();
  if (LOCAL) {
    try { await startWorker(); } catch { return; }
    try {
      if (await cloud.initCloud()) {
        const prof = cloud.cloudProfile();
        if (prof) await attachCloudProfile(prof);
        else await api("/api/auth/logout", { method: "POST" }); // sin sesión en la nube, sin perfil
      }
    } catch (err) { toast(`Cuentas no disponibles: ${err.message}`); }
  }
  await loadUser();
  const join = location.hash.match(/^#join\/([\w-]+)\/([\w-]+)/);
  if (join) {
    const name = prompt("Tu nombre para la partida:", "Compañero") || "Compañero";
    try {
      const data = await api(`/api/games/${join[1]}/join`, { method: "POST", body: { invite: join[2], name } });
      current = { id: data.game_id, token: data.seat_token, obs: data.observation, seen: maxSeq(data.observation), help: false, discard: new Set(), amount: 2, busy: false };
      history.replaceState(null, "", location.pathname);
      go("game");
      return;
    } catch (err) { toast(err.message); }
  }
  const saved = store.get("musst.current", null);
  if (saved && saved.id) {
    try {
      const obs = await api(`/api/games/${saved.id}`, { token: saved.token });
      if (!obs.finished) {
        current = { ...saved, obs, seen: maxSeq(obs), help: false, discard: new Set(), amount: 2, busy: false };
        go("game");
        return;
      }
    } catch { store.set("musst.current", null); }
  }
  go("home");
}
boot();
