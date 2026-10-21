-- ===========================================================================
-- ГДЗ НЭЛ 3.0 — атомарные лайки доски почёта.
--
-- Проблема: два одновременных вызова honor_like могли оба увидеть
-- отсутствие лайка, вставить его и дважды увеличить счётчик. Обратный
-- сценарий — дважды удалить и дважды уменьшить. Кроме того, клиент мог
-- писать в honor_likes напрямую, обходя счётчик honor_board.likes.
--
-- Решение: блокируем строку поста на время переключения и разрешаем
-- менять honor_likes только через security definer RPC.
-- ===========================================================================

create or replace function public.honor_like(p_id bigint)
returns table (total_likes integer, liked boolean)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_uid uuid := auth.uid();
  v_likes integer;
  v_liked boolean := false;
begin
  if v_uid is null then
    raise exception 'войди, чтобы ставить лайки' using errcode = '42501';
  end if;

  -- сериализуем все переключения одного поста
  select b.likes into v_likes
    from public.honor_board b
   where b.id = p_id
   for update;

  if not found then
    raise exception 'запись не найдена' using errcode = 'P0002';
  end if;

  if exists (
    select 1 from public.honor_likes
     where post_id = p_id and user_id = v_uid
  ) then
    delete from public.honor_likes
     where post_id = p_id and user_id = v_uid;
    v_likes := greatest(v_likes - 1, 0);
  else
    insert into public.honor_likes (post_id, user_id)
    values (p_id, v_uid);
    v_likes := v_likes + 1;
    v_liked := true;
  end if;

  update public.honor_board
     set likes = v_likes
   where id = p_id;

  return query select v_likes, v_liked;
end;
$$;

grant execute on function public.honor_like(bigint) to authenticated;

-- Прямые insert/delete обходили бы пересчёт likes. Оставляем только RPC.
revoke insert, delete on public.honor_likes from authenticated;
drop policy if exists honor_likes_insert on public.honor_likes;
drop policy if exists honor_likes_delete on public.honor_likes;

-- Разово чиним счётчики, если они разошлись с фактическими лайками.
update public.honor_board b
   set likes = (select count(*)::integer from public.honor_likes l where l.post_id = b.id);
