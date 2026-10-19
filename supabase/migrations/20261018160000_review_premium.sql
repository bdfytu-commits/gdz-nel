-- ===========================================================================
-- ГДЗ НЭЛ 2.0 — отзывы с пометкой автора «ГДЗ+» (PRO).
--
-- profiles закрыт RLS: чужой профиль из браузера не прочитать. Поэтому
-- статус подписки авторов отзывов отдаёт security definer RPC: он умеет
-- обойти RLS profiles, но отдаёт только одобренные отзывы (и собственные,
-- как политика reviews_select).
--
-- Клиент (app/assets/script.js) при отсутствии функции падает обратно
-- на обычный select — фича просто не показывается, ничего не ломается.
-- ===========================================================================

create or replace function public.reviews_for_task(p_task_id text)
returns table (
  id uuid,
  task_id text,
  user_id uuid,
  username text,
  rating integer,
  "text" text,
  ai_status text,
  is_approved boolean,
  created_at timestamptz,
  author_premium boolean
)
language sql
security definer
stable
set search_path = public, pg_temp
as $function$
  select
    r.id, r.task_id, r.user_id, r.username, r.rating, r."text",
    r.ai_status, r.is_approved, r.created_at,
    coalesce(p.is_premium and p.premium_until > now(), false) as author_premium
  from public.reviews r
  left join public.profiles p on p.id = r.user_id
  where r.task_id = p_task_id
    and (r.is_approved or r.user_id = auth.uid())
  order by r.created_at desc
  limit 50;
$function$;

revoke all on function public.reviews_for_task(text) from public;
grant execute on function public.reviews_for_task(text) to anon, authenticated;
