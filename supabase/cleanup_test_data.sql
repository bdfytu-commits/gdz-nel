-- ===========================================================================
-- ГДЗ НЭЛ — финальная уборка тестовых данных
--
-- Удаляет:
--   * тестовых пользователей user1@gdz-nel.test и user2@gdz-nel.test
--     (профили, отзывы, фото-запросы, историю, достижения, логи админа
--     удалит каскад);
--   * тестовые платежи (payment_id = 'test-playwright...');
--   * тестовые отзывы (по авторам и по маркерам «playwright» /
--     «прод-проверка»).
--
-- НЕ трогает admin@gdz-nel.test и реальных пользователей.
--
-- Запуск: Supabase → SQL Editor → вставить целиком → Run.
-- Только посмотреть, без удаления: заменить `commit;` на `rollback;`.
-- Скрипт идемпотентный: повторный запуск ничего не сломает.
-- ===========================================================================

begin;

-- предохранитель: без админа не начинаем
do $$
begin
  if not exists (
    select 1 from auth.users where lower(email) = 'admin@gdz-nel.test'
  ) then
    raise exception 'admin@gdz-nel.test не найден — уборка отменена';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 1. до уборки
-- ---------------------------------------------------------------------------
select 'до: пользователи' as metric, count(*) as value
from auth.users
where lower(email) in ('user1@gdz-nel.test', 'user2@gdz-nel.test')

union all
select 'до: платежи (test-playwright)', count(*)
from public.payments
where payment_id ilike 'test-playwright%'
   or lower(coalesce(email, '')) in ('user1@gdz-nel.test', 'user2@gdz-nel.test')

union all
select 'до: отзывы (тестовые)', count(*)
from public.reviews r
where r.user_id in (
        select id from auth.users
        where lower(email) in ('user1@gdz-nel.test', 'user2@gdz-nel.test')
      )
   or r.text ilike '%playwright%'
   or r.text ilike '%прод-проверка%';

-- ---------------------------------------------------------------------------
-- 2. файлы фото-решений тестовых пользователей (bucket photos)
-- ---------------------------------------------------------------------------
delete from storage.objects
where bucket_id = 'photos'
  and owner_id::text in (
    select id::text from auth.users
    where lower(email) in ('user1@gdz-nel.test', 'user2@gdz-nel.test')
  );

-- ---------------------------------------------------------------------------
-- 3. платежи
-- ---------------------------------------------------------------------------
delete from public.payments
where payment_id ilike 'test-playwright%'
   or lower(coalesce(email, '')) in ('user1@gdz-nel.test', 'user2@gdz-nel.test');

-- ---------------------------------------------------------------------------
-- 4. отзывы
--    каскад удалит отзывы тестовых юзеров, но тестовые отзывы могли
--    остаться от других аккаунтов — чистим по маркерам
-- ---------------------------------------------------------------------------
delete from public.reviews
where user_id in (
        select id from auth.users
        where lower(email) in ('user1@gdz-nel.test', 'user2@gdz-nel.test')
      )
   or text ilike '%playwright%'
   or text ilike '%прод-проверка%';

-- ---------------------------------------------------------------------------
-- 5. пользователи (каскад: profiles, reviews, photo_requests, history,
--    achievements, admin_logs)
-- ---------------------------------------------------------------------------
delete from auth.users
where lower(email) in ('user1@gdz-nel.test', 'user2@gdz-nel.test');

-- ---------------------------------------------------------------------------
-- 6. после уборки
-- ---------------------------------------------------------------------------
select 'после: тестовые пользователи' as metric, count(*) as value
from auth.users
where lower(email) in ('user1@gdz-nel.test', 'user2@gdz-nel.test')

union all
select 'после: админ на месте', count(*)
from auth.users
where lower(email) = 'admin@gdz-nel.test'

union all
select 'после: платежи (test-playwright)', count(*)
from public.payments
where payment_id ilike 'test-playwright%'

union all
select 'после: отзывы (тестовые)', count(*)
from public.reviews
where text ilike '%playwright%' or text ilike '%прод-проверка%';

commit;

-- После уборки: зайти в Supabase → Authentication → Users и убедиться, что
-- admin@gdz-nel.test остался с ролью admin в public.profiles. Пароль админа
-- уже сменён вручную; если нет — сменить в Dashboard → Users → Reset password.
