-- ===========================================================================
-- ГДЗ НЭЛ 2.1 — доска почёта, кастомизация профиля и комментарии.
-- Идемпотентно: можно выполнять в SQL Editor повторно.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 0. Причина решения ИИ (видна в админке)
-- ---------------------------------------------------------------------------
alter table public.reviews add column if not exists ai_reason text;

-- ---------------------------------------------------------------------------
-- 1. Профиль: рамка, цвет ника, цвет фона
-- ---------------------------------------------------------------------------
alter table public.profiles add column if not exists border_type text not null default 'none';
alter table public.profiles add column if not exists nick_color text not null default '';
alter table public.profiles add column if not exists bg_color text not null default '';

alter table public.profiles drop constraint if exists profiles_border_type_check;
alter table public.profiles add constraint profiles_border_type_check
  check (border_type in ('none', 'gold', 'neon', 'fire', 'minimal'));

alter table public.profiles drop constraint if exists profiles_nick_color_check;
alter table public.profiles add constraint profiles_nick_color_check
  check (nick_color = '' or nick_color ~ '^#[0-9A-Fa-f]{6}$');

alter table public.profiles drop constraint if exists profiles_bg_color_check;
alter table public.profiles add constraint profiles_bg_color_check
  check (bg_color = '' or bg_color ~ '^#[0-9A-Fa-f]{6}$');

create or replace function public.profile_premium_active(p_id uuid)
returns boolean
language sql stable security definer
set search_path = public, pg_temp
as $$
  select coalesce(bool_and(is_premium and premium_until > now()), false)
    from public.profiles where id = p_id;
$$;

create or replace function public.guard_profile_customization()
returns trigger
language plpgsql security definer
set search_path = public, pg_temp
as $$
begin
  if (new.border_type is distinct from old.border_type
      or new.nick_color is distinct from old.nick_color
      or new.bg_color is distinct from old.bg_color)
     and auth.uid() is not null
     and not public.is_admin()
     and not public.profile_premium_active(old.id) then
    raise exception 'кастомизация доступна только с ГДЗ+' using errcode = '42501';
  end if;
  return new;
end;
$$;

drop trigger if exists profiles_guard_customization on public.profiles;
create trigger profiles_guard_customization
  before update on public.profiles
  for each row execute function public.guard_profile_customization();

-- ---------------------------------------------------------------------------
-- 2. Доска почёта
-- ---------------------------------------------------------------------------
create table if not exists public.honor_board (
  id bigint generated always as identity primary key,
  text text not null check (char_length(text) between 3 and 1200),
  likes integer not null default 0 check (likes >= 0),
  created_at timestamptz not null default now()
);

create index if not exists honor_board_created_idx on public.honor_board (created_at desc);

create table if not exists public.honor_likes (
  post_id bigint not null references public.honor_board (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);

alter table public.honor_board enable row level security;
alter table public.honor_likes enable row level security;

grant select on public.honor_board to anon, authenticated;
grant insert, update, delete on public.honor_board to authenticated;
grant select on public.honor_likes to authenticated;
grant insert, delete on public.honor_likes to authenticated;

drop policy if exists honor_board_select on public.honor_board;
create policy honor_board_select on public.honor_board
  for select to anon, authenticated using (true);

drop policy if exists honor_board_admin_write on public.honor_board;
create policy honor_board_admin_write on public.honor_board
  for all to authenticated
  using (public.is_admin())
  with check (public.is_admin());

drop policy if exists honor_likes_select on public.honor_likes;
create policy honor_likes_select on public.honor_likes
  for select to authenticated using (user_id = auth.uid());

drop policy if exists honor_likes_insert on public.honor_likes;
create policy honor_likes_insert on public.honor_likes
  for insert to authenticated with check (user_id = auth.uid());

drop policy if exists honor_likes_delete on public.honor_likes;
create policy honor_likes_delete on public.honor_likes
  for delete to authenticated using (user_id = auth.uid());

create or replace function public.honor_like(p_id bigint)
returns table (likes integer, liked boolean)
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

  return query select b.likes, v_liked from public.honor_board b where b.id = p_id;
end;
$$;

grant execute on function public.honor_like(bigint) to authenticated;

-- ---------------------------------------------------------------------------
-- 3. Комментарии к профилям
-- ---------------------------------------------------------------------------
create table if not exists public.profile_comments (
  id uuid primary key default gen_random_uuid(),
  target_profile_id uuid not null references public.profiles (id) on delete cascade,
  author_id uuid not null references auth.users (id) on delete cascade,
  text text not null check (char_length(text) between 2 and 800),
  created_at timestamptz not null default now()
);

create index if not exists profile_comments_target_idx
  on public.profile_comments (target_profile_id, created_at desc);

alter table public.profile_comments enable row level security;
grant select, insert, delete on public.profile_comments to authenticated;

drop policy if exists profile_comments_select on public.profile_comments;
create policy profile_comments_select on public.profile_comments
  for select to authenticated using (true);

drop policy if exists profile_comments_insert on public.profile_comments;
create policy profile_comments_insert on public.profile_comments
  for insert to authenticated
  with check (author_id = auth.uid() and not public.is_banned());

drop policy if exists profile_comments_delete on public.profile_comments;
create policy profile_comments_delete on public.profile_comments
  for delete to authenticated
  using (author_id = auth.uid() or public.is_admin());

-- Публичная карточка без email/возраста и прочих личных полей.
create or replace function public.profile_public(p_id uuid)
returns table (
  id uuid, username text, avatar_url text, border_type text,
  nick_color text, bg_color text, premium boolean, created_at timestamptz
)
language sql stable security definer
set search_path = public, pg_temp
as $$
  select p.id, p.username, p.avatar_url, p.border_type, p.nick_color,
         p.bg_color,
         coalesce(p.is_premium and p.premium_until > now(), false),
         p.created_at
    from public.profiles p
   where p.id = p_id;
$$;

grant execute on function public.profile_public(uuid) to anon, authenticated;

create or replace function public.profile_comments_list(p_target uuid)
returns table (
  id uuid, text text, created_at timestamptz,
  author_id uuid, author_name text, author_avatar text, author_premium boolean
)
language sql stable security definer
set search_path = public, pg_temp
as $$
  select c.id, c.text, c.created_at, c.author_id,
         coalesce(nullif(p.username, ''), 'Аноним') as author_name,
         p.avatar_url,
         coalesce(p.is_premium and p.premium_until > now(), false) as author_premium
    from public.profile_comments c
    left join public.profiles p on p.id = c.author_id
   where c.target_profile_id = p_target
   order by c.created_at desc
   limit 100;
$$;

grant execute on function public.profile_comments_list(uuid) to authenticated, anon;
