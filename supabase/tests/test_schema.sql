-- Pruebas de permisos (RLS) y de las funciones de administración.
\set ON_ERROR_STOP on
grant select, insert, update, delete on all tables in schema public to authenticated;

-- Dos jugadores registrados por la vía normal (signUp → trigger crea el perfil)
insert into auth.users (id, email, raw_user_meta_data) values
  ('11111111-1111-1111-1111-111111111111', 'admin@jugadores.mus-st.app', '{"username":"sara"}'),
  ('22222222-2222-2222-2222-222222222222', 'ana@jugadores.mus-st.app', '{"username":"ana"}'),
  ('33333333-3333-3333-3333-333333333333', 'luis@jugadores.mus-st.app', '{"username":"luis"}');
update public.profiles set role = 'admin' where username = 'sara';
insert into public.games (id, user_id, mode, won, score) values
  ('g-ana', '22222222-2222-2222-2222-222222222222', 'rapida', true, '{40,20}'),
  ('g-luis', '33333333-3333-3333-3333-333333333333', 'rapida', false, '{10,40}');

-- Como ana (jugadora)
set role authenticated;
select set_config('request.jwt.claim.sub', '22222222-2222-2222-2222-222222222222', false);
do $$ begin
  assert (select count(*) from public.games) = 1, 'ana solo ve su partida';
  assert (select count(*) from public.profiles) = 1, 'ana solo ve su perfil';
  begin
    update public.profiles set role = 'admin' where id = auth.uid();
    raise exception 'ana se ha hecho admin';
  exception when others then
    if sqlerrm like '%ana se ha hecho admin%' then raise; end if;
  end;
  begin
    perform public.admin_create_user('pirata', 'contraseña1');
    raise exception 'una jugadora ha creado usuarios';
  exception when others then
    if sqlerrm like '%jugadora ha creado%' then raise; end if;
  end;
  begin
    insert into public.games (id, user_id, mode, won, score)
    values ('falsa', '33333333-3333-3333-3333-333333333333', 'rapida', true, '{40,0}');
    raise exception 'ana ha escrito una partida de luis';
  exception when others then
    if sqlerrm like '%ana ha escrito%' then raise; end if;
  end;
  insert into public.player_models (user_id, model) values (auth.uid(), '{"games":1}');
end $$;

-- Como sara (administradora)
select set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', false);
do $$
declare nid uuid;
begin
  assert (select count(*) from public.games) = 2, 'la admin ve todas las partidas';
  assert (select count(*) from public.profiles) = 3, 'la admin ve todos los perfiles';
  assert (select count(*) from public.player_models) = 1, 'la admin ve los modelos';
  nid := public.admin_create_user('nuevo', 'contraseña-segura', 'player');
  assert (select username from public.profiles where id = nid) = 'nuevo', 'perfil creado';
  perform public.admin_update_user(nid, 'renombrado', 'admin', 'otra-contraseña');
  assert (select role from public.profiles where id = nid) = 'admin', 'rol cambiado';
  perform public.admin_delete_user('33333333-3333-3333-3333-333333333333');
  assert (select count(*) from public.games where id = 'g-luis') = 0, 'borrado en cascada';
  begin
    perform public.admin_delete_user(auth.uid());
    raise exception 'la admin se ha borrado a sí misma';
  exception when others then
    if sqlerrm like '%se ha borrado%' then raise; end if;
  end;
end $$;
reset role;
do $$ begin
  assert (select count(*) from auth.identities i join auth.users u on u.id = i.user_id
          where u.email = 'renombrado@jugadores.mus-st.app') = 1, 'usuario creado con identidad y correo renombrado';
  assert (select count(*) from auth.users where id = '33333333-3333-3333-3333-333333333333') = 0, 'usuario borrado';
end $$;
select 'OK: permisos y administración' as resultado;
