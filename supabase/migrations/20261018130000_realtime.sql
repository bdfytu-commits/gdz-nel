-- ===========================================================================
-- ГДЗ НЭЛ 2.0 — realtime для админки (Ф9.14)
--
-- Подписка на новые отзывы и запросы «решить по фото»: админка показывает
-- их сразу, без обновления страницы. RLS действует и на realtime: строки
-- приходят только тем, кому их отдал бы обычный SELECT (админам).
-- ===========================================================================

do $$
begin
  alter publication supabase_realtime add table public.reviews;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.photo_requests;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.events;
exception when duplicate_object then null;
end $$;
