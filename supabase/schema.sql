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
