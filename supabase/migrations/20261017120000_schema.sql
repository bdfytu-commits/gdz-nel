-- ГДЗ НЭЛ: схема БД (профили, отзывы, фото-запросы)
-- Порядок применения: 20261017120000 → 20261017120100 → 20261017120200 → 20261017120300
-- Либо вставить содержимое по очереди в SQL Editor, либо `supabase db push`.

-- профили пользователей (1:1 с auth.users)
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  username text not null default '',
  email text,
  age integer check (age between 1 and 120),
  gender text check (gender in ('м', 'ж')),
  favorite_subject text,
  role text not null default 'user' check (role in ('user', 'admin')),
  ban boolean not null default false,
  terms_accepted boolean not null default false,
  created_at timestamptz not null default now()
);

-- отзывы к заданиям; task_id = "<id учебника>:<номер задания>", например "vilenkin-6-1:1.12"
create table if not exists public.reviews (
  id uuid primary key default gen_random_uuid(),
  task_id text not null,
  user_id uuid not null references auth.users (id) on delete cascade,
  username text not null default '',
  rating integer not null check (rating between 1 and 5),
  "text" text not null check (char_length("text") between 3 and 2000),
  ai_status text not null default 'pending' check (ai_status in ('pending', 'approved', 'rejected')),
  is_approved boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists reviews_task_idx on public.reviews (task_id, created_at desc);
create index if not exists reviews_status_idx on public.reviews (ai_status);
create index if not exists reviews_user_idx on public.reviews (user_id);

-- запросы «реши по фото»
create table if not exists public.photo_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  image_url text not null,
  ai_response text,
  created_at timestamptz not null default now()
);

create index if not exists photo_requests_user_idx on public.photo_requests (user_id, created_at desc);

-- helper: текущий пользователь — админ? (security definer — без рекурсии в RLS профилей)
create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and role = 'admin'
  );
$$;

-- helper: текущий пользователь забанен?
create or replace function public.is_banned()
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select coalesce((select ban from public.profiles where id = auth.uid()), false);
$$;

-- профиль создаётся автоматически при регистрации
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  insert into public.profiles (id, username, email, age, gender, favorite_subject, terms_accepted)
  values (
    new.id,
    coalesce(nullif(new.raw_user_meta_data ->> 'username', ''), split_part(new.email, '@', 1)),
    new.email,
    nullif(new.raw_user_meta_data ->> 'age', '')::integer,
    nullif(new.raw_user_meta_data ->> 'gender', ''),
    nullif(new.raw_user_meta_data ->> 'favorite_subject', ''),
    coalesce((new.raw_user_meta_data ->> 'terms_accepted')::boolean, false)
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- пользователь не может сам менять себе role/ban/email/terms_accepted
create or replace function public.protect_profile_fields()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if not public.is_admin() then
    new.role := old.role;
    new.ban := old.ban;
    new.email := old.email;
    new.terms_accepted := old.terms_accepted;
  end if;
  return new;
end;
$$;

drop trigger if exists protect_profile_fields on public.profiles;
create trigger protect_profile_fields
  before update on public.profiles
  for each row execute function public.protect_profile_fields();

-- имя автора отзыва берётся из профиля, а не из запроса клиента
create or replace function public.fill_review_username()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  new.username := coalesce(
    (select p.username from public.profiles p where p.id = new.user_id),
    'Аноним'
  );
  return new;
end;
$$;

drop trigger if exists fill_review_username on public.reviews;
create trigger fill_review_username
  before insert on public.reviews
  for each row execute function public.fill_review_username();

-- RPC: полное удаление пользователя админом (профиль уходит каскадом)
create or replace function public.admin_delete_user(target uuid)
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if not public.is_admin() then
    raise exception 'только администратор может удалять пользователей';
  end if;
  if target = auth.uid() then
    raise exception 'нельзя удалить свой аккаунт';
  end if;
  delete from auth.users where id = target;
end;
$$;
