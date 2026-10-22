# Supabase: база, авторизация, функции

Проект: `qncqeoklwblztbnoktwk` (регион eu-west-1), API —
`https://qncqeoklwblztbnoktwk.supabase.co`.

На 21.10.2026 миграции `social` и `fix_honor_like` применены, Edge Function
`moderate-review` версии 2 — `ACTIVE` (модель `openai/gpt-oss-20b`).

В репозитории лежит только **publishable**-ключ (`assets/supabase.js`) — он публичный
по замыслу. Секретные ключи (`sb_secret_…`) в код и коммиты не попадают: в браузере они
не нужны, а функциям секретный ключ выдаёт сам Supabase (или он задаётся через
`supabase secrets set`, см. ниже).

## Что уже настроено

Миграции в `supabase/migrations/` (применены 17–21.10.2026, порядок — по имени файла):

| Файл | Что делает |
| --- | --- |
| `20261017120000_schema.sql` | таблицы `profiles`, `reviews`, `photo_requests`, триггеры (`handle_new_user`, `protect_profile_fields`, `fill_review_username`), RPC `admin_delete_user` |
| `20261017120100_rls.sql` | RLS и 13 политик: свои данные — владельцу, отзывы — всем после одобрения, админу — всё |
| `20261017120200_storage.sql` | публичный бакет `photos` (5 МБ, jpeg/png/webp), запись/удаление — только своя папка `<uid>/` |
| `20261017120300_webhook.sql` | `pg_net`-триггер: после INSERT в `reviews` зовёт Edge Function `moderate-review` |
| `20261017120400_admin_storage.sql` | админ может удалять чужие фото из storage и записи `photo_requests` |
| `20261018160000_review_premium.sql` | RPC `reviews_for_task` с флагом `is_premium` автора — PRO-бейджи в отзывах |
| `20261021120000_social.sql` | доска почёта (`honor_board`, `honor_likes`), комментарии профилей (`profile_comments`), кастомизация профиля, RPC `honor_like`, `profile_public`, `profile_comments_list` |
| `20261021130000_fix_honor_like.sql` | исправление конфликта имени `likes` в `honor_like` (RPC падал с 42702) |

Если проект пересоздаётся: применить файлы по порядку — вставить содержимое
в SQL Editor или выполнить `supabase db push` (после `supabase link`).

Ключевые правила RLS:

- `profiles`: видит и правит свой профиль, админ — все; сам себе запрещено менять
  `role`, `ban`, `email`, `terms_accepted` (триггер).
- `reviews`: опубликованные видит каждый (даже аноним), свой отзыв автор видит с любым
  статусом; INSERT — только залогиненному и не забаненному (пост-модерация:
  `is_approved=true`, `ai_status='pending'`); UPDATE/DELETE — только админу.
- `honor_board`: читают все, пишет и удаляет только админ; `honor_likes`: каждый
  видит и меняет только свой лайк, счётчик обновляет RPC `honor_like`.
- `profile_comments`: читают все авторизованные, автор удаляет свой комментарий,
  админ — любой.
- `photo_requests`: свои записи + админ; insert — не забаненным.
- Storage: каждый загружает и удаляет файлы только в своей папке; админ — любые.

Имя автора в отзыве всегда берётся из профиля (триггер `fill_review_username`),
клиент его не передаёт.

## Настройка дашборда (один раз, вручную)

1. **Authentication → Sign In / Up → Email** — выключить «Confirm email»
   (`mailer_autoconfirm`), иначе после регистрации придётся подтверждать почту.
2. **Authentication → URL Configuration** — Site URL:
   `https://gdz-nel.pages.dev/`; Redirect URLs:
   `https://gdz-nel.pages.dev/**` и `http://localhost:8000/**`.
3. **Назначить админа** (SQL Editor):

   ```sql
   update public.profiles set role = 'admin' where email = 'bdfy.tu@yandex.ru';
   ```

## Деплой Edge Functions (делает владелец проекта)

Нужен Supabase CLI (`supabase --version`), дальше из корня репозитория:

```bash
supabase login
supabase link --project-ref qncqeoklwblztbnoktwk

# секреты функций (значения — не коммитить никуда)
supabase secrets set GROQ_API_KEY=gsk_...

# на всякий случай: если runtime не отдаёт встроенный service-ключ,
# задать его отдельно (Project Settings -> API Keys -> secret keys)
# supabase secrets set SUPABASE_SECRET_KEY=sb_secret_...

# деплой
supabase functions deploy moderate-review --no-verify-jwt
supabase functions deploy solve-photo
```

Пояснения:

- `verify_jwt` уже прописан в `supabase/config.toml`; флаг у `moderate-review` —
  страховка для старых версий CLI.
- Функции читают сервисный ключ из встроенной переменной
  `SUPABASE_SERVICE_ROLE_KEY` (её Supabase подставляет сам), а если её нет —
  из `SUPABASE_SECRET_KEY`.
- Вебхук уже создан миграцией через `pg_net` — **не создавай второй** Database
  Webhook в дашборде, модерация запустится дважды (впрочем, повторный вызов
  пропускается: функция реагирует только на `ai_status='pending'`).
- Секреты применяются к новым вызовам сразу, передеплой не нужен. Список имён —
  `supabase secrets list` (значения не показываются).

## Как это работает

**Отзывы.** Клиент пишет отзыв в `reviews` (`pending`). Триггер вызывает
`moderate-review`; функция перечитывает отзыв из базы по id (телу вебхука не
доверяет), спрашивает Groq и ставит `is_approved` + `ai_status`. Модель по ТЗ —
`openai/gpt-oss-20b`, запасные — `openai/gpt-oss-120b` и
`openai/gpt-oss-safeguard-20b` (перебор при 4xx; свой выбор — секрет `GROQ_MODEL`).
`llama-3.1-8b-instant` отключена Groq для self-serve с 16.08.2026.
При недоступности Groq срабатывает fail-safe: отзыв публикуется, причина
пишется в `reviews.ai_reason` и видна в админке.

Промпт модерации (не менять без нужды):

> Ты модератор школьного сайта ГДЗ. Если текст содержит мат, оскорбления, рекламу,
> спам или бред — ответь строго 'REJECT'. Если это адекватная критика или похвала
> по теме — ответь строго 'APPROVE'.

**Фото.** `photo.html` загружает снимок в `photos/<uid>/…`, получает публичный URL
и зовёт `solve-photo`. Функция проверяет JWT, бан, что URL — из папки этого
пользователя, и лимит: 5 фото за сутки (`photo_requests`). Дальше скачивает фото,
отправляет в Groq Vision и записывает пару «фото + ответ» в `photo_requests`
(только после успешного ответа — неудачные попытки лимит не съедают). Модель по
ТЗ — `llama-3.2-11b-vision-preview`, запасные — `llama-4-scout-17b-16e-instruct`,
`llama-3.2-90b-vision-preview` (секрет `GROQ_VISION_MODEL`).

Промпт Vision (не менять без нужды):

> Распознай задачу на фото. Если это математика/физика/химия — реши пошагово.
> Если это код — найди ошибки и предложи исправленный вариант. Если текст
> нечитаем — так и скажи.

## Проверка после деплоя

1. Под тестовым аккаунтом оставить отзыв в приложении, через ~5 секунд обновить
   страницу: отзыв либо опубликован, либо помечен «отклонён».
2. Логи: дашборд → Edge Functions → Logs (или `supabase functions logs moderate-review`).
3. Быстрый ручной вызов модерации (JWT не нужен):

   ```bash
   curl -sS -X POST "https://qncqeoklwblztbnoktwk.supabase.co/functions/v1/moderate-review" \
     -H "Content-Type: application/json" -d '{"id":"<uuid отзыва>"}'
   ```

   Чтобы перепрогнать отзыв: `update public.reviews set ai_status='pending', is_approved=false where id='…';`
4. Если отзывы висят в «на pending»: проверить, что функция задеплоена
   (`curl -i` по адресу вернёт 400/500, а не 404), что задан `GROQ_API_KEY`,
   и посмотреть логи функции.
5. Лимит фото: `select count(*) from public.photo_requests where user_id='…' and created_at > now() - interval '1 day';` — при 5 и больше функция вернёт «Лимит 5 фото в день».

## Уборка тестовых данных (20.10.2026)

Готовый скрипт: `supabase/cleanup_test_data.sql` (запускать в SQL Editor целиком).

Что делает:

- удаляет `user1@gdz-nel.test` и `user2@gdz-nel.test` (каскад: профили, отзывы,
  фото-запросы, история, достижения, логи);
- удаляет платежи `test-playwright*` и платежи с тестовыми email;
- удаляет тестовые отзывы по маркерам `playwright` / `прод-проверка`;
- чистит файлы из бакета `photos`, принадлежащие тестовым юзерам;
- **не трогает** `admin@gdz-nel.test`;
- печатает счётчики до/после и делает `commit`.

Проверка после запуска: `admin@gdz-nel.test` существует, в `public.profiles`
у него `is_admin = true`. Пароль админа уже сменён 20.10.2026 (старый был
засвечен в публичном репозитории); при необходимости — Dashboard → Users →
Reset password.

## OG-картинки: `generate-og`

Функция лежит в `supabase/functions/generate-og/index.ts`, но **не задеплоена**.
Она отдаёт SVG 1200×630 по query-параметрам `title`, `subtitle`, `badge`.

Для деплоя нужны:

- `SUPABASE_ACCESS_TOKEN` — personal access token из Supabase Dashboard →
  Account → Access Tokens;
- project ref `qncqeoklwblztbnoktwk` (или `supabase link --project-ref ...`);
- Supabase CLI;
- для PNG-площадок (Telegram/VK) — либо статические `seo/og/*.png`, либо
  отдельный рендер SVG → PNG (resvg-wasm). Сейчас используются статические PNG.

Команды:

```bash
supabase link --project-ref qncqeoklwblztbnoktwk
supabase functions deploy generate-og --no-verify-jwt
```

Секреты функции не нужны: она не обращается к БД. Проверка после деплоя:

```bash
curl -sI 'https://qncqeoklwblztbnoktwk.supabase.co/functions/v1/generate-og?title=ГДЗ%20НЭЛ'
# content-type: image/svg+xml
```
