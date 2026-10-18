-- ===========================================================================
-- ГДЗ НЭЛ 2.0 — подписка «ГДЗ+» (Lava.top)
--
-- 1) профиль получает флаг is_premium и срок premium_until;
-- 2) таблица payments — журнал платежей (вебхук lava-webhook);
-- 3) protect_profile_fields защищает подписку от подмены из клиента;
-- 4) RPC grant_premium — идемпотентная выдача подписки по email
--    (вызывает edge-функция под service-ролью).
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 1. профиль
-- ---------------------------------------------------------------------------
alter table public.profiles add column if not exists is_premium boolean not null default false;
alter table public.profiles add column if not exists premium_until timestamptz;

-- ---------------------------------------------------------------------------
-- 2. платежи
-- ---------------------------------------------------------------------------
create table if not exists public.payments (
  id bigint generated always as identity primary key,
  user_id uuid references auth.users (id) on delete set null,
  payment_id text,
  amount numeric(12, 2),
  status text not null default 'pending',
  email text,
  raw jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists payments_payment_id_key
  on public.payments (payment_id) where payment_id is not null;
create index if not exists payments_user_idx on public.payments (user_id);
create index if not exists payments_created_idx on public.payments (created_at desc);

alter table public.payments enable row level security;

-- каждый видит свои платежи, админ — все; вставка и правка только
-- service-ролью edge-функции (она RLS обходит)
drop policy if exists payments_select on public.payments;
create policy payments_select on public.payments
  for select to authenticated
  using (user_id = auth.uid() or public.is_admin());

-- ---------------------------------------------------------------------------
-- 3. protect_profile_fields: подписку нельзя включить себе из браузера
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
  -- service-роль edge-функций (вебхук оплаты) пишет в обход защиты
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
  end if;
  return new;
end;
$function$;

-- ---------------------------------------------------------------------------
-- 4. RPC выдачи подписки по email (идемпотентно по payment_id)
-- ---------------------------------------------------------------------------
create or replace function public.grant_premium(
  target_email text,
  days int default 30,
  payment text default null,
  amount_value numeric default null,
  pay_status text default 'success',
  payload jsonb default null
)
returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $function$
declare
  uid uuid;
begin
  if target_email is null or position('@' in target_email) = 0 then
    raise exception 'нужен email покупателя';
  end if;
  days := coalesce(nullif(days, 0), 30);

  select id into uid
    from public.profiles
   where lower(email) = lower(target_email)
   limit 1;

  insert into public.payments (user_id, payment_id, amount, status, email, raw)
  values (uid, payment, amount_value, pay_status, lower(target_email), payload)
  on conflict (payment_id) where payment_id is not null do nothing;

  if pay_status = 'success' then
    if uid is null then
      return null; -- платёж записан, пользователя с таким email нет — разберёт админ
    end if;
    perform set_config('gdz.system', 'on', true);
    update public.profiles
       set is_premium = true,
           premium_until = greatest(coalesce(premium_until, now()), now())
                           + make_interval(days => days)
     where id = uid;
  end if;

  return uid;
end;
$function$;

revoke all on function public.grant_premium(text, int, text, numeric, text, jsonb)
  from public, anon, authenticated;
grant execute on function public.grant_premium(text, int, text, numeric, text, jsonb)
  to service_role;
