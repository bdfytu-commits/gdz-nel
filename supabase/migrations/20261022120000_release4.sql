-- ===========================================================================
-- ГДЗ НЭЛ 4.0 — геймификация, промокоды, рефералы, защита от DDoS.
--
-- Всё, что пользователь не должен менять себе сам (XP, стрик, PRO, коды
-- рефералов), защищено триггером protect_profile_fields и security definer
-- функциями. Прямой доступ к логам, банам и промокодам — только у админа.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 1. прогресс в профиле
-- ---------------------------------------------------------------------------
alter table public.profiles add column if not exists xp integer not null default 0;
alter table public.profiles add column if not exists streak_days integer not null default 0;
alter table public.profiles add column if not exists last_active_date date;
alter table public.profiles add column if not exists referral_code text;
alter table public.profiles add column if not exists referred_by uuid references auth.users (id) on delete set null;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.profiles'::regclass and conname = 'profiles_xp_check'
  ) then
    alter table public.profiles add constraint profiles_xp_check check (xp >= 0);
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.profiles'::regclass and conname = 'profiles_streak_check'
  ) then
    alter table public.profiles add constraint profiles_streak_check check (streak_days >= 0);
  end if;
end $$;

update public.profiles
   set referral_code = upper(substr(md5(id::text), 1, 8))
 where referral_code is null or referral_code = '';

create unique index if not exists profiles_referral_code_key
  on public.profiles (upper(referral_code))
  where referral_code is not null;

alter table public.profiles
  alter column referral_code set default upper(substr(md5(gen_random_uuid()::text), 1, 8));

-- ---------------------------------------------------------------------------
-- 2. XP-события: одна и та же задача/действие не начисляются повторно за день
-- ---------------------------------------------------------------------------
create table if not exists public.xp_events (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  amount integer not null check (amount > 0),
  kind text not null,
  ref text not null default '',
  day date not null default current_date,
  created_at timestamptz not null default now(),
  unique (user_id, kind, ref, day)
);

create index if not exists xp_events_user_idx on public.xp_events (user_id, created_at desc);
alter table public.xp_events enable row level security;

drop policy if exists xp_events_select on public.xp_events;
create policy xp_events_select on public.xp_events
  for select to authenticated
  using (user_id = auth.uid() or public.is_admin());

revoke all on public.xp_events from anon, authenticated;
grant select on public.xp_events to authenticated;

-- ---------------------------------------------------------------------------
-- 3. рефералы
-- ---------------------------------------------------------------------------
create table if not exists public.referrals (
  id bigint generated always as identity primary key,
  referrer_id uuid not null references auth.users (id) on delete cascade,
  referred_id uuid not null references auth.users (id) on delete cascade,
  reward_days integer not null default 3,
  created_at timestamptz not null default now(),
  unique (referred_id)
);

create index if not exists referrals_referrer_idx on public.referrals (referrer_id, created_at desc);
alter table public.referrals enable row level security;

drop policy if exists referrals_select on public.referrals;
create policy referrals_select on public.referrals
  for select to authenticated
  using (referrer_id = auth.uid() or referred_id = auth.uid() or public.is_admin());

revoke all on public.referrals from anon, authenticated;
grant select on public.referrals to authenticated;

-- ---------------------------------------------------------------------------
-- 4. промокоды
-- ---------------------------------------------------------------------------
create table if not exists public.promo_codes (
  id uuid primary key default gen_random_uuid(),
  code text not null,
  days integer not null default 10 check (days between 1 and 365),
  max_uses integer not null default 1 check (max_uses between 1 and 10000),
  uses integer not null default 0 check (uses >= 0),
  active boolean not null default true,
  expires_at timestamptz,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now()
);

create unique index if not exists promo_codes_code_key on public.promo_codes (upper(code));
create index if not exists promo_codes_created_idx on public.promo_codes (created_at desc);
alter table public.promo_codes enable row level security;

drop policy if exists promo_codes_admin_select on public.promo_codes;
create policy promo_codes_admin_select on public.promo_codes
  for select to authenticated using (public.is_admin());

drop policy if exists promo_codes_admin_insert on public.promo_codes;
create policy promo_codes_admin_insert on public.promo_codes
  for insert to authenticated with check (public.is_admin());

drop policy if exists promo_codes_admin_update on public.promo_codes;
create policy promo_codes_admin_update on public.promo_codes
  for update to authenticated using (public.is_admin()) with check (public.is_admin());

drop policy if exists promo_codes_admin_delete on public.promo_codes;
create policy promo_codes_admin_delete on public.promo_codes
  for delete to authenticated using (public.is_admin());

revoke all on public.promo_codes from anon, authenticated;
grant select, insert, update, delete on public.promo_codes to authenticated;

create table if not exists public.promo_redemptions (
  id bigint generated always as identity primary key,
  code_id uuid not null references public.promo_codes (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (code_id, user_id)
);

create index if not exists promo_redemptions_user_idx on public.promo_redemptions (user_id, created_at desc);
alter table public.promo_redemptions enable row level security;

drop policy if exists promo_redemptions_select on public.promo_redemptions;
create policy promo_redemptions_select on public.promo_redemptions
  for select to authenticated
  using (user_id = auth.uid() or public.is_admin());

revoke all on public.promo_redemptions from anon, authenticated;
grant select on public.promo_redemptions to authenticated;

-- ---------------------------------------------------------------------------
-- 5. логи запросов и баны IP
-- ---------------------------------------------------------------------------
create table if not exists public.request_logs (
  id bigint generated always as identity primary key,
  ip text not null,
  path text not null default '/',
  method text not null default 'GET',
  user_agent text,
  status integer not null default 200,
  is_ddos boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists request_logs_ip_time_idx on public.request_logs (ip, created_at desc);
create index if not exists request_logs_time_idx on public.request_logs (created_at desc);
alter table public.request_logs enable row level security;

drop policy if exists request_logs_admin_select on public.request_logs;
create policy request_logs_admin_select on public.request_logs
  for select to authenticated using (public.is_admin());

revoke all on public.request_logs from anon, authenticated;
grant select on public.request_logs to authenticated;

create table if not exists public.ip_bans (
  ip text primary key,
  banned_until timestamptz not null,
  reason text not null default 'rate limit',
  is_ddos boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists ip_bans_until_idx on public.ip_bans (banned_until);
alter table public.ip_bans enable row level security;

drop policy if exists ip_bans_admin_select on public.ip_bans;
create policy ip_bans_admin_select on public.ip_bans
  for select to authenticated using (public.is_admin());

drop policy if exists ip_bans_admin_delete on public.ip_bans;
create policy ip_bans_admin_delete on public.ip_bans
  for delete to authenticated using (public.is_admin());

revoke all on public.ip_bans from anon, authenticated;
grant select, delete on public.ip_bans to authenticated;

-- ---------------------------------------------------------------------------
-- 6. защита служебных полей профиля от подмены из браузера
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
  if auth.role() = 'service_role' or current_user = 'service_role' then
    return new;
  end if;
  if not public.is_admin() then
    new.role := old.role;
    new.ban := old.ban;
    new.email := old.email;
    new.terms_accepted := old.terms_accepted;
    new.is_premium := old.is_premium;
    new.premium_until := old.premium_until;
    new.xp := old.xp;
    new.streak_days := old.streak_days;
    new.last_active_date := old.last_active_date;
    new.referral_code := old.referral_code;
    new.referred_by := old.referred_by;
  end if;
  return new;
end;
$function$;

drop trigger if exists profiles_protect_fields on public.profiles;
create trigger profiles_protect_fields
  before update on public.profiles
  for each row execute function public.protect_profile_fields();

-- ---------------------------------------------------------------------------
-- 7. регистрация: код приглашения из metadata + награда пригласившему
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_ref uuid;
  v_code text;
begin
  v_code := upper(trim(coalesce(new.raw_user_meta_data ->> 'ref', '')));
  if v_code <> '' then
    select id into v_ref
      from public.profiles
     where upper(referral_code) = v_code
     limit 1;
    if v_ref = new.id then v_ref := null; end if;
  end if;

  insert into public.profiles (
    id, username, email, age, gender, favorite_subject, terms_accepted, referred_by
  )
  values (
    new.id,
    coalesce(nullif(new.raw_user_meta_data ->> 'username', ''), split_part(new.email, '@', 1)),
    new.email,
    nullif(new.raw_user_meta_data ->> 'age', '')::integer,
    nullif(new.raw_user_meta_data ->> 'gender', ''),
    nullif(new.raw_user_meta_data ->> 'favorite_subject', ''),
    coalesce((new.raw_user_meta_data ->> 'terms_accepted')::boolean, false),
    v_ref
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

create or replace function public.reward_referral()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  inserted int := 0;
  v_referrer uuid;
begin
  v_referrer := new.referred_by;
  if v_referrer is null or v_referrer = new.id then return new; end if;

  insert into public.referrals (referrer_id, referred_id, reward_days)
  values (v_referrer, new.id, 3)
  on conflict (referred_id) do nothing;
  get diagnostics inserted = row_count;

  if inserted > 0 then
    perform set_config('gdz.system', 'on', true);
    update public.profiles
       set is_premium = true,
           premium_until = greatest(coalesce(premium_until, now()), now()) + interval '3 days'
     where id = v_referrer;
  end if;
  return new;
end;
$$;

drop trigger if exists profiles_reward_referral on public.profiles;
create trigger profiles_reward_referral
  after insert on public.profiles
  for each row execute function public.reward_referral();

-- ---------------------------------------------------------------------------
-- 8. XP и стрики
-- ---------------------------------------------------------------------------
create or replace function public.award_xp(p_kind text, p_ref text default '')
returns table (xp integer, level integer, streak_days integer)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_uid uuid := auth.uid();
  v_amount int;
  v_ref text := left(coalesce(p_ref, ''), 200);
  v_inserted int := 0;
  v_xp int;
  v_streak int;
begin
  if v_uid is null then
    raise exception 'нужен вход в аккаунт' using errcode = '42501';
  end if;
  if exists (select 1 from public.profiles where id = v_uid and ban) then
    return;
  end if;

  v_amount := case lower(coalesce(p_kind, ''))
    when 'view' then 5
    when 'review' then 20
    when 'share' then 5
    when 'daily' then 10
    else 0
  end;
  if v_amount = 0 then
    raise exception 'неизвестное действие';
  end if;

  insert into public.xp_events (user_id, amount, kind, ref, day)
  values (v_uid, v_amount, lower(p_kind), v_ref, current_date)
  on conflict (user_id, kind, ref, day) do nothing;
  get diagnostics v_inserted = row_count;

  if v_inserted > 0 then
    perform set_config('gdz.system', 'on', true);
    update public.profiles set xp = xp + v_amount where id = v_uid;
  end if;

  select p.xp, p.streak_days into v_xp, v_streak from public.profiles p where p.id = v_uid;
  return query select coalesce(v_xp, 0), (coalesce(v_xp, 0) / 100) + 1, coalesce(v_streak, 0);
end;
$$;

create or replace function public.touch_streak()
returns table (xp integer, level integer, streak_days integer, last_active_date date)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_uid uuid := auth.uid();
  v_last date;
  v_streak int := 1;
  v_xp int := 0;
begin
  if v_uid is null then
    raise exception 'нужен вход в аккаунт' using errcode = '42501';
  end if;

  select p.last_active_date, p.streak_days, p.xp
    into v_last, v_streak, v_xp
    from public.profiles p where p.id = v_uid
    for update;

  if not found then
    return;
  end if;

  if v_last = current_date then
    return query select v_xp, (v_xp / 100) + 1, v_streak, v_last;
    return;
  end if;

  if v_last = current_date - 1 then
    v_streak := coalesce(v_streak, 0) + 1;
  else
    v_streak := 1;
  end if;

  perform set_config('gdz.system', 'on', true);
  update public.profiles
     set last_active_date = current_date,
         streak_days = v_streak
   where id = v_uid;

  -- ежедневный бонус начисляется отдельным XP-событием
  perform public.award_xp('daily', current_date::text);

  select p.xp into v_xp from public.profiles p where p.id = v_uid;
  return query select coalesce(v_xp, 0), (coalesce(v_xp, 0) / 100) + 1, v_streak, current_date;
end;
$$;

-- ---------------------------------------------------------------------------
-- 9. промокод → +N дней PRO
-- ---------------------------------------------------------------------------
create or replace function public.redeem_promo(p_code text)
returns table (code text, days integer, premium_until timestamptz)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_uid uuid := auth.uid();
  v_code text := upper(trim(coalesce(p_code, '')));
  v_row public.promo_codes%rowtype;
  v_until timestamptz;
begin
  if v_uid is null then
    raise exception 'войди в аккаунт, чтобы применить промокод' using errcode = '42501';
  end if;
  if v_code = '' then
    raise exception 'введи промокод';
  end if;
  if exists (select 1 from public.profiles where id = v_uid and ban) then
    raise exception 'аккаунт заблокирован';
  end if;

  select * into v_row
    from public.promo_codes
   where upper(code) = v_code
   for update;

  if not found then
    raise exception 'промокод не найден';
  end if;
  if not v_row.active then
    raise exception 'промокод отключён';
  end if;
  if v_row.expires_at is not null and v_row.expires_at <= now() then
    raise exception 'срок промокода истёк';
  end if;
  if v_row.uses >= v_row.max_uses then
    raise exception 'промокод уже использован максимальное число раз';
  end if;
  if exists (
    select 1 from public.promo_redemptions r
    where r.code_id = v_row.id and r.user_id = v_uid
  ) then
    raise exception 'ты уже применял этот промокод';
  end if;

  perform set_config('gdz.system', 'on', true);
  update public.profiles
     set is_premium = true,
         premium_until = greatest(coalesce(premium_until, now()), now())
                         + make_interval(days => v_row.days)
   where id = v_uid
   returning premium_until into v_until;

  update public.promo_codes set uses = uses + 1 where id = v_row.id;
  insert into public.promo_redemptions (code_id, user_id) values (v_row.id, v_uid);

  return query select v_row.code, v_row.days, v_until;
end;
$$;

-- ---------------------------------------------------------------------------
-- 10. публичный счётчик учеников (без раскрытия профилей)
-- ---------------------------------------------------------------------------
create or replace function public.get_user_count()
returns bigint
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select count(*)::bigint from public.profiles where coalesce(ban, false) = false;
$$;

-- ---------------------------------------------------------------------------
-- 11. права
-- ---------------------------------------------------------------------------
revoke all on function public.award_xp(text, text) from public, anon;
revoke all on function public.touch_streak() from public, anon;
revoke all on function public.redeem_promo(text) from public, anon;
revoke all on function public.get_user_count() from public;
revoke all on function public.reward_referral() from public, anon, authenticated;

grant execute on function public.award_xp(text, text) to authenticated;
grant execute on function public.touch_streak() to authenticated;
grant execute on function public.redeem_promo(text) to authenticated;
grant execute on function public.get_user_count() to anon, authenticated;
