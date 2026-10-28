// MUS.ST — publicidad en la mesa: reverso de las cartas de los bots y consumición junto a
// cada jugador. La elige un administrador (panel Admin → Publicidad) y se guarda en Supabase
// (tabla site_settings, clave "ads"); sin cuentas en la nube se usa DEFAULT_ADS.

export const DRINKS = { cerveza: "🍺 Cerveza", refresco: "🥤 Refresco", cafe: "☕ Café", agua: "💧 Agua", ninguna: "Ninguna" };

export const DEFAULT_ADS = {
  card_brand: "MUS.ST", card_color: "#7a1f2b", card_image: null,
  drink: "cerveza", drink_brand: "", drink_color: "#c8102e", drink_image: null,
};

const HEX = /^#[0-9a-fA-F]{6}$/;
const IMAGE = /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/;
export const MAX_IMAGE = 400_000; // caracteres del data URL (unos 290 KB de imagen)

// Valida lo que viene de la base de datos o del formulario (lo mismo que comprueba SQL).
export function cleanAds(raw) {
  const a = { ...DEFAULT_ADS, ...(raw || {}) };
  const text = (v, max) => String(v ?? "").trim().slice(0, max);
  const img = (v) => (typeof v === "string" && v.length <= MAX_IMAGE && IMAGE.test(v) ? v : null);
  return {
    card_brand: text(a.card_brand, 24) || DEFAULT_ADS.card_brand,
    card_color: HEX.test(a.card_color) ? a.card_color : DEFAULT_ADS.card_color,
    card_image: img(a.card_image),
    drink: a.drink in DRINKS ? a.drink : DEFAULT_ADS.drink,
    drink_brand: text(a.drink_brand, 24),
    drink_color: HEX.test(a.drink_color) ? a.drink_color : DEFAULT_ADS.drink_color,
    drink_image: img(a.drink_image),
  };
}

const escAttr = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// Reverso: color del patrocinador, rayas, y su marca (o su logo) en el centro.
export function backSVG(ads, cls = "bcard") {
  const a = cleanAds(ads);
  const center = a.card_image
    ? `<rect x="26" y="88" width="148" height="124" rx="12" fill="#fffdf6" stroke="#e8b923" stroke-width="4"/>
       <image href="${escAttr(a.card_image)}" x="32" y="94" width="136" height="112" preserveAspectRatio="xMidYMid meet"/>`
    : `<ellipse cx="100" cy="150" rx="78" ry="40" fill="${a.card_color}" stroke="#e8b923" stroke-width="4"/>
       <text x="100" y="${150 + Math.round(fontFor(a.card_brand) * 0.35)}" text-anchor="middle" font-family="Georgia, serif" font-weight="800" font-size="${fontFor(a.card_brand)}" fill="#e8b923">${escAttr(a.card_brand)}</text>`;
  const stripes = [0, 1, 2, 3, 4, 5].map((i) => `<path d="M16,${40 + i * 44} L184,${18 + i * 44}" stroke="#fff" stroke-opacity=".14" stroke-width="10"/>`).join("");
  return `<svg class="${cls}" viewBox="0 0 200 300" role="img" aria-label="Carta boca abajo de ${escAttr(a.card_brand)}">
    <rect x="3" y="3" width="194" height="294" rx="16" fill="${a.card_color}" stroke="#fff4dd" stroke-width="6"/>
    <rect x="16" y="16" width="168" height="268" rx="10" fill="none" stroke="#e8b923" stroke-width="3"/>${stripes}${center}</svg>`;
}

function fontFor(text) { return Math.max(14, Math.min(30, Math.floor(260 / Math.max(text.length, 1)))); }

// Consumición: cerveza, refresco, café o agua con la marca (o el logo) en la etiqueta.
export function drinkSVG(ads) {
  const a = cleanAds(ads);
  if (a.drink === "ninguna") return "";
  const label = (x, y, w, h, rotate = false) => {
    if (a.drink_image) return `<image href="${escAttr(a.drink_image)}" x="${x}" y="${y}" width="${w}" height="${h}" preserveAspectRatio="xMidYMid meet"/>`;
    if (!a.drink_brand) return "";
    const size = Math.max(6, Math.min(12, Math.floor(((rotate ? h : w) * 1.6) / a.drink_brand.length)));
    const cx = x + w / 2, cy = y + h / 2;
    return `<text x="${cx}" y="${cy + size * 0.35}" text-anchor="middle" font-family="system-ui, sans-serif" font-weight="800" font-size="${size}" fill="#fff"${rotate ? ` transform="rotate(-90 ${cx} ${cy})"` : ""}>${escAttr(a.drink_brand)}</text>`;
  };
  const c = a.drink_color;
  const body = {
    cerveza: `<path d="M10,22 L50,22 L46,94 L14,94 Z" fill="#f2a516" stroke="#fff" stroke-opacity=".7" stroke-width="2"/>
      <path d="M8,24 C6,12 18,8 24,12 C28,4 40,6 42,12 C50,8 56,16 52,24 Z" fill="#fffbea"/>
      <circle cx="22" cy="48" r="1.6" fill="#fff6c8"/><circle cx="38" cy="84" r="1.6" fill="#fff6c8"/>
      <rect x="15" y="54" width="30" height="22" rx="3" fill="${c}"/>${label(16, 55, 28, 20)}`,
    refresco: `<rect x="12" y="12" width="36" height="84" rx="8" fill="${c}" stroke="#fff" stroke-opacity=".5" stroke-width="2"/>
      <rect x="14" y="8" width="32" height="8" rx="3" fill="#c9c9c9"/><rect x="16" y="20" width="6" height="70" rx="3" fill="#fff" opacity=".18"/>${label(18, 22, 24, 66, true)}`,
    cafe: `<path d="M10,52 L44,52 L40,86 L14,86 Z" fill="#fffdf6" stroke="#6b4a2a" stroke-width="2"/>
      <path d="M44,58 C56,58 56,76 42,76" fill="none" stroke="#fffdf6" stroke-width="4"/>
      <ellipse cx="27" cy="53" rx="16" ry="3" fill="#5a3418"/><ellipse cx="28" cy="90" rx="26" ry="5" fill="#fffdf6" stroke="#6b4a2a"/>
      <rect x="15" y="62" width="24" height="16" rx="2" fill="${c}"/>${label(15, 62, 24, 16)}`,
    agua: `<path d="M24,4 L36,4 L36,16 C48,24 48,30 48,40 L48,94 L12,94 L12,40 C12,30 12,24 24,16 Z" fill="#cfe9ff" fill-opacity=".85" stroke="#fff" stroke-width="2"/>
      <rect x="22" y="0" width="16" height="6" rx="2" fill="${c}"/><rect x="12" y="50" width="36" height="26" fill="${c}"/>${label(13, 51, 34, 24)}`,
  }[a.drink];
  return `<svg class="drink" viewBox="0 0 60 100" role="img" aria-label="${a.drink === "cafe" ? "café" : a.drink}${a.drink_brand ? ` ${escAttr(a.drink_brand)}` : ""}">${body}</svg>`;
}
