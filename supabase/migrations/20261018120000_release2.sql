-- ============================================================================
-- ГДЗ НЭЛ 2.0 — миграция релиза: ачивки, история, аватары, логи, аналитика,
-- авто-бан, синхронизация ника, удаление своего аккаунта, рейтинг ачивок.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. profiles.avatar_url
-- ---------------------------------------------------------------------------
alter table public.profiles add column if not exists avatar_url text;

-- ---------------------------------------------------------------------------
-- 2. achievements — ачивки пользователей
-- ---------------------------------------------------------------------------
create table if not exists public.achievements (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  badge_type text not null,
  unlocked_at timestamptz not null default now(),
  unique (user_id, badge_type)
);

create index if not exists achievements_user_idx on public.achievements (user_id);
create index if not exists achievements_unlocked_idx on public.achievements (unlocked_at desc);

alter table public.achievements enable row level security;

drop policy if exists achievements_select_own on public.achievements;
create policy achievements_select_own on public.achievements
  for select to authenticated
  using (auth.uid() = user_id or public.is_admin());

-- insert/update/delete из клиента запрещены: только security definer триггеры

-- ---------------------------------------------------------------------------
-- 3. history — история просмотров задач
-- ---------------------------------------------------------------------------
create table if not exists public.history (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  task_id text not null,
  viewed_at timestamptz not null default now(),
  unique (user_id, task_id)
);

create index if not exists history_user_idx on public.history (user_id, viewed_at desc);

alter table public.history enable row level security;

drop policy if exists history_select_own on public.history;
create policy history_select_own on public.history
  for select to authenticated using (auth.uid() = user_id);

drop policy if exists history_insert_own on public.history;
create policy history_insert_own on public.history
  for insert to authenticated with check (auth.uid() = user_id);

drop policy if exists history_update_own on public.history;
create policy history_update_own on public.history
  for update to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists history_delete_own on public.history;
create policy history_delete_own on public.history
  for delete to authenticated using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 4. admin_logs — журнал действий администратора
-- ---------------------------------------------------------------------------
create table if not exists public.admin_logs (
  id bigint generated always as identity primary key,
  admin_id uuid not null references auth.users (id) on delete cascade,
  action text not null,
  target text,
  meta jsonb,
  created_at timestamptz not null default now()
);

create index if not exists admin_logs_created_idx on public.admin_logs (created_at desc);

alter table public.admin_logs enable row level security;

drop policy if exists admin_logs_select on public.admin_logs;
create policy admin_logs_select on public.admin_logs
  for select to authenticated using (public.is_admin());

drop policy if exists admin_logs_insert on public.admin_logs;
create policy admin_logs_insert on public.admin_logs
  for insert to authenticated
  with check (public.is_admin() and admin_id = auth.uid());

-- ---------------------------------------------------------------------------
-- 5. events — лёгкая собственная аналитика (просмотры, скачивания, виталки)
-- ---------------------------------------------------------------------------
create table if not exists public.events (
  id bigint generated always as identity primary key,
  name text not null,
  path text,
  user_id uuid references auth.users (id) on delete set null,
  meta jsonb,
  created_at timestamptz not null default now()
);

create index if not exists events_created_idx on public.events (created_at desc);
create index if not exists events_name_idx on public.events (name, created_at desc);

alter table public.events enable row level security;

drop policy if exists events_insert_any on public.events;
create policy events_insert_any on public.events
  for insert to anon, authenticated with check (true);

drop policy if exists events_select_admin on public.events;
create policy events_select_admin on public.events
  for select to authenticated using (public.is_admin());

-- ---------------------------------------------------------------------------
-- 6. строки-индексы для админки
-- ---------------------------------------------------------------------------
create index if not exists reviews_created_idx on public.reviews (created_at desc);
create index if not exists reviews_user_idx on public.reviews (user_id);
create index if not exists reviews_task_idx on public.reviews (task_id);
create index if not exists photo_requests_created_idx on public.photo_requests (created_at desc);
create index if not exists profiles_email_idx on public.profiles (lower(email));

-- ---------------------------------------------------------------------------
-- 7. бакет аватарок + политики «только своя папка»
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('avatars', 'avatars', true, 2097152, array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do nothing;

drop policy if exists avatars_insert_own on storage.objects;
create policy avatars_insert_own on storage.objects
  for insert to authenticated
  with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists avatars_update_own on storage.objects;
create policy avatars_update_own on storage.objects
  for update to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists avatars_delete_own on storage.objects;
create policy avatars_delete_own on storage.objects
  for delete to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists avatars_select_all on storage.objects;
create policy avatars_select_all on storage.objects
  for select to anon, authenticated
  using (bucket_id = 'avatars');

-- ---------------------------------------------------------------------------
-- 8. системный флаг для protect_profile_fields (авто-бан в обход защиты)
-- ---------------------------------------------------------------------------
create or replace function public.protect_profile_fields()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $function$
begin
  if current_setting('gdz.system', true) = 'on' then
    return new;
  end if;
  if not public.is_admin() then
    new.role := old.role;
    new.ban := old.ban;
    new.email := old.email;
    new.terms_accepted := old.terms_accepted;
  end if;
  return new;
end;
$function$;

-- ---------------------------------------------------------------------------
-- 9. выдача ачивок
-- ---------------------------------------------------------------------------
create or replace function public.award_achievement(uid uuid, badge text)
returns void
language sql
security definer
set search_path = public, pg_temp
as $$
  insert into public.achievements (user_id, badge_type) values (uid, badge)
  on conflict (user_id, badge_type) do nothing;
$$;

revoke all on function public.award_achievement(uuid, text) from public, anon, authenticated;

-- «Добро пожаловать» — при создании профиля
create or replace function public.profiles_welcome_achievement()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  perform public.award_achievement(new.id, 'welcome');
  return new;
end;
$$;

drop trigger if exists profiles_welcome on public.profiles;
create trigger profiles_welcome
  after insert on public.profiles
  for each row execute function public.profiles_welcome_achievement();

-- «Первый отзыв» — при первом отзыве
create or replace function public.reviews_review_achievement()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  perform public.award_achievement(new.user_id, 'review1');
  return new;
end;
$$;

drop trigger if exists reviews_review1 on public.reviews;
create trigger reviews_review1
  after insert on public.reviews
  for each row execute function public.reviews_review_achievement();

-- история задач: ежедневная ачивка + 10/100 задач + обрезка до 300 записей
create or replace function public.history_achievements()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  cnt int;
begin
  perform public.award_achievement(new.user_id, 'daily-' || to_char(now(), 'YYYY-MM-DD'));

  select count(distinct task_id) into cnt from public.history where user_id = new.user_id;
  if cnt >= 10 then
    perform public.award_achievement(new.user_id, 'tasks10');
  end if;
  if cnt >= 100 then
    perform public.award_achievement(new.user_id, 'tasks100');
  end if;

  delete from public.history
  where user_id = new.user_id
    and id not in (
      select id from public.history
      where user_id = new.user_id
      order by viewed_at desc
      limit 300
    );
  return new;
end;
$$;

drop trigger if exists history_achievements on public.history;
create trigger history_achievements
  after insert or update on public.history
  for each row execute function public.history_achievements();

-- авто-бан: 5 отклонённых ИИ отзывов → бан
create or replace function public.reviews_autoban()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  rejected_count int;
begin
  if (tg_op = 'INSERT' or old.ai_status is distinct from new.ai_status)
     and new.ai_status = 'rejected' then
    select count(*) into rejected_count
    from public.reviews
    where user_id = new.user_id and ai_status = 'rejected';
    if rejected_count >= 5 then
      perform set_config('gdz.system', 'on', true);
      update public.profiles set ban = true where id = new.user_id and ban is distinct from true;
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists reviews_autoban on public.reviews;
create trigger reviews_autoban
  after insert or update on public.reviews
  for each row execute function public.reviews_autoban();

-- синхронизация ника: профиль изменился → отзывы обновились
create or replace function public.profiles_username_sync()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if new.username is distinct from old.username then
    update public.reviews set username = new.username where user_id = new.id;
  end if;
  return new;
end;
$$;

drop trigger if exists profiles_username_sync on public.profiles;
create trigger profiles_username_sync
  after update on public.profiles
  for each row execute function public.profiles_username_sync();

-- ---------------------------------------------------------------------------
-- 10. удаление своего аккаунта + рейтинг ачивок
-- ---------------------------------------------------------------------------
create or replace function public.delete_own_account()
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if auth.uid() is null then
    raise exception 'требуется вход в аккаунт';
  end if;
  delete from auth.users where id = auth.uid();
end;
$$;

revoke all on function public.delete_own_account() from public, anon;
grant execute on function public.delete_own_account() to authenticated;

create or replace function public.achievement_top(limit_n integer default 10)
returns table (username text, badges bigint)
language sql
security definer
set search_path = public, pg_temp
as $$
  select coalesce(nullif(p.username, ''), 'ученик') as username, count(*)::bigint as badges
  from public.achievements a
  join public.profiles p on p.id = a.user_id
  where p.ban is not true
  group by 1
  order by badges desc, username
  limit least(greatest(limit_n, 1), 50);
$$;

grant execute on function public.achievement_top(integer) to anon, authenticated;

-- ---------------------------------------------------------------------------
-- 11. бэкфил ачивок для существующих пользователей
-- ---------------------------------------------------------------------------
insert into public.achievements (user_id, badge_type)
select id, 'welcome' from public.profiles
on conflict (user_id, badge_type) do nothing;

insert into public.achievements (user_id, badge_type)
select distinct user_id, 'review1' from public.reviews
on conflict (user_id, badge_type) do nothing;
