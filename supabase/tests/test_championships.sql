-- Pruebas de la publicidad y de los campeonatos (permisos, inscripción, cuadro y resultados).
\set ON_ERROR_STOP on
grant select, insert, update, delete on all tables in schema public to authenticated;
-- Como en Supabase, el rol anónimo también tiene permisos sobre las tablas: lo frena la RLS.
grant select on all tables in schema public to anon;

insert into auth.users (id, email, raw_user_meta_data) values
  ('a1111111-1111-1111-1111-111111111111', 'jefa@jugadores.mus-st.app', '{"username":"jefa"}'),
  ('a2222222-2222-2222-2222-222222222222', 'eva@jugadores.mus-st.app', '{"username":"eva"}'),
  ('a3333333-3333-3333-3333-333333333333', 'leo@jugadores.mus-st.app', '{"username":"leo"}'),
  ('a4444444-4444-4444-4444-444444444444', 'mar@jugadores.mus-st.app', '{"username":"mar"}');
update public.profiles set role = 'admin' where username = 'jefa';

-- Publicidad: la lee cualquiera, también sin sesión; solo la cambia un administrador.
set role authenticated;
select set_config('request.jwt.claim.sub', 'a2222222-2222-2222-2222-222222222222', false);
do $$ begin
  begin
    perform public.admin_set_ads('{"card_brand":"Pirata"}');
    raise exception 'una jugadora ha cambiado la publicidad';
  exception when others then
    if sqlerrm like '%jugadora ha cambiado%' then raise; end if;
  end;
  begin
    insert into public.site_settings (key, value) values ('ads', '{}');
    raise exception 'una jugadora ha escrito ajustes';
  exception when others then
    if sqlerrm like '%jugadora ha escrito%' then raise; end if;
  end;
  begin
    perform public.admin_create_championship('Pirata', now(), 8);
    raise exception 'una jugadora ha creado un campeonato';
  exception when others then
    if sqlerrm like '%jugadora ha creado%' then raise; end if;
  end;
end $$;

select set_config('request.jwt.claim.sub', 'a1111111-1111-1111-1111-111111111111', false);
do $$
declare bad jsonb; saved jsonb;
begin
  saved := public.admin_set_ads('{"card_brand":" Bar Pepe ","drink":"refresco","drink_brand":"Cola","card_image":"data:image/png;base64,iVBORw0KGgo="}');
  assert saved ->> 'card_brand' = 'Bar Pepe', 'marca sin espacios';
  assert saved ->> 'card_color' = '#7a1f2b', 'color por defecto';
  perform public.admin_set_ads('{"card_brand":"Bar Pepe","drink":"cafe"}');  -- segunda vez: actualiza
  foreach bad in array array[
    '{"card_brand":""}', '{"card_brand":"xxxxxxxxxxxxxxxxxxxxxxxxx"}', '{"card_brand":"a","card_color":"rojo"}',
    '{"card_brand":"a","drink":"whisky"}', '{"card_brand":"a","card_image":"javascript:alert(1)"}',
    '{"card_brand":"a","drink_image":"data:image/svg+xml;base64,PHN2Zz4="}', '{"card_brand":"a","card_image":12}']::jsonb[] loop
    begin
      perform public.admin_set_ads(bad);
      raise exception 'aceptada: %', bad;
    exception when others then
      if sqlerrm like 'aceptada:%' then raise; end if;
    end;
  end loop;
end $$;
set role anon;
do $$ begin
  assert (select value ->> 'drink' from public.site_settings where key = 'ads') = 'cafe', 'sin sesión se ve la publicidad';
  assert (select count(*) from public.championships) = 0, 'sin sesión no se ven campeonatos';
end $$;

-- Campeonatos: la administradora crea uno; validaciones.
set role authenticated;
select set_config('request.jwt.claim.sub', 'a1111111-1111-1111-1111-111111111111', false);
do $$
declare bad record; cid bigint;
begin
  for bad in select * from (values ('', 8, 40), ('Copa', 4, 40), ('Copa', 12, 40), ('Copa', 8, 35)) v(n, s, t) loop
    begin
      perform public.admin_create_championship(bad.n, now(), bad.s, bad.t);
      raise exception 'aceptado: %', bad;
    exception when others then
      if sqlerrm like 'aceptado:%' then raise; end if;
    end;
  end loop;
  cid := public.admin_create_championship(' Copa de Otoño ', now() + interval '3 days', 8, 30, true);
  assert (select name from public.championships where id = cid) = 'Copa de Otoño', 'nombre sin espacios';
  begin
    perform public.admin_start_championship(cid);
    raise exception 'ha empezado sin parejas';
  exception when others then
    if sqlerrm like '%sin parejas%' then raise; end if;
  end;
end $$;

-- Inscripción: eva se apunta buscando compañero, leo se une, mar se apunta con un bot.
select set_config('request.jwt.claim.sub', 'a2222222-2222-2222-2222-222222222222', false);
do $$
declare cid bigint := (select id from public.championships where name = 'Copa de Otoño');
begin
  perform public.champ_sign_up(cid, 'Las de Eva', true);
  begin
    perform public.champ_sign_up(cid, 'Otra', false);
    raise exception 'apuntada dos veces';
  exception when others then
    if sqlerrm like '%apuntada dos veces%' then raise; end if;
  end;
  begin
    perform public.champ_sign_up(cid, '   ', false);
    raise exception 'nombre vacío aceptado';
  exception when others then
    if sqlerrm like '%vacío aceptado%' then raise; end if;
  end;
end $$;
select set_config('request.jwt.claim.sub', 'a3333333-3333-3333-3333-333333333333', false);
do $$
declare cid bigint := (select id from public.championships where name = 'Copa de Otoño');
declare tid bigint := (select id from public.champ_teams where name = 'Las de Eva');
begin
  begin
    perform public.champ_sign_up(cid, 'las de eva', false);
    raise exception 'nombre repetido aceptado';
  exception when others then
    if sqlerrm like '%repetido aceptado%' then raise; end if;
  end;
  begin
    perform public.champ_leave(cid);
    raise exception 'se ha borrado sin estar apuntado';
  exception when others then
    if sqlerrm like '%sin estar apuntado%' then raise; end if;
  end;
  perform public.champ_join_team(tid);
  assert (select partner from public.champ_teams where id = tid) = auth.uid(), 'leo es el compañero de eva';
  assert (select count(*) from public.champ_players(cid)) = 2, 'se ven los nombres de quienes juegan';
  perform public.champ_leave(cid);  -- leo se va: queda la plaza libre
  assert (select partner from public.champ_teams where id = tid) is null, 'plaza libre otra vez';
  perform public.champ_join_team(tid);
end $$;
select set_config('request.jwt.claim.sub', 'a4444444-4444-4444-4444-444444444444', false);
do $$
declare cid bigint := (select id from public.championships where name = 'Copa de Otoño');
declare tid bigint := (select id from public.champ_teams where name = 'Las de Eva');
begin
  begin
    perform public.champ_join_team(tid);
    raise exception 'se ha unido a una pareja completa';
  exception when others then
    if sqlerrm like '%pareja completa%' then raise; end if;
  end;
  perform public.champ_sign_up(cid, 'Mar y su bot', false);
  perform public.champ_leave(cid);  -- quien apuntó la pareja se va: se va la pareja
  assert not exists (select 1 from public.champ_teams where name = 'Mar y su bot'), 'pareja borrada';
  perform public.champ_sign_up(cid, 'Mar y su bot', false);
  -- Aún no es la fecha: champ_start_due no lo empieza.
  assert public.champ_start_due() = 0, 'no empieza antes de su fecha';
end $$;

-- Llega la fecha: al consultar se sortea el cuadro y se completan las 8 parejas con bots.
reset role;
update public.championships set starts_at = now() - interval '1 minute' where name = 'Copa de Otoño';
set role authenticated;
do $$
declare cid bigint := (select id from public.championships where name = 'Copa de Otoño');
begin
  assert public.champ_start_due() = 1, 'empieza al llegar la fecha';
  assert (select status from public.championships where id = cid) = 'en_juego', 'en juego';
  assert (select count(*) from public.champ_teams where championship_id = cid) = 8, '8 parejas';
  assert (select count(*) from public.champ_teams where championship_id = cid and is_bot) = 6, '6 de bots';
  assert (select count(*) from public.champ_matches where championship_id = cid) = 7, 'cuartos, semis y final';
  assert (select count(*) from public.champ_matches where championship_id = cid and round = 1) = 4, '4 cuartos';
  -- Los cuartos entre bots ya están decididos, con un tanteo de partida a 30.
  assert not exists (select 1 from public.champ_matches m where championship_id = cid and round = 1 and winner is null
                     and not public.champ_human(m.team_a) and not public.champ_human(m.team_b)), 'bots decididos';
  assert not exists (select 1 from public.champ_matches where championship_id = cid and winner is not null
                     and not (30 = any(score))), 'tanteo a 30';
  begin
    perform public.champ_sign_up(cid, 'Tarde', false);
    raise exception 'apuntada tras empezar';
  exception when others then
    if sqlerrm like '%tras empezar%' then raise; end if;
  end;
end $$;

-- Mar juega su partido: alguien de fuera no puede apuntar el resultado; ella sí.
do $$
declare m public.champ_matches; mine bigint := (select id from public.champ_teams where name = 'Mar y su bot');
begin
  select * into m from public.champ_matches where mine in (team_a, team_b) and round = 1;
  perform set_config('request.jwt.claim.sub', 'a2222222-2222-2222-2222-222222222222', false);
  if not exists (select 1 from public.champ_teams t where t.id in (m.team_a, m.team_b) and t.name = 'Las de Eva') then
    begin
      perform public.champ_report(m.id, mine, array[30, 12]);
      raise exception 'eva ha apuntado un partido ajeno';
    exception when others then
      if sqlerrm like '%partido ajeno%' then raise; end if;
    end;
  end if;
  perform set_config('request.jwt.claim.sub', 'a4444444-4444-4444-4444-444444444444', false);
  begin
    perform public.champ_report(m.id, 999999, array[30, 12]);
    raise exception 'ganador que no juega aceptado';
  exception when others then
    if sqlerrm like '%que no juega aceptado%' then raise; end if;
  end;
  begin
    perform public.champ_report(m.id, mine, array[30]);
    raise exception 'tanteo incompleto aceptado';
  exception when others then
    if sqlerrm like '%incompleto aceptado%' then raise; end if;
  end;
  perform public.champ_report(m.id, mine, case when m.team_a = mine then array[30, 12] else array[12, 30] end);
  assert (select winner from public.champ_matches where id = m.id) = mine, 'resultado apuntado';
  begin
    perform public.champ_report(m.id, mine, array[30, 12]);
    raise exception 'apuntado dos veces';
  exception when others then
    if sqlerrm like '%apuntado dos veces%' then raise; end if;
  end;
end $$;

-- La administradora da los partidos que queden con personas hasta terminar el campeonato.
select set_config('request.jwt.claim.sub', 'a1111111-1111-1111-1111-111111111111', false);
do $$
declare cid bigint := (select id from public.championships where name = 'Copa de Otoño'); m public.champ_matches;
begin
  loop
    select * into m from public.champ_matches where championship_id = cid
      and team_a is not null and team_b is not null and winner is null order by round, slot limit 1;
    exit when not found;
    perform public.admin_set_match_winner(m.id, m.team_a);
    assert (select walkover from public.champ_matches where id = m.id), 'dado por el admin';
  end loop;
  assert (select status from public.championships where id = cid) = 'terminado', 'terminado';
  assert (select winner_team from public.championships where id = cid) is not null, 'con campeón';
  assert not exists (select 1 from public.champ_matches where championship_id = cid and winner is null), 'todo jugado';
  perform public.admin_delete_championship(cid);
  assert not exists (select 1 from public.champ_teams where championship_id = cid), 'borrado en cascada';
end $$;

-- Las funciones internas no se pueden llamar directamente.
do $$ begin
  begin
    perform public.champ_play_bots(1);
    raise exception 'función interna llamada';
  exception when others then
    if sqlerrm like '%interna llamada%' then raise; end if;
  end;
end $$;
reset role;
select 'OK: publicidad y campeonatos' as resultado;
