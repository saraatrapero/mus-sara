// MUS.ST — cuentas en Supabase (usuario + contraseña) para la versión de GitHub Pages.
//
// Python (Pyodide) sigue siendo el cerebro: juega, aprende y calcula. Este módulo solo:
//   · inicia sesión / registra en Supabase (Auth), con nombre de usuario en lugar de correo;
//   · al entrar, trae lo que la IA ya sabía del jugador y la autocrítica de los bots;
//   · al acabar una partida, guarda el resumen, el modelo del jugador y la autocrítica;
//   · da al administrador los datos del panel y las operaciones sobre usuarios (RPC con RLS).
//
// La clave "anon" es pública por diseño: la seguridad la ponen las políticas RLS de
// supabase/schema.sql.

const SUPABASE_JS = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/+esm";
const EMAIL_DOMAIN = "jugadores.mus-st.app"; // igual que public.username_email() en SQL
const USERNAME = /^[A-Za-z0-9_.-]{3,32}$/;

let client = null;
let profile = null;

export function usernameEmail(username) { return `${username.toLowerCase()}@${EMAIL_DOMAIN}`; }

export async function initCloud() {
  let config = null;
  try {
    const res = await fetch(new URL("cloud-config.json", import.meta.url));
    if (res.ok) config = await res.json();
  } catch { /* sin configuración: modo perfil local */ }
  if (!config || !config.url || !config.anonKey) return false;
  const { createClient } = await import(SUPABASE_JS);
  client = createClient(config.url, config.anonKey, { auth: { persistSession: true } });
  const { data } = await client.auth.getSession();
  if (data.session) await loadProfile();
  return true;
}

export const cloudEnabled = () => client !== null;
export const cloudProfile = () => profile;
export const isAdmin = () => profile?.role === "admin";

async function loadProfile() {
  const { data: auth } = await client.auth.getUser();
  if (!auth.user) { profile = null; return null; }
  const { data, error } = await client.from("profiles").select("*").eq("id", auth.user.id).single();
  if (error) throw new Error(error.message);
  profile = data;
  client.from("profiles").update({ last_seen: new Date().toISOString() }).eq("id", data.id).then(() => {});
  return profile;
}

function check(username, password) {
  if (!USERNAME.test(username || "")) throw new Error("Usuario: de 3 a 32 letras, números, punto, guion o guion bajo");
  if (!password || password.length < 8) throw new Error("La contraseña necesita al menos 8 caracteres");
}

export async function signIn(username, password) {
  check(username, password);
  const { error } = await client.auth.signInWithPassword({ email: usernameEmail(username), password });
  if (error) throw new Error("Usuario o contraseña incorrectos");
  return loadProfile();
}

export async function signUp(username, password) {
  check(username, password);
  const { error } = await client.auth.signUp({
    email: usernameEmail(username), password, options: { data: { username } },
  });
  if (error) throw new Error(error.message.includes("registered") ? "Ese nombre de usuario ya existe" : error.message);
  return loadProfile();
}

export async function signOut() { await client.auth.signOut(); profile = null; }

// ------------------------------------------------------------------ sincronización con la IA
export async function pullMemory() {
  const [model, memory] = await Promise.all([
    client.from("player_models").select("model").eq("user_id", profile.id).maybeSingle(),
    client.from("bot_memory").select("key,data"),
  ]);
  return { model: model.data?.model ?? null, bot_memory: Object.fromEntries((memory.data || []).map((r) => [r.key, r.data])) };
}

export async function pushGame(exported) {
  const { game, model, style, bot_memory } = exported;
  const ops = [
    client.from("games").upsert({ ...game, user_id: profile.id }),
    client.from("player_models").upsert({ user_id: profile.id, model, style, updated_at: new Date().toISOString() }),
    ...Object.entries(bot_memory || {}).map(([key, data]) =>
      client.from("bot_memory").upsert({ key, data, updated_by: profile.id, updated_at: new Date().toISOString() })),
  ];
  const results = await Promise.all(ops);
  const failed = results.find((r) => r.error);
  if (failed) throw new Error(failed.error.message);
}

export async function myGames() {
  const { data, error } = await client.from("games")
    .select("id,mode,rivals,won,score,reason,stats,created_at").eq("user_id", profile.id).order("created_at");
  if (error) throw new Error(error.message);
  return data;
}

// ------------------------------------------------------------------ administración
export async function adminData() {
  const [users, games, models, memory] = await Promise.all([
    client.from("profiles").select("*").order("created_at"),
    client.from("games").select("id,user_id,mode,rivals,partner,won,score,reason,stats,created_at").order("created_at"),
    client.from("player_models").select("user_id,model,style,updated_at"),
    client.from("bot_memory").select("key,data,updated_at"),
  ]);
  for (const r of [users, games, models, memory]) if (r.error) throw new Error(r.error.message);
  return { users: users.data, games: games.data, models: models.data, memory: memory.data };
}

async function rpc(name, args) {
  const { data, error } = await client.rpc(name, args);
  if (error) throw new Error(error.message);
  return data;
}
export const adminCreateUser = (username, password, role) => rpc("admin_create_user", { p_username: username, p_password: password, p_role: role });
export const adminUpdateUser = (id, { username = null, role = null, password = null }) =>
  rpc("admin_update_user", { p_id: id, p_username: username || null, p_role: role || null, p_password: password || null });
export const adminDeleteUser = (id) => rpc("admin_delete_user", { p_id: id });

// ------------------------------------------------------------------ publicidad
// La lee cualquiera (también sin sesión); solo la cambia un administrador (admin_set_ads valida).
export async function loadAds() {
  const { data, error } = await client.from("site_settings").select("value").eq("key", "ads").maybeSingle();
  if (error) throw new Error(error.message);
  return data?.value ?? null;
}
export const adminSetAds = (ads) => rpc("admin_set_ads", { p_ads: ads });

// ------------------------------------------------------------------ campeonatos
// Al consultarlos se empiezan los que ya han llegado a su fecha (champ_start_due).
export async function championships() {
  await rpc("champ_start_due", {});
  const { data, error } = await client.from("championships")
    .select("*, champ_teams(captain, partner)").order("starts_at", { ascending: false });
  if (error) throw new Error(error.message);
  return data;
}
export async function championship(id) {
  await rpc("champ_start_due", {});
  const [champ, teams, matches, players] = await Promise.all([
    client.from("championships").select("*").eq("id", id).single(),
    client.from("champ_teams").select("*").eq("championship_id", id).order("id"),
    client.from("champ_matches").select("*").eq("championship_id", id).order("round").order("slot"),
    client.rpc("champ_players", { p_champ: id }),
  ]);
  for (const r of [champ, teams, matches, players]) if (r.error) throw new Error(r.error.message);
  return { ...champ.data, teams: teams.data, matches: matches.data,
    names: Object.fromEntries(players.data.map((p) => [p.id, p.username])) };
}
export const champSignUp = (id, name, partnerOpen) => rpc("champ_sign_up", { p_champ: id, p_team_name: name, p_partner_open: partnerOpen });
export const champJoin = (teamId) => rpc("champ_join_team", { p_team: teamId });
export const champLeave = (id) => rpc("champ_leave", { p_champ: id });
export const champReport = (matchId, winner, score) => rpc("champ_report", { p_match: matchId, p_winner: winner, p_score: score });
export const adminCreateChampionship = ({ name, startsAt, size, target, signals }) =>
  rpc("admin_create_championship", { p_name: name, p_starts_at: startsAt, p_size: size, p_target: target, p_signals: signals });
export const adminStartChampionship = (id) => rpc("admin_start_championship", { p_champ: id });
export const adminDeleteChampionship = (id) => rpc("admin_delete_championship", { p_champ: id });
export const adminSetMatchWinner = (matchId, winner) => rpc("admin_set_match_winner", { p_match: matchId, p_winner: winner });
