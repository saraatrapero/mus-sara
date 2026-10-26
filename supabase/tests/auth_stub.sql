-- Imitación mínima de Supabase para probar supabase/schema.sql en un PostgreSQL normal.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
end $$;
create schema if not exists auth;
create schema if not exists extensions;
create table if not exists auth.users (
  instance_id uuid, id uuid primary key, aud text, role text, email text unique, encrypted_password text,
  email_confirmed_at timestamptz, raw_app_meta_data jsonb, raw_user_meta_data jsonb,
  created_at timestamptz, updated_at timestamptz, confirmation_token text, recovery_token text,
  email_change_token_new text, email_change text
);
create table if not exists auth.identities (
  id uuid primary key, user_id uuid references auth.users (id) on delete cascade, provider_id text,
  identity_data jsonb, provider text, created_at timestamptz, updated_at timestamptz, last_sign_in_at timestamptz
);
create or replace function auth.uid() returns uuid language sql stable as
  $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
-- pgcrypto simulado (en Supabase es el real)
create or replace function extensions.gen_salt(text) returns text language sql as $$ select 'salt' $$;
create or replace function extensions.crypt(p text, s text) returns text language sql as $$ select md5(p || s) $$;
grant usage on schema public, auth, extensions to anon, authenticated;
