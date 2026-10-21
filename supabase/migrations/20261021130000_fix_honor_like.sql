-- Исправление honor_like: имя выходной колонки likes конфликтовало
-- с колонкой honor_board.likes, из-за чего RPC падал с 42702.
-- Возвращаем total_likes — явное имя без пересечения с таблицей.

drop function if exists public.honor_like(bigint);

create function public.honor_like(p_id bigint)
returns table (total_likes integer, liked boolean)
language plpgsql security definer
set search_path = public, pg_temp
as $$
declare
  v_uid uuid := auth.uid();
  v_liked boolean := false;
begin
  if v_uid is null then
    raise exception 'войди, чтобы ставить лайки' using errcode = '42501';
  end if;

  if exists (select 1 from public.honor_likes where post_id = p_id and user_id = v_uid) then
    delete from public.honor_likes where post_id = p_id and user_id = v_uid;
    update public.honor_board set likes = greatest(likes - 1, 0) where id = p_id;
  else
    insert into public.honor_likes (post_id, user_id) values (p_id, v_uid);
    update public.honor_board set likes = likes + 1 where id = p_id;
    v_liked := true;
  end if;

  return query
    select b.likes, v_liked
      from public.honor_board b
     where b.id = p_id;
end;
$$;

grant execute on function public.honor_like(bigint) to authenticated;
