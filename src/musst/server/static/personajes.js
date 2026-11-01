// MUS.ST — personajes de parodia que encarnan a los bots: caricaturas dibujadas y frases.
// Apodos inventados que recuerdan a tipos de la tele y del corazón, sin nombrar a nadie real
// (los mismos de la app de Render). El servidor reparte un personaje distinto a cada bot
// (musst/server/personajes.py); aquí está cómo se dibuja y qué dice cada uno.

export const AVISO =
  "Personajes de parodia con apodos inventados. Cualquier parecido con personas reales es una caricatura humorística sin relación con ellas.";

// Momentos de la partida → frases de cada personaje (si no tiene, habla como siempre).
export const MOMENTO = {
  MusRequested: "pide_mus", MusCut: "corta_mus", Passed: "pasa", BetPlaced: "envida", BetRaised: "envida",
  OrdagoDeclared: "ordago", BetAccepted: "acepta", OrdagoAccepted: "acepta", BetRejected: "rechaza",
};

export const PERSONAJES = {
  marquesa: {
    apodo: "La Marquesa", estilo: "conservadora", color: "#b5838d",
    frases: {
      corta_mus: ["Yo con esto no me levanto de la silla.", "Corto, que tengo una merienda."],
      pasa: ["Ay, no, qué horror, eso no se envida.", "Paso, querida, paso."],
      envida: ["Que una tiene un nombre que cuidar.", "Pero con mucha clase."],
      ordago: ["Y que conste que no es lo mío."],
      rechaza: ["Gracias. Muy amable."],
      gana_lance: ["Lo sabía, la elegancia siempre gana."],
      pierde_lance: ["Esto en palacio no pasaba."],
      gana_partida: ["Qué partida tan divina."],
      pierde_partida: ["Me voy a tomar un té, que lo necesito."],
    },
  },
  tentador: {
    apodo: "El Tentador", estilo: "farolero", color: "#e07a5f",
    frases: {
      pide_mus: ["¿Te atreves?"],
      envida: ["¿Quieres o no quieres? Mírame a los ojos.", "Y no te digo más."],
      ordago: ["Lo que pasa en esta mesa, se queda en esta mesa."],
      acepta: ["Me gustan los retos."],
      gana_lance: ["Nunca enseñes las cartas a la primera cita."],
      pierde_lance: ["Me habéis pillado, pero qué bien lo he pasado."],
      gana_partida: ["Ya os dije que era irresistible."],
      pierde_partida: ["Mañana me tocará a mí."],
    },
  },
  superviviente: {
    apodo: "La Superviviente", estilo: "arriesgada", color: "#81b29a",
    frases: {
      envida: ["Que aquí se viene a sobrevivir."],
      ordago: ["¡De peores islas he salido!"],
      acepta: ["Con hambre se juega mejor."],
      gana_lance: ["¡Otra prueba de recompensa para mí!"],
      pierde_lance: ["Me voy a la palapa a pensar."],
      gana_partida: ["¡Sobreviví!"],
      pierde_partida: ["Me nominan, pero vuelvo."],
    },
  },
  tronista: {
    apodo: "El Tronista", estilo: "imprevisible", color: "#3d405b",
    frases: {
      pide_mus: ["Depende de cómo me mires."],
      corta_mus: ["Hoy vengo a por todas… o a por ninguna."],
      envida: ["Por la cara."],
      gana_lance: ["Ya sabía yo que esta mano tenía química."],
      pierde_lance: ["No era mi tipo de carta."],
      gana_partida: ["Elijo… ¡la victoria!"],
      pierde_partida: ["Me voy sin elegir a nadie."],
    },
  },
  abuela: {
    apodo: "La Abuela del Mus", estilo: "equilibrada", color: "#f2cc8f",
    frases: {
      revela_31: ["Treinta y una, como Dios manda."],
      rechaza: ["Eso lo has echado con el corazón, no con la cabeza."],
      pasa: ["Paso, hijo, que tengo paciencia."],
      gana_lance: ["La veteranía es un grado."],
      pierde_lance: ["Bueno, alguna te tenía que dejar."],
      gana_partida: ["Esto ya lo jugaba yo de jovencita."],
      pierde_partida: ["Muy bien, cariño, así se aprende."],
    },
  },
  verbena: {
    apodo: "El de la Verbena", estilo: "agresivo", color: "#f4a261",
    frases: {
      envida: ["¡Que suene la orquesta!"],
      ordago: ["¡Y todos a bailar!"],
      gana_lance: ["Esta mano ha sido un temazo."],
      pierde_lance: ["Me he desafinado un poco."],
      gana_partida: ["¡Y otra, y otra, y otra!"],
      pierde_partida: ["Se acabó la verbena."],
    },
  },
  presentador: {
    apodo: "El Presentador", estilo: "cauto", color: "#2a9d8f",
    frases: {
      pide_mus: ["Y en el próximo lance… ¡sorpresa!"],
      pasa: ["Lo dejamos aquí, nos vemos después de la publicidad."],
      gana_lance: ["Ha sido una gala inolvidable."],
      pierde_lance: ["Queda expulsado… pero solo de este lance."],
      gana_partida: ["¡Y el ganador de esta edición es…!"],
      pierde_partida: ["Gracias por vernos, buenas noches."],
    },
  },
  influencer: {
    apodo: "La Influencer", estilo: "experta en señas", color: "#c77dff",
    frases: {
      corta_mus: ["Que se me enfría el café."],
      revela_31: ["Hashtag treinta y una."],
      gana_lance: ["Esto lo subo a stories."],
      pierde_lance: ["Esta mano no sale en mis fotos."],
      gana_partida: ["Hoy tengo el algoritmo de cara."],
      pierde_partida: ["Me desconecto un ratito."],
    },
  },
};

// Elige una frase de forma estable (la misma para el mismo evento).
export function frase(id, momento, n = 0) {
  const opts = PERSONAJES[id]?.frases[momento];
  return opts && opts.length ? opts[Math.abs(n) % opts.length] : null;
}

// ------------------------------------------------------------------ caricaturas
// Cabeza grande y rasgos exagerados (caricatura), en el mismo lienzo de 64×64 que las caras
// de siempre. ``g`` trae lo que decide la mesa: ojos (con la mirada), cejas, boca de la seña,
// inclinación de la cabeza y hombros. Cada personaje pone pelo, ropa y su complemento.
const SKIN = {
  marquesa: "#f6d7c3", tentador: "#d9a07a", superviviente: "#c68a5e", tronista: "#b9733f",
  abuela: "#f3d2bd", verbena: "#e8b48a", presentador: "#f0c8a0", influencer: "#f1c7a8",
};
const BROW = {
  marquesa: "#9c8455", tentador: "#1b120c", superviviente: "#4a2f1c", tronista: "#120c08",
  abuela: "#8f8f8f", verbena: "#130d0a", presentador: "#5a3b24", influencer: "#3a2418",
};

// Boca por defecto de cada uno (si no está haciendo una seña con la boca).
const MOUTH = {
  marquesa: '<path d="M27.5 44.5q4.5 2.2 9 0q-4.5 1-9 0z" fill="#c2185b"/><path d="M27.5 44.5q4.5-1.4 9 0" stroke="#a3154d" stroke-width="1.2" fill="none"/>',
  tentador: '<path d="M27 44q6 2.5 11-1.5" stroke="#5a1e1e" stroke-width="2" fill="none" stroke-linecap="round"/>',
  superviviente: '<path d="M26 43q6 6 12 0z" fill="#5a1e1e"/><path d="M27 43.3h10" stroke="#fff" stroke-width="2"/>',
  tronista: '<path d="M25 42.5q7 7 14 0z" fill="#fff" stroke="#5a1e1e" stroke-width="1.2"/><path d="M27 44h10" stroke="#ddd" stroke-width=".8"/>',
  abuela: '<path d="M27.5 44q4.5 3 9 0" stroke="#7a2a2a" stroke-width="1.8" fill="none" stroke-linecap="round"/>',
  verbena: '<path d="M26 43q6 6.5 12 0z" fill="#5a1e1e"/><ellipse cx="32" cy="46.5" rx="3" ry="1.4" fill="#e46b7a"/>',
  presentador: '<path d="M24.5 42q7.5 8 15 0z" fill="#fff" stroke="#5a1e1e" stroke-width="1.2"/><path d="M26 43.5h12M29 42.4v3.4M32 42.4v4M35 42.4v3.4" stroke="#ddd" stroke-width=".7"/>',
  influencer: '<path d="M27.5 43.6q4.5 4 9 0q-2.2-1.4-4.5-.4q-2.3-1-4.5.4z" fill="#ff5d8f"/>',
};

const BACK = {
  // Lo que va detrás de la cabeza (pelo largo, aro de luz, palmera…).
  marquesa: '<path d="M11 33q-3-21 21-23t21 23q2 7-3 9 1-9-3-14-6-5-15-5t-15 5q-4 5-3 14-5-2-3-9z" fill="#e5d3a1"/>',
  tentador: "",
  superviviente: '<path d="M50 14q8 0 12 6-6-2-9 1 6 1 8 6-6-3-10-1z" fill="#3f8a4c"/><path d="M50 14q2 12-1 24" stroke="#6b4a2a" stroke-width="2" fill="none"/>',
  tronista: "",
  abuela: "",
  verbena: "",
  presentador: "",
  influencer: '<circle cx="32" cy="30" r="27" fill="none" stroke="#fff6c8" stroke-width="3" opacity=".9"/><path d="M14 30q-2-20 18-21t18 21l2 20-6-4-1-14q-3-9-13-9t-13 9l-1 14-6 4z" fill="#5b3a29"/><path d="M17 36q-1 8 1 14M47 36q1 8-1 14" stroke="#ff8fab" stroke-width="2.4" fill="none"/>',
};

const BODY = {
  marquesa: (c) => `<path d="M8 64q3-13 16-15h16q13 2 16 15z" fill="${c}"/><path d="M24 50q8 6 16 0" stroke="#fff" stroke-width="1.4" fill="none" stroke-dasharray="1.6 1.4"/>${[24, 27, 30, 33, 36, 39].map((x, i) => `<circle cx="${x + 0.5}" cy="${50.5 + (i === 0 || i === 5 ? 0 : i === 1 || i === 4 ? 1.4 : 2.1)}" r="1.3" fill="#fffaf0" stroke="#d8cdb8" stroke-width=".3"/>`).join("")}`,
  tentador: (c) => `<path d="M7 64q3-13 16-15h18q13 2 16 15z" fill="${c}"/><path d="M26 49l6 11 6-11z" fill="#d9a07a"/><path d="M26 49l-3 6 5-1zM38 49l3 6-5-1z" fill="#fff"/><path d="M28 53q4 4 8 0" stroke="#e8b923" stroke-width="1.2" fill="none"/><circle cx="32" cy="56.4" r="1.4" fill="#e8b923"/>`,
  superviviente: (c) => `<path d="M9 64q3-12 14-14h18q11 2 14 14z" fill="#c68a5e"/><path d="M15 64q1-9 7-12h20q6 3 7 12z" fill="${c}"/><path d="M20 53l2 11M44 53l-2 11" stroke="#5c8f74" stroke-width="1"/>`,
  tronista: (c) => `<path d="M5 64q2-13 17-16h20q15 3 17 16z" fill="#b9733f"/><path d="M17 64q0-9 6-13h18q6 4 6 13z" fill="${c}"/><path d="M14 56q3-3 6-2M50 56q-3-3-6-2" stroke="#8a5428" stroke-width="1" fill="none"/>`,
  abuela: (c) => `<path d="M8 64q3-13 16-15h16q13 2 16 15z" fill="${c}"/><path d="M32 50v14" stroke="#c9a05f" stroke-width="1"/>${[53, 57, 61].map((y) => `<circle cx="34" cy="${y}" r="1" fill="#8a6a3a"/>`).join("")}<path d="M24 49q8 5 16 0" stroke="#fff" stroke-width="2.2" fill="none"/>`,
  verbena: (c) => `<path d="M6 64q3-14 17-16h18q14 2 17 16z" fill="${c}"/>${[[14, 58], [20, 54], [44, 54], [50, 58], [17, 62], [47, 62], [24, 60], [40, 60]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r=".9" fill="#fff7c2"/>`).join("")}<path d="M27 48l5 9 5-9z" fill="#fff"/><path d="M29 49q3 2 6 0" stroke="#111" stroke-width="1.4" fill="none"/>`,
  presentador: (c) => `<path d="M7 64q3-13 16-15h18q13 2 16 15z" fill="${c}"/><path d="M26 49l6 12 6-12z" fill="#fff"/><path d="M28.5 51.5l3.5 1.6 3.5-1.6v3.2l-3.5-1.6-3.5 1.6z" fill="#d62828"/><path d="M26 49l-3 8 6-2zM38 49l3 8-6-2z" fill="#1f6f66"/>`,
  influencer: (c) => `<path d="M9 64q3-12 15-14h16q12 2 15 14z" fill="${c}"/><rect x="44" y="47" width="8" height="13" rx="1.6" fill="#222" transform="rotate(12 48 53)"/><path d="M47.3 52.3q.9-1 1.8 0q.9-1 1.8 0q0 1.5-1.8 2.6q-1.8-1.1-1.8-2.6z" fill="#ff5d8f" transform="rotate(12 48 53)"/>`,
};

const FRONT = {
  // Pelo y complementos por delante de la cara.
  marquesa: '<path d="M16 26q1-15 16-15t16 15q-5-8-16-8t-16 8z" fill="#efe0b4"/><path d="M22 12l3-5 3 4 4-6 4 6 3-4 3 5z" fill="#e8b923" stroke="#b48a12" stroke-width=".6"/><circle cx="32" cy="7.5" r="1.4" fill="#4fc3f7"/><circle cx="16.6" cy="38" r="1.6" fill="#fffaf0"/><circle cx="47.4" cy="38" r="1.6" fill="#fffaf0"/>',
  // Barba de tres días: sombra en la mandíbula, por debajo de la boca.
  tentador: '<path d="M18 37q2 9 9 11.5q5 1.6 10 0q7-2.5 9-11.5q-2 6-8 7.5q-6 1.4-12 0q-6-1.5-8-7.5z" fill="#3a2418" opacity=".28"/><path d="M16 27q-1-12 10-15q10-4 18 2q5 4 4 13q-3-7-9-8-8-1-14 1-6 2-9 7z" fill="#1b120c"/><path d="M26 13q4-6 12-3" stroke="#3a2a1d" stroke-width="1.5" fill="none"/>',
  superviviente: '<path d="M17 27q-2-14 15-15t15 15q-2-4-4-2 0-4-4-3-1-3-4-1-3-3-5 0-3-2-5 1-3-1-4 3-2-2-4 2z" fill="#6b4226"/><path d="M16.5 22q15.5-6 31 0v4q-15.5-5-31 0z" fill="#d62828"/><path d="M47 23l5 4-4 1z" fill="#d62828"/><ellipse cx="41" cy="38" rx="2.4" ry="1.3" fill="#7a5233" opacity=".55"/>' +
    [[23, 35], [25, 37], [39, 35]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r=".6" fill="#7a4a2a"/>`).join(""),
  tronista: '<path d="M17 25l2-11 3 6 3-9 3 7 4-9 3 8 4-7 2 8 3-5 1 12q-15-6-28 0z" fill="#120c08"/><path d="M24 12l1 5M36 11l-1 6" stroke="#c8a165" stroke-width="1.2"/><rect x="19" y="17.5" width="11" height="5" rx="2" fill="#222"/><rect x="34" y="17.5" width="11" height="5" rx="2" fill="#222"/><path d="M30 19.5h4" stroke="#222" stroke-width="1.4"/><circle cx="16.8" cy="38.5" r="1.3" fill="none" stroke="#e8b923" stroke-width="1"/>',
  abuela: '<path d="M16 29q0-17 16-17t16 17q-3-10-16-10t-16 10z" fill="#d9d9d9"/><circle cx="32" cy="10" r="5.5" fill="#cfcfcf"/><path d="M27 10q5-3 10 0" stroke="#b8b8b8" stroke-width="1" fill="none"/>' +
    '<circle cx="26" cy="30" r="5.4" fill="none" stroke="#7b5a3a" stroke-width="1.5"/><circle cx="38" cy="30" r="5.4" fill="none" stroke="#7b5a3a" stroke-width="1.5"/><path d="M31.4 30h1.2" stroke="#7b5a3a" stroke-width="1.5"/><circle cx="16.6" cy="38" r="1.5" fill="#fffaf0"/><circle cx="47.4" cy="38" r="1.5" fill="#fffaf0"/>',
  verbena: '<path d="M16 27q-2-13 8-17 10-5 20 0 6 3 4 10l-1 6q-3-9-15-9-11 0-16 10z" fill="#130d0a"/><path d="M22 9q10-6 22 2" stroke="#3a2a1d" stroke-width="1.6" fill="none"/><path d="M17 27v9l2-1v-7zM47 27v9l-2-1v-7z" fill="#130d0a"/><path d="M26 41.5q6-2 12 0q-6-1-12 0z" stroke="#130d0a" stroke-width="1.6" fill="none"/>' +
    '<g transform="rotate(-25 13 46)"><rect x="11" y="44" width="4" height="14" rx="1.5" fill="#333"/><circle cx="13" cy="43" r="3.4" fill="#9a9a9a"/></g>',
  presentador: '<path d="M17 27q-1-14 15-15t15 15q-3-7-9-7-1-2-4 0-9-1-17 7z" fill="#5a3b24"/><path d="M17.5 27q-.5-3 .8-6M46.5 27q.5-3-.8-6" stroke="#b9b2a8" stroke-width="2"/><path d="M33 13q-3 4-1 8" stroke="#3e2816" stroke-width="1" fill="none"/>',
  influencer: '<path d="M16 28q-1-16 16-16t16 16q-3-9-9-10-4 6-15 6-5 0-8 4z" fill="#5b3a29"/><path d="M36 12q5 2 6 8" stroke="#ff8fab" stroke-width="2" fill="none"/>' +
    '<path d="M21 14.5q2-3 4.5-.6q2.5-2.4 4.5.6q0 3-4.5 5q-4.5-2-4.5-5z" fill="#ff5d8f" stroke="#222" stroke-width=".6"/><path d="M34 14.5q2-3 4.5-.6q2.5-2.4 4.5.6q0 3-4.5 5q-4.5-2-4.5-5z" fill="#ff5d8f" stroke="#222" stroke-width=".6"/><path d="M30 15.5h4" stroke="#222" stroke-width="1"/>',
};

const EXTRA_FACE = {
  // Detalles de la cara (mejillas, pestañas, lunar…).
  marquesa: '<circle cx="22" cy="37" r="2.6" fill="#f28b9b" opacity=".55"/><circle cx="42" cy="37" r="2.6" fill="#f28b9b" opacity=".55"/><circle cx="40" cy="41" r=".8" fill="#4a2c2a"/>',
  tentador: "",
  superviviente: "",
  tronista: '<path d="M29.5 36.5q2.5 1.6 5 0" stroke="#8a5428" stroke-width="1" fill="none"/>',
  abuela: '<circle cx="21.5" cy="38" r="2.8" fill="#f28b9b" opacity=".6"/><circle cx="42.5" cy="38" r="2.8" fill="#f28b9b" opacity=".6"/><path d="M22 41q1 1.5 0 3M42 41q-1 1.5 0 3" stroke="#d9a58f" stroke-width=".8" fill="none"/>',
  verbena: "",
  presentador: '<circle cx="22" cy="37" r="2.2" fill="#f2a08b" opacity=".45"/><circle cx="42" cy="37" r="2.2" fill="#f2a08b" opacity=".45"/>',
  influencer: '<path d="M21 26.5l-2-1.6M43 26.5l2-1.6M21.6 27.7l-2.3-.7M42.4 27.7l2.3-.7" stroke="#222" stroke-width=".8"/><circle cx="22" cy="37" r="2.2" fill="#ff9fb8" opacity=".5"/><circle cx="42" cy="37" r="2.2" fill="#ff9fb8" opacity=".5"/>',
};

const NOSE = {
  marquesa: '<path d="M32 30q-1 6 1 8" stroke="#d9a58f" stroke-width="1.4" fill="none"/>',
  tentador: '<path d="M32 29q-3 7 0 9q2 1 3-1" stroke="#a8724e" stroke-width="1.5" fill="none"/>',
  superviviente: '<path d="M32 30q-2 6 0 8q2 .5 2.5-1" stroke="#9a6640" stroke-width="1.4" fill="none"/>',
  tronista: '<path d="M32 29q-3 7-1 9q3 1 4-1" stroke="#8a5428" stroke-width="1.5" fill="none"/>',
  abuela: '<ellipse cx="32" cy="36" rx="2.6" ry="2" fill="#eab8a1"/>',
  verbena: '<path d="M32 29q-4 8-1 10q3 1 4.5-1.5" stroke="#b8805a" stroke-width="1.6" fill="none"/>',
  presentador: '<path d="M32 30q-2 6 0 8" stroke="#cf9e78" stroke-width="1.4" fill="none"/>',
  influencer: '<path d="M32 31q-1 4.5 1 6" stroke="#d9a58f" stroke-width="1.2" fill="none"/>',
};

export function caricatureSVG(id, g) {
  const skin = SKIN[id];
  const body = BODY[id](PERSONAJES[id].color);
  const brow = (y) => `<path d="M21.5 ${y}q4.5-2 9 0M33.5 ${y}q4.5-2 9 0" stroke="${BROW[id]}" stroke-width="${id === "tentador" || id === "verbena" ? 2.6 : 1.8}" fill="none" stroke-linecap="round"/>`;
  return `<svg class="face caricature ${g.gesture ? "gesturing" : ""}" viewBox="0 0 64 64" aria-hidden="true">
    <rect width="64" height="64" fill="${PERSONAJES[id].color}" opacity=".18"/>
    ${BACK[id]}
    <g transform="translate(0 ${g.shoulders || 0})">${body}</g>
    <g transform="${g.tilt}">
      <rect x="28" y="44" width="8" height="7" fill="${skin}"/>
      <ellipse cx="32" cy="31" rx="15.5" ry="16.5" fill="${skin}"/>
      <ellipse cx="16.8" cy="32" rx="2.2" ry="3.4" fill="${skin}"/><ellipse cx="47.2" cy="32" rx="2.2" ry="3.4" fill="${skin}"/>
      ${EXTRA_FACE[id]}${brow(g.browY)}${g.eyes}${NOSE[id]}${g.mouth || MOUTH[id]}${FRONT[id]}
    </g></svg>`;
}
