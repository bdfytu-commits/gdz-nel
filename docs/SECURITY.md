# Безопасность ГДЗ НЭЛ

Аудит: 2026-10-22 13:57 UTC. Скрипт: `scripts/audit_security.py`.

## Клиентский код

- просмотрено файлов `.html` / `.js`: **85**;
- найдено publishable-ключей: **1**;
- найдено секретных ключей/`service_role`: **0**.

В браузере используется только публикуемый ключ Supabase (`sb_publishable_…`). Он предназначен для клиента, доступ к данным ограничен RLS. Секретные ключи и `GROQ_API_KEY` живут только в переменных Supabase Edge Functions и в браузер не попадают.

Проверка `grep` по клиенту: секретов и служебных ключей нет.

## RLS в базе

- public-таблиц найдено: **17**;
- без RLS: **0**;
- с RLS, но без политик: **0**;
- политики с записью для `anon`: **3**.

| таблица | RLS | политик | запись anon |
|---|---:|---:|---:|
| `achievements` | да | 1 | нет |
| `admin_logs` | да | 2 | нет |
| `events` | да | 2 | **ДА** |
| `history` | да | 4 | нет |
| `honor_board` | да | 2 | **ДА** |
| `honor_likes` | да | 3 | нет |
| `ip_bans` | да | 2 | нет |
| `payments` | да | 1 | нет |
| `photo_requests` | да | 3 | нет |
| `profile_comments` | да | 3 | нет |
| `profiles` | да | 3 | нет |
| `promo_codes` | да | 4 | нет |
| `promo_redemptions` | да | 1 | нет |
| `referrals` | да | 1 | нет |
| `request_logs` | да | 1 | нет |
| `reviews` | да | 5 | **ДА** |
| `xp_events` | да | 1 | нет |

## Проверенные границы

- `profiles`: пользователь читает/правит только свой профиль, админ — все; `role`, `ban`, `email`, `is_premium`, `premium_until`, `xp`, `streak_days`, `referral_code`, `referred_by` защищены триггером от подмены из браузера.
- `reviews`: удаление и обновление чужих отзывов — только админ; INSERT — только свой и не забаненному.
- `profile_comments`: автор удаляет свой комментарий, чужой — только админ.
- `photo_requests`: свои записи и админ; удаление чужого — только админ.
- `request_logs`, `ip_bans`, `promo_codes`: чтение/управление — только админ; промокод применяется через security definer RPC `redeem_promo`.
- `xp_events`, `referrals`: клиент только читает свои; начисления — через security definer RPC/триггеры.
- storage `photos` / `avatars`: запись и удаление только в своей папке `<uid>/`.

## Ограничения

- RLS проверен статически по миграциям. Фактическое состояние проекта нужно подтвердить SQL-запросом из `docs/SECURITY.md` раздела «Проверка».
- Rate limit `log-request` работает после вызова Edge Function; на уровне CDN нужен Cloudflare WAF/Rate Limiting — он не заменяется клиентским логом.
- Промокоды и рефералы можно пытаться фармить новыми аккаунтами; включи подтверждение email в Supabase Auth, если начнётся злоупотребление.

## Проверка

```sql
select c.relname, c.relrowsecurity,
       (select count(*) from pg_policies p where p.tablename = c.relname) as policies
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'public' and c.relkind = 'r'
 order by c.relname;
```

Ожидается `relrowsecurity = true` у каждой таблицы и `policies > 0`.
