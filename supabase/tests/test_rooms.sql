-- Pruebas de las salas online: código, unirse, quién ve qué y quién manda.
\set ON_ERROR_STOP on
grant select, insert, update, delete on all tables in schema public to authenticated;
grant select on all tables in schema public to anon;

insert into auth.users (id, email, raw_user_meta_data) values
  ('b1111111-1111-1111-1111-111111111111', 'ana@jugadores.mus-st.app', '{"username":"ana"}'),
  ('b2222222-2222-2222-2222-222222222222', 'eva@jugadores.mus-st.app', '{"username":"eva"}'),
  ('b3333333-3333-3333-3333-333333333333', 'leo@jugadores.mus-st.app', '{"username":"leo"}'),
  ('b4444444-4444-4444-4444-444444444444', 'mar@jugadores.mus-st.app', '{"username":"mar"}'),
  ('b5555555-5555-5555-5555-555555555555', 'pez@jugadores.mus-st.app', '{"username":"pez"}');
create temp table codes (k text primary key, code text);
grant all on codes to authenticated;

set role authenticated;
-- Ana crea una sala de cuatro: le sale un código de 6 letras sin 0/O/1/I.
select set_config('request.jwt.claim.sub', 'b1111111-1111-1111-1111-111111111111', false);
do $$
declare c text;
begin
  begin
    perform public.room_create('tres');
    raise exception 'sala de tres aceptada';
  exception when others then
    if sqlerrm like '%tres aceptada%' then raise; end if;
  end;
  c := public.room_create('cuatro', '{"target":30}');
  assert c ~ '^[A-HJ-NP-Z2-9]{6}$', 'código raro: ' || c;
  insert into codes values ('cuatro', c);
  assert (select seats -> '0' ->> 'name' from public.rooms where code = c) = 'ana', 'ana en el asiento 0';
end $$;

-- Eva, Leo y Mar se unen (en minúsculas también vale); Pez ya no cabe.
select set_config('request.jwt.claim.sub', 'b2222222-2222-2222-2222-222222222222', false);
do $$
declare c text := (select code from codes where k = 'cuatro');
begin
  assert (select count(*) from public.rooms) = 0, 'sin unirse no se ve la sala';
  assert public.room_join(lower(c)) = 2, 'eva, compañera de ana';
  assert public.room_join(c) = 2, 'unirse dos veces no cambia el asiento';
  assert (select count(*) from public.rooms) = 1, 'ya la ve';
  begin
    perform public.room_join('ZZZZZZ');
    raise exception 'código inventado aceptado';
  exception when others then
    if sqlerrm like '%inventado aceptado%' then raise; end if;
  end;
end $$;
select set_config('request.jwt.claim.sub', 'b3333333-3333-3333-3333-333333333333', false);
select public.room_join((select code from codes where k = 'cuatro')) = 1 as leo_en_1 \gset
select set_config('request.jwt.claim.sub', 'b4444444-4444-4444-4444-444444444444', false);
do $$
declare c text := (select code from codes where k = 'cuatro');
begin
  assert public.room_join(c) = 3, 'mar en el 3';
  perform public.room_leave(c);   -- se va antes de empezar…
  assert public.room_join(c) = 3, '…y vuelve';
end $$;
select set_config('request.jwt.claim.sub', 'b5555555-5555-5555-5555-555555555555', false);
do $$
begin
  begin
    perform public.room_join((select code from codes where k = 'cuatro'));
    raise exception 'sala llena aceptada';
  exception when others then
    if sqlerrm like '%llena aceptada%' then raise; end if;
  end;
end $$;

-- Solo Ana (anfitriona) empieza y publica; los demás no pueden.
select set_config('request.jwt.claim.sub', 'b2222222-2222-2222-2222-222222222222', false);
do $$
declare c text := (select code from codes where k = 'cuatro');
begin
  begin
    perform public.room_set_status(c, 'jugando');
    raise exception 'eva ha empezado la sala';
  exception when others then
    if sqlerrm like '%eva ha empezado%' then raise; end if;
  end;
  begin
    perform public.room_publish(c, 1, '{"hand":["1O"]}');
    raise exception 'eva ha publicado';
  exception when others then
    if sqlerrm like '%eva ha publicado%' then raise; end if;
  end;
  begin
    perform public.room_send(c, '{"path":"action"}');
    raise exception 'acción antes de empezar';
  exception when others then
    if sqlerrm like '%antes de empezar%' then raise; end if;
  end;
end $$;
select set_config('request.jwt.claim.sub', 'b1111111-1111-1111-1111-111111111111', false);
do $$
declare c text := (select code from codes where k = 'cuatro');
begin
  perform public.room_set_status(c, 'jugando');
  perform public.room_publish(c, 1, '{"seat":1,"hand":["1O","1C","12E","12B"]}');
  perform public.room_publish(c, 2, '{"seat":2,"hand":["4O","5C","6E","7B"]}');
  perform public.room_publish(c, 2, '{"seat":2,"hand":["4O","5C","6E","10B"]}');  -- se actualiza
  begin
    perform public.room_set_status(c, 'esperando');
    raise exception 'vuelta atrás aceptada';
  exception when others then
    if sqlerrm like '%atrás aceptada%' then raise; end if;
  end;
  assert (select count(*) from public.room_views) = 0, 'la anfitriona no lee las cartas ajenas de la tabla';
end $$;

-- Cada persona ve solo su asiento; tras empezar ya no entra nadie más.
select set_config('request.jwt.claim.sub', 'b2222222-2222-2222-2222-222222222222', false);
do $$
declare c text := (select code from codes where k = 'cuatro'); a bigint;
begin
  assert (select count(*) from public.room_views) = 1, 'eva ve una vista';
  assert (select obs -> 'hand' ->> 3 from public.room_views) = '10B', 'la última';
  a := public.room_send(c, '{"path":"action","body":{"action":{"type":"mus"}}}');
  insert into codes values ('accion', a::text);
  assert (select seat from public.room_actions where id = a) = 2, 'acción del asiento 2';
  begin
    perform public.room_pending(c);
    raise exception 'eva lee las acciones pendientes';
  exception when others then
    if sqlerrm like '%acciones pendientes%' then raise; end if;
  end;
end $$;
select set_config('request.jwt.claim.sub', 'b3333333-3333-3333-3333-333333333333', false);
do $$
begin
  assert (select obs ->> 'seat' from public.room_views) = '1', 'leo ve solo el 1';
  assert (select count(*) from public.room_actions) = 0, 'leo no ve las acciones de eva';
end $$;
select set_config('request.jwt.claim.sub', 'b5555555-5555-5555-5555-555555555555', false);
do $$
begin
  assert (select count(*) from public.rooms) = 0, 'pez no ve la sala';
  begin
    perform public.room_send((select code from codes where k = 'cuatro'), '{"path":"action"}');
    raise exception 'pez ha jugado';
  exception when others then
    if sqlerrm like '%pez ha jugado%' then raise; end if;
  end;
end $$;

-- La anfitriona recoge la acción y la marca como hecha (con o sin error).
select set_config('request.jwt.claim.sub', 'b1111111-1111-1111-1111-111111111111', false);
do $$
declare c text := (select code from codes where k = 'cuatro'); a bigint := (select code::bigint from codes where k = 'accion');
begin
  assert (select count(*) from public.room_pending(c)) = 1, 'una pendiente';
  perform public.room_done(a, 'No es tu turno');
  assert (select count(*) from public.room_pending(c)) = 0, 'ninguna pendiente';
  perform public.room_set_status(c, 'terminada');
end $$;
select set_config('request.jwt.claim.sub', 'b2222222-2222-2222-2222-222222222222', false);
do $$
begin
  assert (select error from public.room_actions) = 'No es tu turno', 'eva ve por qué no valió';
end $$;

-- Sin sesión no se ve nada; si la anfitriona se va, la sala desaparece.
set role anon;
do $$ begin
  assert (select count(*) from public.rooms) = 0 and (select count(*) from public.room_views) = 0, 'anon no ve nada';
end $$;
set role authenticated;
select set_config('request.jwt.claim.sub', 'b1111111-1111-1111-1111-111111111111', false);
do $$
declare c text := (select code from codes where k = 'cuatro');
begin
  perform public.room_leave(c);
  assert not exists (select 1 from public.room_actions where code = c), 'borrado en cascada';
end $$;
reset role;
select 'OK: salas' as resultado;
