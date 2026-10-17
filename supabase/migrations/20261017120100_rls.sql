-- ГДЗ НЭЛ: RLS и права доступа

alter table public.profiles enable row level security;
alter table public.reviews enable row level security;
alter table public.photo_requests enable row level security;

-- права на таблицы и функции
grant usage on schema public to anon, authenticated;
grant select, insert, update, delete on public.profiles to authenticated;
grant select, insert, update, delete on public.reviews to anon, authenticated;
grant select, insert, update, delete on public.photo_requests to authenticated;
grant execute on function public.is_admin() to anon, authenticated;
grant execute on function public.is_banned() to authenticated;
revoke execute on function public.admin_delete_user(uuid) from public;
grant execute on function public.admin_delete_user(uuid) to authenticated;

-- profiles: свои строки видят и правят владельцы, админ — всё; insert — только триггером
drop policy if exists profiles_select on public.profiles;
create policy profiles_select on public.profiles
  for select to authenticated
  using (id = auth.uid() or public.is_admin());

drop policy if exists profiles_update on public.profiles;
create policy profiles_update on public.profiles
  for update to authenticated
  using (id = auth.uid() or public.is_admin())
  with check (id = auth.uid() or public.is_admin());

drop policy if exists profiles_delete on public.profiles;
create policy profiles_delete on public.profiles
  for delete to authenticated
  using (public.is_admin());

-- reviews: одобренные видят все, свои — автор (включая «на проверке»), всё — админ
drop policy if exists reviews_select on public.reviews;
create policy reviews_select on public.reviews
  for select to anon, authenticated
  using (is_approved or user_id = auth.uid() or public.is_admin());

drop policy if exists reviews_insert on public.reviews;
create policy reviews_insert on public.reviews
  for insert to authenticated
  with check (
    user_id = auth.uid()
    and not public.is_banned()
    and is_approved = false
    and ai_status = 'pending'
  );

drop policy if exists reviews_update on public.reviews;
create policy reviews_update on public.reviews
  for update to authenticated
  using (public.is_admin())
  with check (public.is_admin());

drop policy if exists reviews_delete on public.reviews;
create policy reviews_delete on public.reviews
  for delete to authenticated
  using (public.is_admin());

-- photo_requests: свои + админ (для фото-логов в админке)
drop policy if exists photo_requests_select on public.photo_requests;
create policy photo_requests_select on public.photo_requests
  for select to authenticated
  using (user_id = auth.uid() or public.is_admin());

drop policy if exists photo_requests_insert on public.photo_requests;
create policy photo_requests_insert on public.photo_requests
  for insert to authenticated
  with check (user_id = auth.uid() and not public.is_banned());
