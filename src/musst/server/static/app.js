// MUS.ST — frontend sin dependencias. Solo renderiza observaciones y envía intenciones.
// La legalidad la decide siempre el motor (RulesEngine); aquí solo se ocultan botones.
// Dos backends con la misma API: el servidor FastAPI o, en GitHub Pages, el mismo Python
// ejecutándose en este navegador con Pyodide (worker.js). Lo decide <meta name="musst-backend">.

const $main = document.getElementById("main");
const $live = document.getElementById("live");
const $modal = document.getElementById("modal");
const $modalBody = document.getElementById("modal-body");

// ------------------------------------------------------------------ ajustes
const DEFAULT_SETTINGS = {
  theme: "auto", text_size: 1, reduce_motion: false, sound: true, speed: 1, table: "verde", card_back: "rayas",
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
  O: '<svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="11" fill="#d4a72c" stroke="#7a5a10" stroke-width="2"/><circle cx="16" cy="16" r="5" fill="none" stroke="#7a5a10" stroke-width="2"/></svg>',
  C: '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M8 6h16c0 8-3 12-8 12S8 14 8 6z" fill="#b8323f" stroke="#5e1018" stroke-width="2"/><path d="M16 18v6M11 27h10" stroke="#5e1018" stroke-width="2.5" stroke-linecap="round"/></svg>',
  E: '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 3l3 4v15h-6V7z" fill="#5a7da8" stroke="#1d3553" stroke-width="1.8"/><path d="M9 22h14M16 22v7" stroke="#1d3553" stroke-width="2.6" stroke-linecap="round"/></svg>',
  B: '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M12 28l2-22c1-3 5-3 6 0l-2 22z" fill="#5f8a3a" stroke="#2c4318" stroke-width="1.8"/><circle cx="17" cy="11" r="1.5" fill="#2c4318"/><circle cx="16" cy="17" r="1.5" fill="#2c4318"/></svg>',
};
function parseCard(code) { return { rank: Number(code.slice(0, -1)), suit: code.slice(-1) }; }
function cardLabel(code) {
  const { rank, suit } = parseCard(code);
  const names = { 1: "As", 2: "Dos", 3: "Tres", 4: "Cuatro", 5: "Cinco", 6: "Seis", 7: "Siete", 10: "Sota", 11: "Caballo", 12: "Rey" };
  const extra = rank === 3 ? " (cuenta como rey)" : rank === 2 ? " (cuenta como as)" : "";
  return `${names[rank]} de ${SUITS[suit].toLowerCase()}${extra}`;
}
function cardHTML(code, { small = false, button = false, pressed = false } = {}) {
  const { rank, suit } = parseCard(code);
  const tag = button ? "button" : "div";
  const equiv = rank === 3 ? '<span class="equiv">=R</span>' : rank === 2 ? '<span class="equiv">=A</span>' : "";
  const attrs = button ? ` type="button" data-card="${code}" aria-pressed="${pressed}"` : ' role="img"';
  return `<${tag} class="card${small ? " small" : ""}"${attrs} aria-label="${cardLabel(code)}">
    <span class="rank">${RANK_LABEL[rank] ?? rank}</span><span class="suit">${SUIT_SVG[suit]}</span>
    <span class="suit-name">${SUITS[suit]}</span>${equiv}</${tag}>`;
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
};
const SOUND_OF = {
  MusCut: "cut", BetPlaced: "bet", BetRaised: "bet", BetAccepted: "accept", OrdagoAccepted: "accept",
  BetRejected: "reject", OrdagoDeclared: "ordago", PointsAwarded: "points", GameFinished: "end", DealerAssigned: "deal",
};

// ------------------------------------------------------------------ navegación
const views = { home, learn, arena, stats, settings: settingsView, game: () => renderGame(), tutorial, training };
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
          <div class="form-grid">
            <label class="field">Rivales<select name="rivals"><option value="sencillo">Sencillo</option><option value="medio" selected>Medio</option><option value="profesional">Profesional</option></select></label>
            <label class="field">Compañero<select name="partner"><option value="sencillo">Bot sencillo</option><option value="medio">Bot medio</option><option value="profesional">Bot profesional</option>${LOCAL ? "" : '<option value="human">Humano (invitación)</option>'}</select></label>
            <label class="field">Tantos<select name="target"><option>40</option><option>30</option><option>20</option><option>60</option></select></label>
            <label class="field">Tu nombre<input name="name" maxlength="24" value="Tú"></label>
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
    startGame({
      mode: "personalizada", rivals: f.get("rivals"), partner: f.get("partner"), target: Number(f.get("target")),
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
      id: data.game_id, token: data.seat_token, obs: data.observation, seen: 0,
      help: Boolean(opts.help), discard: new Set(), amount: 2, busy: false,
    };
    current.seen = maxSeq(current.obs);
    store.set("musst.current", { id: current.id, token: current.token });
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

function renderGame(bubbles = {}) {
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
  const teamLabel = (t) => (obs.seats.some((s) => s.team === t && s.kind === "human") ? (t === myTeam ? "Tu pareja" : "Pareja rival") : t === myTeam ? "Tu pareja" : "Pareja bots");
  const scoreLine = (t) => {
    const pts = obs.score[t];
    const am = Math.floor(pts / 5), st = pts % 5;
    const left = obs.target - pts;
    return `<div class="score-line"><span class="team-dot" style="background:var(${t === 0 ? "--team-a" : "--team-b"})"></span>
      <span>${teamLabel(t)}${t === myTeam ? " (" + (t === 0 ? "A" : "B") + ")" : ""}</span>
      <span class="amarracos" aria-hidden="true">${'<span class="amarraco"></span>'.repeat(am)}${'<span class="piedra"></span>'.repeat(st)}</span>
      ${left > 0 && left <= 4 ? '<span class="dentro">dentro</span>' : ""}
      <strong aria-label="${pts} tantos">${pts}</strong></div>`;
  };
  const seatHTML = (s) => {
    const pos = seatPosition(s.seat, me);
    const decl = (k) => (obs.declarations[k] && obs.declarations[k][String(s.seat)] !== undefined
      ? `<span class="chip ${obs.declarations[k][String(s.seat)] ? "si" : "no"}">${k === "pares" ? "Pares" : "Juego"}: ${obs.declarations[k][String(s.seat)] ? "sí ✔" : "no ✘"}</span>` : "");
    const revealed = obs.revealed_hands && obs.revealed_hands[String(s.seat)];
    const cards = s.seat === me ? "" : revealed
      ? `<div class="hand">${revealed.map((c) => cardHTML(c, { small: true })).join("")}</div>`
      : `<div class="backs" role="img" aria-label="4 cartas ocultas">${'<span class="back"></span>'.repeat(4)}</div>`;
    const avatar = s.kind === "bot" ? "🤖" : esc(s.avatar || "🧑");
    const bubble = bubbles[s.seat] ? `<span class="bubble ${bubbles[s.seat] === "ÓRDAGO" ? "ordago" : ""}">${bubbles[s.seat]}</span>` : "";
    const status = s.waiting ? '<span class="chip">esperando…</span>' : !s.connected ? '<span class="chip">desconectado</span>' : "";
    return `<div class="seat ${pos} ${obs.turn === s.seat ? "turn" : ""}" style="--team-color:var(${s.team === 0 ? "--team-a" : "--team-b"})">
      ${bubble}<div class="avatar" aria-hidden="true">${avatar}</div>
      <div class="seat-name">${esc(s.name)}${s.seat === me ? " (tú)" : ""}${s.level ? ` <span class="chip">${esc(s.level)}</span>` : ""}</div>
      <div class="seat-meta"><span class="chip">${s.team === 0 ? "◆ Pareja A" : "● Pareja B"}</span>${obs.mano === s.seat ? '<span class="chip mano">mano</span>' : ""}${decl("pares")}${decl("juego")}${status}</div>
      ${pos === "bottom" ? "" : cards}</div>`;
  };
  const bet = obs.current_bet;
  const betInfo = bet ? (bet.is_ordago ? `Órdago de la pareja ${bet.bettor_team === 0 ? "A" : "B"}` : `En juego: ${bet.stake} tantos`) : "";
  const finished = obs.finished;
  const myTurn = obs.turn === me && !finished;
  $main.innerHTML = "";
  $main.append(h(`
  <div class="game">
    <h1 class="sr-only">Mesa de juego</h1>
    <div class="scorebar" role="region" aria-label="Marcador">
      <div><div class="lances" aria-label="Lances">${lanceBar}</div><small class="muted">Jugada ${obs.round} · a ${obs.target} tantos · ${current.obs.mode}</small></div>
      <div class="scores">${scoreLine(myTeam)}${scoreLine(1 - myTeam)}</div>
    </div>
    ${obs.invite ? `<div class="invite">Invita a tu compañero: comparte este enlace <code>${location.origin}${location.pathname}#join/${obs.game_id}/${obs.invite}</code></div>` : ""}
    <div class="table" role="region" aria-label="Mesa de Mus">
      ${obs.seats.filter((s) => s.seat !== me).map(seatHTML).join("")}
      <div class="center"><div><div class="lance-title">${esc(phaseName)}</div><div class="bet-info">${esc(betInfo)}</div>
        <div class="bet-info">${finished ? (obs.winner === myTeam ? "¡Habéis ganado!" : "Ha ganado la pareja rival") : myTurn ? "Te toca" : `Habla ${esc(names[obs.turn] ?? "")}`}</div></div></div>
      ${seatHTML(obs.seats[me])}
    </div>
    <div class="hand" id="my-hand" aria-label="Tus cartas">${obs.hand.map((c) => cardHTML(c, { button: obs.phase === "discard" && myTurn, pressed: current.discard.has(c) })).join("")}</div>
    <div class="status-line" id="status"></div>
    <div class="actions" id="actions" role="group" aria-label="Acciones disponibles"></div>
    <div class="row" style="justify-content:center">
      <button class="btn ghost" id="help-btn" aria-expanded="${current.help}">? ¿Qué puedo hacer?</button>
      ${finished ? '<button class="btn primary" id="summary-btn">Ver resumen</button>' : ""}
      <button class="btn ghost" id="log-btn">Historial de la jugada</button>
    </div>
    <div id="help" class="help-panel" ${current.help ? "" : "hidden"}></div>
  </div>`));
  renderActions();
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
  if (obs.finished || obs.turn !== obs.seat) return;
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
    const obs = await api(`/api/games/${current.id}/action`, { method: "POST", body: { action }, token: current.token });
    await animateTo(obs);
  } catch (err) {
    toast(err.message);
  } finally {
    current.busy = false;
  }
}

async function animateTo(obs) {
  const names = obs.seats.map((s) => s.name);
  const fresh = obs.history.filter((e) => e.seq > current.seen);
  const prevRound = current.obs.round;
  for (const e of fresh) {
    const bubble = BUBBLE[e.kind];
    if (SOUND_OF[e.kind]) play(SOUND_OF[e.kind]);
    const text = eventText(e, names);
    if (text) announce(text);
    if (bubble && e.round === prevRound && e.actor !== obs.seat) {
      setStatus(text);
      renderGame({ [e.actor]: bubble });
      await sleep(420);
    } else if (e.kind === "HandsRevealed" && e.round === prevRound) {
      setStatus("Se enseñan las cartas");
      await sleep(250);
    }
  }
  current.seen = maxSeq(obs);
  current.obs = obs;
  renderGame();
  const last = fresh.filter((e) => e.kind === "RoundFinished").pop();
  if (last) setStatus(`Fin de la jugada: ${last.payload.score[0]} – ${last.payload.score[1]}`);
  if (obs.finished) { store.set("musst.current", null); setTimeout(showSummary, 600); }
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
    <h1 class="page-title">Replay</h1>
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
      <div class="avatar">${s.kind === "bot" ? "🤖" : "🧑"}</div><div class="seat-name">${esc(s.name)}</div>
      ${hands ? `<div class="hand">${hands[String(s.seat)].map((c) => cardHTML(c, { small: true })).join("")}</div>` : '<div class="backs" role="img" aria-label="Mano no revelada">' + '<span class="back"></span>'.repeat(4) + "</div>"}</div>`).join("");
    document.getElementById("replay-table").innerHTML = seatsHTML +
      `<div class="center"><div><div class="lance-title">${esc(lance)}</div><div class="bet-info">A ${score[0]} – B ${score[1]}</div><div class="bet-info">${esc(cur ? eventText(cur, names) : "")}</div></div></div>`;
    const log = document.getElementById("r-log");
    log.innerHTML = upto.slice(-40).map((e, k, arr) => `<li class="${k === arr.length - 1 ? "now" : ""}">${esc(eventText(e, names))}</li>`).join("");
    log.lastElementChild?.scrollIntoView({ block: "nearest" });
  };
  const stop = () => { clearInterval(timer); timer = null; document.getElementById("r-play").textContent = "▶ REPRODUCIR"; };
  document.getElementById("r-first").onclick = () => { stop(); i = 0; draw(); };
  document.getElementById("r-last").onclick = () => { stop(); i = steps.length - 1; draw(); };
  document.getElementById("r-prev").onclick = () => { stop(); i = Math.max(0, i - 1); draw(); };
  document.getElementById("r-next").onclick = () => { stop(); i = Math.min(steps.length - 1, i + 1); draw(); };
  document.getElementById("r-play").onclick = (e) => {
    if (timer) { stop(); return; }
    e.target.textContent = "⏸ PAUSA";
    timer = setInterval(() => { if (i >= steps.length - 1) { stop(); return; } i += 1; draw(); }, 700 * settings.speed);
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
    </form></div></div>`));
  document.getElementById("sf").onchange = (e) => {
    const f = new FormData(e.currentTarget);
    settings = {
      ...settings, theme: f.get("theme"), text_size: Number(f.get("text_size")), speed: Number(f.get("speed")),
      table: f.get("table"), card_back: f.get("card_back"), reduce_motion: f.get("reduce_motion") === "on", sound: f.get("sound") === "on",
    };
    saveSettings();
  };
}

function loginDialog() {
  openModal(`<h2 id="modal-title">Entrar</h2>
    <form id="lf" class="stack">
      <label class="field">Usuario<input name="username" autocomplete="username" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_.\\-]+"></label>
      ${LOCAL ? `<p class="muted">Perfil local: tus partidas, estadísticas y lo que el bot aprende de ti se guardan solo en este navegador. No hace falta contraseña.</p>
      <div class="row"><button class="btn primary" value="login">Usar este perfil</button><button class="btn ghost" type="button" data-close>Cancelar</button></div>`
      : `<label class="field">Contraseña<input name="password" type="password" autocomplete="current-password" required minlength="8"></label>
      <p class="muted">Solo guardamos tu usuario y un hash de la contraseña. Nada más.</p>
      <div class="row"><button class="btn primary" value="login">Entrar</button><button class="btn" value="register">Crear cuenta</button><button class="btn ghost" type="button" data-close>Cancelar</button></div>`}
    </form>`);
  document.getElementById("lf").onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const kind = e.submitter?.value === "register" ? "register" : "login";
    try {
      await api(`/api/auth/${kind}`, { method: "POST", body: { username: f.get("username"), password: f.get("password") } });
      $modal.close();
      await loadUser();
      toast(kind === "register" ? "Cuenta creada" : `Hola, ${user ? user.username : ""}`);
      go("home");
    } catch (err) { toast(err.message); }
  };
}
function accountMenu() {
  openModal(`<h2 id="modal-title">${esc(user.username)}</h2><div class="row">
    <button class="btn" id="to-stats">Mis estadísticas</button><button class="btn" id="logout">Salir</button><button class="btn ghost" data-close>Cerrar</button></div>`);
  document.getElementById("to-stats").onclick = () => { $modal.close(); go("stats"); };
  document.getElementById("logout").onclick = async () => { await api("/api/auth/logout", { method: "POST" }); user = null; $modal.close(); updateAccount(); go("home"); };
}
function updateAccount() { document.getElementById("account").textContent = user ? user.username : "Entrar"; }
async function loadUser() {
  try { user = await api("/api/me"); } catch { user = null; }
  if (user && user.settings && Object.keys(user.settings).length) { settings = { ...settings, ...user.settings }; applySettings(); }
  updateAccount();
}

// ------------------------------------------------------------------ arranque
async function boot() {
  applySettings();
  if (LOCAL) {
    try { await startWorker(); } catch { return; }
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
