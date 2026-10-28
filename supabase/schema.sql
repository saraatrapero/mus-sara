-- MUS.ST · Esquema de Supabase (cuentas, partidas, modelos de jugador y panel de administración)
--
-- Cómo aplicarlo: Supabase → SQL Editor → pegar este fichero → Run. Es idempotente.
-- Después, convertir la primera cuenta en administradora:
--     update public.profiles set role = 'admin' where username = 'TU_USUARIO';
--
-- Seguridad: todas las tablas tienen RLS. Un jugador solo ve y escribe lo suyo; un administrador
-- lo ve todo. Las operaciones de administración sobre usuarios pasan por funciones
-- SECURITY DEFINER que comprueban `is_admin()` antes de hacer nada.

create extension if not exists pgcrypto with schema extensions;

-- ---------------------------------------------------------------- perfiles
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  username text unique not null check (username ~ '^[A-Za-z0-9_.-]{3,32}$'),
  role text not null default 'player' check (role in ('player', 'admin')),
  avatar text,
  settings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  last_seen timestamptz
);

-- Partidas terminadas (resumen + historial público para el replay).
create table if not exists public.games (
  id text primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  mode text not null,
  rivals text,
  partner text,
  won boolean not null,
  score int[] not null,
  reason text,
  stats jsonb not null default '{}'::jsonb,
  history jsonb,
  created_at timestamptz not null default now()
);
create index if not exists games_user_idx on public.games (user_id, created_at desc);

-- Lo que la IA ha aprendido de cada jugador (PlayerModel serializado).
create table if not exists public.player_models (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  model jsonb not null,
  style text,
  updated_at timestamptz not null default now()
);

-- Memoria compartida de los bots (autocrítica de cada nivel).
create table if not exists public.bot_memory (
  key text primary key check (key ~ '^self:[a-z]+$'),
  data jsonb not null,
  updated_by uuid references public.profiles (id) on delete set null,
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- utilidades
create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles where id = auth.uid() and role = 'admin');
$$;

-- Al registrarse, se crea el perfil con el nombre de usuario de los metadatos.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, username)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'username', split_part(new.email, '@', 1)))
  on conflict (id) do nothing;
  return new;
end;
$$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Un jugador no puede ascenderse a administrador. (Sin sesión, p. ej. desde el editor SQL de
-- Supabase, sí se puede: así se crea el primer administrador.)
create or replace function public.protect_role() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.role is distinct from old.role and auth.uid() is not null and not public.is_admin() then
    raise exception 'Solo un administrador puede cambiar roles';
  end if;
  return new;
end;
$$;
drop trigger if exists profiles_protect_role on public.profiles;
create trigger profiles_protect_role before update on public.profiles
  for each row execute function public.protect_role();

-- ---------------------------------------------------------------- RLS
alter table public.profiles enable row level security;
alter table public.games enable row level security;
alter table public.player_models enable row level security;
alter table public.bot_memory enable row level security;

drop policy if exists profiles_read on public.profiles;
create policy profiles_read on public.profiles for select
  using (id = auth.uid() or public.is_admin());
drop policy if exists profiles_update on public.profiles;
create policy profiles_update on public.profiles for update
  using (id = auth.uid() or public.is_admin()) with check (id = auth.uid() or public.is_admin());
drop policy if exists profiles_delete on public.profiles;
create policy profiles_delete on public.profiles for delete using (public.is_admin());

drop policy if exists games_read on public.games;
create policy games_read on public.games for select using (user_id = auth.uid() or public.is_admin());
drop policy if exists games_insert on public.games;
create policy games_insert on public.games for insert with check (user_id = auth.uid());
drop policy if exists games_delete on public.games;
create policy games_delete on public.games for delete using (public.is_admin());

drop policy if exists models_read on public.player_models;
create policy models_read on public.player_models for select
  using (user_id = auth.uid() or public.is_admin());
drop policy if exists models_write on public.player_models;
create policy models_write on public.player_models for insert with check (user_id = auth.uid());
drop policy if exists models_update on public.player_models;
create policy models_update on public.player_models for update
  using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists memory_read on public.bot_memory;
create policy memory_read on public.bot_memory for select using (auth.uid() is not null);
drop policy if exists memory_insert on public.bot_memory;
create policy memory_insert on public.bot_memory for insert with check (updated_by = auth.uid());
drop policy if exists memory_update on public.bot_memory;
create policy memory_update on public.bot_memory for update
  using (auth.uid() is not null) with check (updated_by = auth.uid());

-- ---------------------------------------------------------------- administración
-- Correo interno: Supabase identifica por correo; MUS.ST usa nombre de usuario.
create or replace function public.username_email(p_username text) returns text
language sql immutable as $$ select lower(p_username) || '@jugadores.mus-st.app' $$;

create or replace function public.admin_create_user(p_username text, p_password text, p_role text default 'player')
returns uuid language plpgsql security definer set search_path = public, extensions as $$
declare
  new_id uuid := gen_random_uuid();
  mail text := public.username_email(p_username);
begin
  if not public.is_admin() then raise exception 'Solo administradores'; end if;
  if p_username !~ '^[A-Za-z0-9_.-]{3,32}$' then raise exception 'Nombre de usuario no válido'; end if;
  if length(p_password) < 8 then raise exception 'La contraseña necesita al menos 8 caracteres'; end if;
  if p_role not in ('player', 'admin') then raise exception 'Rol no válido'; end if;
  insert into auth.users (
    instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
    confirmation_token, recovery_token, email_change_token_new, email_change
  ) values (
    '00000000-0000-0000-0000-000000000000', new_id, 'authenticated', 'authenticated', mail,
    extensions.crypt(p_password, extensions.gen_salt('bf')), now(),
    '{"provider":"email","providers":["email"]}'::jsonb, jsonb_build_object('username', p_username),
    now(), now(), '', '', '', ''
  );
  insert into auth.identities (id, user_id, provider_id, identity_data, provider, created_at, updated_at, last_sign_in_at)
  values (gen_random_uuid(), new_id, new_id::text,
          jsonb_build_object('sub', new_id::text, 'email', mail, 'email_verified', true),
          'email', now(), now(), now());
  update public.profiles set role = p_role where id = new_id;
  return new_id;
end;
$$;

create or replace function public.admin_update_user(
  p_id uuid, p_username text default null, p_role text default null, p_password text default null
) returns void language plpgsql security definer set search_path = public, extensions as $$
begin
  if not public.is_admin() then raise exception 'Solo administradores'; end if;
  if p_id = auth.uid() and p_role is not null and p_role <> 'admin' then
    raise exception 'No puedes quitarte a ti mismo el rol de administrador';
  end if;
  if p_username is not null then
    if p_username !~ '^[A-Za-z0-9_.-]{3,32}$' then raise exception 'Nombre de usuario no válido'; end if;
    update public.profiles set username = p_username where id = p_id;
    update auth.users set email = public.username_email(p_username),
      raw_user_meta_data = coalesce(raw_user_meta_data, '{}'::jsonb) || jsonb_build_object('username', p_username),
      updated_at = now()
    where id = p_id;
  end if;
  if p_role is not null then
    if p_role not in ('player', 'admin') then raise exception 'Rol no válido'; end if;
    update public.profiles set role = p_role where id = p_id;
  end if;
  if p_password is not null then
    if length(p_password) < 8 then raise exception 'La contraseña necesita al menos 8 caracteres'; end if;
    update auth.users set encrypted_password = extensions.crypt(p_password, extensions.gen_salt('bf')),
      updated_at = now() where id = p_id;
  end if;
end;
$$;

create or replace function public.admin_delete_user(p_id uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.is_admin() then raise exception 'Solo administradores'; end if;
  if p_id = auth.uid() then raise exception 'No puedes borrar tu propia cuenta de administrador'; end if;
  delete from auth.users where id = p_id;  -- en cascada: perfil, partidas y modelo
end;
$$;

-- Funciones que solo puede llamar un usuario con sesión (nunca el rol anónimo).
revoke all on function public.admin_create_user(text, text, text) from public, anon;
revoke all on function public.admin_update_user(uuid, text, text, text) from public, anon;
revoke all on function public.admin_delete_user(uuid) from public, anon;
grant execute on function public.admin_create_user(text, text, text) to authenticated;
grant execute on function public.admin_update_user(uuid, text, text, text) to authenticated;
grant execute on function public.admin_delete_user(uuid) to authenticated;

-- ================================================================ publicidad de la mesa
-- Reverso de las cartas de los bots y consumición junto a cada jugador. La ve todo el mundo
-- (también sin sesión); solo la cambia un administrador con admin_set_ads (que la valida).
create table if not exists public.site_settings (
  key text primary key check (key in ('ads')),
  value jsonb not null,
  updated_by uuid references public.profiles (id) on delete set null,
  updated_at timestamptz not null default now()
);
alter table public.site_settings enable row level security;
drop policy if exists settings_read on public.site_settings;
create policy settings_read on public.site_settings for select using (true);
grant select on public.site_settings to anon, authenticated;

create or replace function public.admin_set_ads(p_ads jsonb) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  img_re constant text := '^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$';
  clean jsonb;
begin
  if not public.is_admin() then raise exception 'Solo administradores'; end if;
  clean := jsonb_build_object(
    'card_brand', btrim(coalesce(p_ads ->> 'card_brand', '')),
    'card_color', coalesce(p_ads ->> 'card_color', '#7a1f2b'),
    'card_image', p_ads -> 'card_image',
    'drink', coalesce(p_ads ->> 'drink', 'cerveza'),
    'drink_brand', btrim(coalesce(p_ads ->> 'drink_brand', '')),
    'drink_color', coalesce(p_ads ->> 'drink_color', '#c8102e'),
    'drink_image', p_ads -> 'drink_image');
  if length(clean ->> 'card_brand') not between 1 and 24 or length(clean ->> 'drink_brand') > 24 then
    raise exception 'La marca tiene que tener entre 1 y 24 letras';
  end if;
  if clean ->> 'card_color' !~ '^#[0-9a-fA-F]{6}$' or clean ->> 'drink_color' !~ '^#[0-9a-fA-F]{6}$' then
    raise exception 'Los colores van en formato #rrggbb';
  end if;
  if clean ->> 'drink' not in ('cerveza', 'refresco', 'cafe', 'agua', 'ninguna') then
    raise exception 'Esa consumición no existe';
  end if;
  if (jsonb_typeof(clean -> 'card_image') = 'string' and (length(clean ->> 'card_image') > 400000 or clean ->> 'card_image' !~ img_re))
     or (jsonb_typeof(clean -> 'drink_image') = 'string' and (length(clean ->> 'drink_image') > 400000 or clean ->> 'drink_image' !~ img_re))
     or coalesce(jsonb_typeof(clean -> 'card_image'), 'null') not in ('string', 'null')
     or coalesce(jsonb_typeof(clean -> 'drink_image'), 'null') not in ('string', 'null') then
    raise exception 'La imagen tiene que ser PNG, JPEG o WebP de 290 KB o menos';
  end if;
  insert into public.site_settings (key, value, updated_by) values ('ads', clean, auth.uid())
  on conflict (key) do update set value = excluded.value, updated_by = excluded.updated_by, updated_at = now();
  return clean;
end;
$$;

-- ================================================================ campeonatos
-- Eliminatorias de 8, 16 o 32 parejas (mínimo 8: cuartos de final, semifinales y final).
-- Un administrador crea el campeonato con nombre y fecha de comienzo; hasta esa fecha la gente
-- se apunta en parejas (con un bot de compañero o con otra persona). Al llegar la fecha se
-- sortea el cuadro y las plazas libres se llenan con parejas de bots. Los partidos entre bots
-- se deciden solos; los de personas se juegan en la web y los apunta quien juega.
create table if not exists public.championships (
  id bigint generated always as identity primary key,
  name text not null check (length(btrim(name)) between 1 and 60),
  starts_at timestamptz not null,
  size int not null check (size in (8, 16, 32)),
  target int not null default 40 check (target in (30, 40)),
  signals boolean not null default false,
  status text not null default 'inscripcion' check (status in ('inscripcion', 'en_juego', 'terminado')),
  winner_team bigint,
  created_by uuid references public.profiles (id) on delete set null,
  created_at timestamptz not null default now()
);

create table if not exists public.champ_teams (
  id bigint generated always as identity primary key,
  championship_id bigint not null references public.championships (id) on delete cascade,
  name text not null check (length(btrim(name)) between 1 and 30),
  -- Si alguien borra su cuenta, su sitio en la pareja lo ocupa un bot.
  captain uuid references public.profiles (id) on delete set null,
  partner uuid references public.profiles (id) on delete set null,
  partner_open boolean not null default false,  -- busca compañero persona
  is_bot boolean not null default false,
  created_at timestamptz not null default now()
);
create unique index if not exists champ_teams_name_idx on public.champ_teams (championship_id, lower(name));

create table if not exists public.champ_matches (
  id bigint generated always as identity primary key,
  championship_id bigint not null references public.championships (id) on delete cascade,
  round int not null,
  slot int not null,
  team_a bigint references public.champ_teams (id),
  team_b bigint references public.champ_teams (id),
  winner bigint references public.champ_teams (id),
  score int[],
  walkover boolean not null default false,  -- lo decidió un administrador
  reported_by uuid references public.profiles (id) on delete set null,
  played_at timestamptz,
  unique (championship_id, round, slot)
);

alter table public.championships enable row level security;
alter table public.champ_teams enable row level security;
alter table public.champ_matches enable row level security;
-- Cualquiera con sesión ve los campeonatos; los cambios van siempre por las funciones de abajo.
drop policy if exists champs_read on public.championships;
create policy champs_read on public.championships for select using (auth.uid() is not null);
drop policy if exists champ_teams_read on public.champ_teams;
create policy champ_teams_read on public.champ_teams for select using (auth.uid() is not null);
drop policy if exists champ_matches_read on public.champ_matches;
create policy champ_matches_read on public.champ_matches for select using (auth.uid() is not null);
grant select on public.championships, public.champ_teams, public.champ_matches to authenticated;

-- Nombres de los perfiles de quienes juegan (los perfiles solo los ve su dueño o un admin).
create or replace function public.champ_players(p_champ bigint)
returns table (id uuid, username text) language sql stable security definer set search_path = public as $$
  select p.id, p.username from public.profiles p
  where auth.uid() is not null and p.id in (
    select captain from public.champ_teams where championship_id = p_champ
    union select partner from public.champ_teams where championship_id = p_champ);
$$;

create or replace function public.champ_rounds(p_size int) returns int language sql immutable as $$
  select (ln(p_size) / ln(2))::int $$;

create or replace function public.admin_create_championship(
  p_name text, p_starts_at timestamptz, p_size int default 8, p_target int default 40, p_signals boolean default false
) returns bigint language plpgsql security definer set search_path = public as $$
declare new_id bigint;
begin
  if not public.is_admin() then raise exception 'Solo administradores'; end if;
  if p_size not in (8, 16, 32) then raise exception 'Un campeonato es de 8, 16 o 32 parejas'; end if;
  if p_target not in (30, 40) then raise exception 'Se juega a 30 o a 40 tantos'; end if;
  if length(btrim(coalesce(p_name, ''))) not between 1 and 60 then
    raise exception 'El nombre tiene que tener entre 1 y 60 letras';
  end if;
  insert into public.championships (name, starts_at, size, target, signals, created_by)
  values (btrim(p_name), p_starts_at, p_size, p_target, p_signals, auth.uid()) returning id into new_id;
  return new_id;
end;
$$;

create or replace function public.admin_delete_championship(p_champ bigint) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.is_admin() then raise exception 'Solo administradores'; end if;
  delete from public.championships where id = p_champ;
end;
$$;

-- Inscripción ---------------------------------------------------------------
create or replace function public.champ_open(p_champ bigint) returns public.championships
language plpgsql security definer set search_path = public as $$
declare c public.championships;
begin
  if auth.uid() is null then raise exception 'Inicia sesión'; end if;
  select * into c from public.championships where id = p_champ for update;
  if not found then raise exception 'Ese campeonato no existe'; end if;
  if c.status <> 'inscripcion' then raise exception 'La inscripción está cerrada: el campeonato ya ha empezado'; end if;
  return c;
end;
$$;

create or replace function public.champ_signed(p_champ bigint, p_user uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.champ_teams
                 where championship_id = p_champ and (captain = p_user or partner = p_user));
$$;

create or replace function public.champ_sign_up(p_champ bigint, p_team_name text, p_partner_open boolean default false)
returns bigint language plpgsql security definer set search_path = public as $$
declare c public.championships; new_id bigint;
begin
  c := public.champ_open(p_champ);
  if length(btrim(coalesce(p_team_name, ''))) not between 1 and 30 then
    raise exception 'El nombre de la pareja tiene que tener entre 1 y 30 letras';
  end if;
  if public.champ_signed(p_champ, auth.uid()) then raise exception 'Ya estás apuntado en este campeonato'; end if;
  if (select count(*) from public.champ_teams where championship_id = p_champ) >= c.size then
    raise exception 'El campeonato está completo';
  end if;
  if exists (select 1 from public.champ_teams where championship_id = p_champ and lower(name) = lower(btrim(p_team_name))) then
    raise exception 'Ya hay una pareja con ese nombre';
  end if;
  insert into public.champ_teams (championship_id, name, captain, partner_open)
  values (p_champ, btrim(p_team_name), auth.uid(), coalesce(p_partner_open, false)) returning id into new_id;
  return new_id;
end;
$$;

create or replace function public.champ_join_team(p_team bigint) returns void
language plpgsql security definer set search_path = public as $$
declare t public.champ_teams;
begin
  select * into t from public.champ_teams where id = p_team;
  if not found then raise exception 'Esa pareja no existe'; end if;
  perform public.champ_open(t.championship_id);
  if public.champ_signed(t.championship_id, auth.uid()) then raise exception 'Ya estás apuntado en este campeonato'; end if;
  if not t.partner_open or t.partner is not null then raise exception 'Esa pareja no busca compañero'; end if;
  update public.champ_teams set partner = auth.uid() where id = p_team;
end;
$$;

create or replace function public.champ_leave(p_champ bigint) returns void
language plpgsql security definer set search_path = public as $$
declare t public.champ_teams;
begin
  perform public.champ_open(p_champ);
  select * into t from public.champ_teams
  where championship_id = p_champ and (captain = auth.uid() or partner = auth.uid());
  if not found then raise exception 'No estás apuntado en este campeonato'; end if;
  if t.captain = auth.uid() then delete from public.champ_teams where id = t.id;  -- se va la pareja
  else update public.champ_teams set partner = null where id = t.id;              -- queda plaza libre
  end if;
end;
$$;

-- Cuadro ----------------------------------------------------------------------
-- Partidos listos entre dos parejas sin personas: se deciden solos (a cara o cruz, con un
-- tanteo verosímil), y el ganador pasa a la ronda siguiente.
create or replace function public.champ_record(p_match bigint, p_winner bigint, p_score int[], p_walkover boolean)
returns void language plpgsql security definer set search_path = public as $$
declare m public.champ_matches; c public.championships;
begin
  select * into m from public.champ_matches where id = p_match for update;
  select * into c from public.championships where id = m.championship_id for update;
  if m.team_a is null or m.team_b is null or m.winner is not null then
    raise exception 'Ese partido no se puede jugar ahora';
  end if;
  if p_winner not in (m.team_a, m.team_b) then raise exception 'Esa pareja no juega este partido'; end if;
  update public.champ_matches set winner = p_winner, score = p_score, walkover = p_walkover,
    reported_by = auth.uid(), played_at = now() where id = p_match;
  if m.round = public.champ_rounds(c.size) then
    update public.championships set status = 'terminado', winner_team = p_winner where id = c.id;
  elsif m.slot % 2 = 0 then
    update public.champ_matches set team_a = p_winner
    where championship_id = c.id and round = m.round + 1 and slot = m.slot / 2;
  else
    update public.champ_matches set team_b = p_winner
    where championship_id = c.id and round = m.round + 1 and slot = m.slot / 2;
  end if;
end;
$$;
revoke all on function public.champ_record(bigint, bigint, int[], boolean) from public, anon, authenticated;

create or replace function public.champ_human(p_team bigint) returns boolean
language sql stable security definer set search_path = public as $$
  select captain is not null or partner is not null from public.champ_teams where id = p_team;
$$;

create or replace function public.champ_play_bots(p_champ bigint) returns void
language plpgsql security definer set search_path = public as $$
declare m public.champ_matches; target int; loser_pts int; a_wins boolean;
begin
  select c.target into target from public.championships c where c.id = p_champ;
  loop
    select * into m from public.champ_matches
    where championship_id = p_champ and team_a is not null and team_b is not null and winner is null
      and not public.champ_human(team_a) and not public.champ_human(team_b)
    order by round, slot limit 1;
    exit when not found;
    a_wins := random() < 0.5;
    loser_pts := 5 + floor(random() * (target - 9))::int;
    perform public.champ_record(m.id, case when a_wins then m.team_a else m.team_b end,
      case when a_wins then array[target, loser_pts] else array[loser_pts, target] end, false);
  end loop;
end;
$$;
revoke all on function public.champ_play_bots(bigint) from public, anon, authenticated;

create or replace function public.champ_draw(p_champ bigint) returns void
language plpgsql security definer set search_path = public as $$
declare
  c public.championships;
  bot_names constant text[] := array['Los Tahúres', 'Las Piedras Rodantes', 'Órdago y Medio',
    'La Pareja Imposible', 'Los Revoques', 'Duples de Reyes', 'Los de la 31', 'Los Amarracos',
    'Mus de Barrio', 'Envido y Quiero', 'La Peña del Mus', 'Los Faroleros', 'Cuatro Reyes',
    'Los de la Chica', 'Grande y Libre', 'Los Mudos', 'Las Señas Ciegas', 'Al Punto',
    'Los Pasadores', 'Medias de Ases', 'La Mano Inocente', 'Los del Postre', 'Treinta y Una',
    'Los Cortamus', 'La Baraja Loca', 'Los Sin Juego', 'Reyes Magos', 'La Última Piedra',
    'Los Descartes', 'Pares y Nones', 'La Vaca del Mus'];
  missing int; ids bigint[]; k int; r int; bot_name text;
begin
  select * into c from public.championships where id = p_champ for update;
  if not found then raise exception 'Ese campeonato no existe'; end if;
  if c.status <> 'inscripcion' then raise exception 'La inscripción está cerrada: el campeonato ya ha empezado'; end if;
  if not exists (select 1 from public.champ_teams where championship_id = p_champ) then
    raise exception 'No hay ninguna pareja apuntada';
  end if;
  missing := c.size - (select count(*) from public.champ_teams where championship_id = p_champ);
  foreach bot_name in array bot_names loop
    exit when missing <= 0;
    if not exists (select 1 from public.champ_teams where championship_id = p_champ and lower(name) = lower(bot_name)) then
      insert into public.champ_teams (championship_id, name, is_bot) values (p_champ, bot_name, true);
      missing := missing - 1;
    end if;
  end loop;
  update public.champ_teams set partner_open = false where championship_id = p_champ;
  select array_agg(id order by random()) into ids from public.champ_teams where championship_id = p_champ;
  for r in 1 .. public.champ_rounds(c.size) loop
    for k in 0 .. (c.size >> r) - 1 loop
      insert into public.champ_matches (championship_id, round, slot, team_a, team_b)
      values (p_champ, r, k,
              case when r = 1 then ids[2 * k + 1] end, case when r = 1 then ids[2 * k + 2] end);
    end loop;
  end loop;
  update public.championships set status = 'en_juego' where id = p_champ;
  perform public.champ_play_bots(p_champ);
end;
$$;
revoke all on function public.champ_draw(bigint) from public, anon, authenticated;

-- Empieza ya (administrador) o, para cualquiera con sesión, los que ya han llegado a su fecha.
create or replace function public.admin_start_championship(p_champ bigint) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.is_admin() then raise exception 'Solo administradores'; end if;
  perform public.champ_draw(p_champ);
end;
$$;

create or replace function public.champ_start_due() returns int
language plpgsql security definer set search_path = public as $$
declare c record; n int := 0;
begin
  if auth.uid() is null then raise exception 'Inicia sesión'; end if;
  for c in select id from public.championships ch
           where ch.status = 'inscripcion' and ch.starts_at <= now()
             and exists (select 1 from public.champ_teams t where t.championship_id = ch.id) loop
    perform public.champ_draw(c.id);
    n := n + 1;
  end loop;
  return n;
end;
$$;

-- Resultado de un partido con personas: lo apunta alguien de las dos parejas al terminar la
-- partida en la web (o un administrador, que puede dar el partido a una pareja).
create or replace function public.champ_report(p_match bigint, p_winner bigint, p_score int[])
returns void language plpgsql security definer set search_path = public as $$
declare m public.champ_matches;
begin
  select * into m from public.champ_matches where id = p_match;
  if not found then raise exception 'Ese partido no existe'; end if;
  if not exists (select 1 from public.champ_teams where id in (m.team_a, m.team_b)
                 and (captain = auth.uid() or partner = auth.uid())) then
    raise exception 'Este partido es de otras parejas';
  end if;
  if p_score is null or array_length(p_score, 1) <> 2 then raise exception 'Tanteo no válido'; end if;
  perform public.champ_record(p_match, p_winner, p_score, false);
  perform public.champ_play_bots(m.championship_id);
end;
$$;

create or replace function public.admin_set_match_winner(p_match bigint, p_winner bigint)
returns void language plpgsql security definer set search_path = public as $$
declare m public.champ_matches;
begin
  if not public.is_admin() then raise exception 'Solo administradores'; end if;
  select * into m from public.champ_matches where id = p_match;
  if not found then raise exception 'Ese partido no existe'; end if;
  perform public.champ_record(p_match, p_winner, null, true);
  perform public.champ_play_bots(m.championship_id);
end;
$$;

do $$
declare f text;
begin
  foreach f in array array[
    'admin_set_ads(jsonb)', 'champ_players(bigint)', 'admin_create_championship(text, timestamptz, int, int, boolean)',
    'admin_delete_championship(bigint)', 'champ_sign_up(bigint, text, boolean)', 'champ_join_team(bigint)',
    'champ_leave(bigint)', 'admin_start_championship(bigint)', 'champ_start_due()',
    'champ_report(bigint, bigint, int[])', 'admin_set_match_winner(bigint, bigint)'] loop
    execute format('revoke all on function public.%s from public, anon', f);
    execute format('grant execute on function public.%s to authenticated', f);
  end loop;
end $$;
