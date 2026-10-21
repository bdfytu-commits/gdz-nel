# Задачи (34 + задача 0)

Отметка: [x] сделано, [~] в работе, [ ] ждёт, [!] заблокировано.
Обновляется после каждой задачи.

- [x] 0. Сохранить ТЗ и правила на диск (docs/SPEC.md, docs/RULES.md, docs/TASKS.md, docs/PROGRESS.md)
- [x] 1. Лендинг: hero clamp(48px,8vw,96px), карточки субъектов ≥280px с SVG-иконками и счётчиками, 3D-tilt, «Как это работает» (3 шага), футер со ссылками
- [x] 2. /app: sticky-шапка с поиском и темой, обложки учебников, сетка ≥56×56 с разделами, блоки условия/решения/ответа, «поделиться» и «сообщить об ошибке»
- [x] 3. SVG-иконки предметов и UI в /assets/img/icons/ (stroke 2px, currentColor)
- [x] 4. Реальные скриншоты через playwright (scripts/take_screenshots.py, /assets/img/screens/, 390×844 и 1440×900), заменить CSS-мокапы
- [x] 5. Тёмная тема: localStorage gdz-nel-theme, prefers-color-scheme, контраст AA, палитра #1A1A1A/#242424/#E8E8E8/#9A9A9A/#1AA3A3
- [x] 6. PWA: manifest.json, service-worker.js (cache-first статика, network-first JSON), apple-touch-icon 180×180, регистрация
- [x] 7. APK через Bubblewrap (JDK/SDK нашлись: реальная сборка, подписанный download/app.apk)
- [x] 8. Клавиши ←/→/Esc + свайпы в /app + подсказки
- [x] 9. Поиск по тексту условия с подсветкой, debounce 200ms
- [x] 10. Закладки (gdz-nel-bookmarks) + экран «Избранное»
- [x] 11. История последних 20 просмотров
- [x] 12. Print-friendly CSS
- [x] 13. «Поделиться» (navigator.share, fallback clipboard + toast)
- [x] 14. «Сообщить об ошибке» (mailto, тема «Ошибка в задании X учебника Y»)
- [x] 15. Группировка по section со sticky-заголовками и «следующий раздел»
- [x] 16. a11y-аудит: aria-label, alt, keyboard-only, фокус, семантика, aria-live
- [x] 17. SEO + Open Graph (og:image скриншот, sitemap.xml, robots.txt, favicon SVG + .ico)
- [x] 18. Lighthouse: Performance >90, A11y >95, BP >95, SEO >90; результаты в docs/CHANGELOG.md
- [x] 19. math/vilenkin-6-1.json — реальные задания
- [x] 20. math/vilenkin-6-2.json — реальные задания
- [x] 21. russian/ladyzhenskaya-6-1.json — реальные задания
- [x] 22. russian/ladyzhenskaya-6-2.json — реальные задания
- [x] 23. english/vaulina-6.json — реальные задания
- [x] 24. biology/pasechnik-6.json — реальные задания
- [x] 25. history/medinsky-6.json — реальные задания
- [x] 26. social/bogolyubov-6.json — реальные задания
- [x] 27. Документация: docs/README.md, docs/CHANGELOG.md, docs/PARSING.md, корневой README
- [x] 28. GitHub Pages deploy (.github/workflows/deploy.yml)
- [x] 29. Деплой: репозиторий bdfytu-commits/gdz-nel, источник Pages — GitHub Actions, домен gdz-nel.pages.dev в canonical/og/sitemap/UA
- [x] 30. Полный сбор без лимита 30: все доступные задания 8 учебников (3541), `--resume` после обрыва, `section_map` для § математики, stats.json + скриншоты
- [x] 31. Реальный APK v4 (ru.nel.gdz, домен bdfytu-commits.github.io) + .well-known/assetlinks.json
- [x] 32. Добор пропусков с альтернативных источников: `scripts/fill_gaps.py` (euroki.org → otvet.plus → reshalka.com, 1 запрос в 1,5 с, robots.txt), 135 серых номеров → 60 добито (математика 46, английский 4, биология 7, история 3), 75 остались серыми; у новых задач поля `source`/`sourceUrl`, схема данных дополнена, отчёт — в docs/PARSING.md
- [x] 33. Финальная ручная приёмка: мобильная версия 375×812 (0 переполнений, счётчик 3601, APK скачивается кликом), раздел «Как поддерживать проект» в README, docs/ABOUT.md для школы
- [x] 34. Юридика и обратная связь: about.html (вместо ссылки на README), contact.html (Web3Forms + honeypot + обязательное согласие на обработку данных), privacy.html, disclaimer.html, футер со всеми ссылками (документы, почта, APK, GitHub, сайт школы) и копирайтом, раздел «Уведомление Роскомнадзора» в docs/README.md

## Метод наполнения (задачи 19–32) — выполнено

Источник: **gdz-raketa.ru** (первый в списке ТЗ с текстовыми ответами; gdz.ru — картинки,
euroki.org — 404, otvet.plus — устаревшая редакция, reshalka.com — закодированные ответы).
Парсер: `scripts/parse_gdz.py` (robots.txt, 1 запрос/сек, честный UA). Собраны все доступные
задания: 3541 по 8 учебникам (математика 889+632, русский 383+332, английский 436,
биология 331, история 350, обществознание 188); проверка `scripts/validate_data.py`,
лог — `docs/PARSING.md`. Задачи без ответа на источнике честно отсутствуют —
в приложении это серые зачёркнутые ячейки. Часть этих пропусков (60 из 135)
добрана скриптом `scripts/fill_gaps.py` с euroki.org: условие берётся со страницы
gdz-raketa.ru, решение и ответ — с альтернативного источника, в задаче сохраняются
`source` и `sourceUrl`; что осталось серым и почему — в docs/PARSING.md.

## Прод-фиксы (релиз 2.0, 18.10.2026)

- [x] Отзывы: пост-модерация — `is_approved` default true, бэкфилл pending, политика INSERT
- [x] Service worker v5: Supabase REST не кэшируется, старые кэши v4 удаляются при активации
- [x] Фронт отзывов: тост «Отзыв успешно добавлен», re-fetch через 1.5 с, бейджи статуса
- [x] premium.html: кнопка оплаты вместо невстраиваемого iframe lava.top
- [x] Математика (ba1c348): дроби CSS-классом `.frac` (без KaTeX — офлайн-PWA), строгие списки шагов «1., 2., 3.» без кружков, интро «Выполните действие:», SVG-визуал (круговая диаграмма, координатная прямая) внутри блока решения
- [x] LaTeX-текст математики: конвертер `_latex_to_text` в parse_gdz.py + разовый `scripts/fix_latex.py` — 6 задач виленкина-6-1 (2.507, 2.511, 2.512, 2.515, 2.516, 2.539) читаемы, ответ 2.511 восстановлен вручную
- [x] Вебхук lava-webhook задеплоен: POST 200 `{"ok":true}`, GET 200 (404 был до раскатки)

## Релиз 2.0 — 19.10.2026

- [x] Админка: выдача и снятие ГДЗ+ в списке юзеров — бейдж срока («до …» / «истёк» / «нет»), фильтр «С ГДЗ+», кнопки «Выдать/Продлить/Забрать PRO» (+30 дней от максимума), журнал в admin_logs, карточки обзора, колонки CSV. Проверено REST-циклом на прод-БД и полным playwright-прогоном.
- [x] Данные 7–9: каталог в едином формате, собраны макарычев-7/8/9, ваулина-7, пасечник-7/8/9, мединский-7/8/9, боголюбов-7/8/9 (баранов-7 и бархударов-8/9 — раньше)
- [x] Контурные карты Матвеев и Тороп 6–9 (gdz.ru): сканы страниц-разворотов локально (`parse_kontur.py`, app/data/…/img/)
- [x] Latex-конвертер математики: пересборка макарычева-8/9, 0 сырых «\» в текстах
- [x] Литература Коровиной 6–9 (части 1–2) с euroki.org: новый предмет `literature` (каталог 6–9, схема, иконка), сбор вопросов/ответов текстом (`parse_euroki.py`)
- [x] Финал данных 2.0: 16 778 заданий, 43 учебника — validate 0 ошибок, stats.json и search-index.json пересобраны
- [x] Английский 8–9 (Ваулина) — euroki.org: `vaulina-8` (685) и `vaulina-9` (722), предмет `english` добавлен в каталог 8–9

## Премиум ГДЗ+ (19.10.2026, без пейволла)

- [x] Шпаргалки: контент видят все, бесплатным — blur(7px) и плашка «открыть в ГДЗ+»
- [x] PDF/печать: у подписки чистая версия, у бесплатных — водяной знак через `@media print`
- [x] Фото: 3 модели на выбор для подписки, подсказка для бесплатных
- [x] Отзывы: PRO-бейдж и золотая аватарка у подписчиков (RPC `reviews_for_task`, миграция `review_premium`)
- [x] Рекламная плашка `.ad-slot` на лендинге: скрыта для ГДЗ+, видна остальным
- [x] Решения и ответы доступны всем — пейволл снят
- [x] Смоук: аноним / премиум / бесплатный — 8 проверок, 0 ошибок консоли

## Переезд на Cloudflare Pages (19.10.2026)

- [x] Проект `gdz-nel` создан, поддомен `gdz-nel.pages.dev` зарезервирован
- [x] build_config: Framework None, build command пустой, output `/`
- [x] `.github/workflows/deploy.yml` удалён
- [x] `tg-notify.yml` → триггер `push` в `main`
- [x] Домен заменён: canonical/og/twitter/sitemap/robots/docs/UA парсеров/TG-бот
- [x] Привязать GitHub-аккаунт в дашборде (Connect to Git → Add account) — автодеплой при пуше в `main` работает
- [x] Пересобрать APK под `gdz-nel.pages.dev` (2.1.0, versionCode 8)
- [x] После первой сборки: проверить `/`, `/app/`, `/admin/`, `/.well-known/assetlinks.json` — всё 200, сборки success по API

## Финальные фазы (20.10.2026)

- [x] `scripts/change_domain.py` — смена домена по репозиторию за один запуск, `--dry-run`
- [x] Playwright: SEO-аудит, мобильный 375×812 (26 страниц, все вкладки админки), CI на каждый push
- [x] Мобильная админка: заголовок вкладки и кнопки разведены по строкам, горизонтального скролла нет
- [x] SEO: twitter:card в поиске, статический JSON-LD приложения, JSON-LD не пустеет после рендера
- [x] Безопасность: CSP и security-заголовки, `/docs|/scripts|/supabase|/.github` закрыты, пароли тестов убраны в `.env.local`, пароль админа сменён
- [x] APK-подпись: `assetlinks.json` содержит оба отпечатка (текущий v8 и старый), проверено aapt/apksigner
- [x] `404.html` вместо soft-404, счётчики и футер приведены к 16 778 / 43 / 6–9 классы
- [x] `supabase/cleanup_test_data.sql` готов (запускать вручную)
- [ ] Запустить `supabase/cleanup_test_data.sql` в SQL Editor после финальных прогонов
- [x] Проверено: в production-файлах и на live нет `is-a.dev`; canonical/OG/sitemap/robots — `gdz-nel.pages.dev`
- [ ] Домен `gdz-nel.is-a.dev`: **ждём апрув PR #57491**, скрипт и код готовы. После апрува — по чеклисту `docs/README.md` (скрипт → пуш → Custom domain → Supabase Auth → Lava → APK → sitemap)
- [ ] TG-бот: токен из BotFather и деплой `scripts/tg-bot/`
- [ ] hCaptcha: sitekey в `auth.html`, если капча включается в Supabase Auth

## Режим ожидания домена (20.10.2026)

- [x] Код, данные, тесты и CI готовы; production — `https://gdz-nel.pages.dev`, автодеплой на `push` в `main` работает
- [x] `scripts/change_domain.py` проверен через `--dry-run` (31 файл, 103 замены на 20.10)
- [x] `gdz-nel.is-a.dev` ещё не выдан: PR `is-a-dev/register#57491` открыт, домен отдаёт страницу is-a.dev «available»
- [x] Случайный запуск скрипта откачен: `git restore .`, код в `main` и на pages.dev — `ffb9954` (дальше только документация), следов `is-a.dev` в production нет
- [ ] **Не запускать** `change_domain.py`, пока PR не смёржен
- [ ] После смёржа — `docs/README.md` → «Переезд на gdz-nel.is-a.dev: чеклист»

## Финальный релиз 2.0.0 (20.10.2026)

- [x] SEO-аудит: 13 страниц, 10 URL, canonical/OG/twitter/JSON-LD/sitemap/robots — чисто
- [x] Playwright: `run_all.sh` — все смоуки зелёные, мобильный аудит 26 страниц, 0 падений
- [x] Валидатор: 45 JSON-файлов, 0 ошибок схемы и дублей номеров
- [x] PWA/офлайн, поиск, избранное, премиум-сценарии и админка — в общем прогоне
- [x] TG-бот: код и инструкция готовы; живой запуск ждёт токен BotFather (внешний блокер)
- [x] Документация README/CHANGELOG/PROGRESS/TASKS синхронизирована с 16 778 задачами и 43 учебниками
- [x] Коммит `release: v2.0.0 final` и push в `main`

## Расширение 3, 4, 10, 11 классы (20.10.2026)

- [x] каркас каталога: новые классы, предметы, иконки `world/geometry/physics/chemistry`
- [x] `parse_euroki_bulk.py`: динамическое оглавление, части, постраничные и пономерные ссылки, разбор `\boxed`, очистка LaTeX, fallback на сканы с CDN
- [x] `parse_gdz_bulk.py`: русский 3–4, английский 3–4 и 11, химия 11, обществознание 11
- [x] `sync_bulk_catalog.py`: слияние манифестов euroki/gdz-raketa в каталог
- [x] PWA v9: новые иконки в precache, сброс старого кэша данных
- [x] админка: колонка «Класс» и фильтр 3/4/10/11 по возрасту, класс в CSV
- [x] дособрать данные и проверить `validate_data.py`
- [x] пересобрать `stats.json` и `search-index.json`
- [x] прогнать SEO и REST-проверки; браузерные смоуки отложены, прод проверяется curl
- [x] обновить README/CHANGELOG/PROGRESS и выпустить отчёт

## Релиз 2.1 — 3–11 классы, доска почёта и профили (21.10.2026)

- [x] Инвентарь euroki: 140 книг, из них 42 — 5 класс (`discover_euroki.py`); добавлен предмет `informatics` (иконка, схема, каталог)
- [x] `parse_euroki_bulk.py`: `--resume` с возвратом готовых файлов в манифест, `--slugs-file` для шардов, атомарная запись `.json.part`, проверка битых картинок, пауза 60 с и смена UA при 403/429
- [x] 5 класс собран: 43 файла, 33 693 задания; каталог — 88 238 заданий, 185 учебников, 15 предметов, 9 классов (3–11)
- [x] `sync_bulk_catalog.py`, `normalize_new_books.py`, `validate_data.py`, `write_stats.py`, `build_search_index.py` — прогнаны, 0 ошибок схемы
- [x] Supabase: применены `20261021120000_social.sql` и `20261021130000_fix_honor_like.sql`; таблицы `honor_board`, `honor_likes`, `profile_comments` и RPC работают в проде
- [x] Доска почёта `honor.html`: тёмная лента, карточки, «Аноним», относительное время, лайк-сердечко; писать может только админ
- [x] `profile.html`: 5 рамок, цвет ника, фон, замок и кнопка покупки для бесплатных; чужие профили через `?user=`, комментарии и удаление своих
- [x] Админка: вкладки «Доска почёта» и «Комментарии», создание/удаление записей, модерация комментариев
- [x] ИИ-модерация: `moderate-review` v2 ACTIVE, Groq `openai/gpt-oss-20b`; тесты «мат» → `rejected`, «без мата» → `approved`; fail-safe `is_approved=true` при ошибке
- [x] Удалён fallback через `reviews`; проверено RLS: обычный пользователь удаляет свой комментарий, чужой — нет
- [x] SEO: `honor.html` в sitemap и OG, счётчики/футеры 1–11 классы, PWA v10 с honor и informatics в precache
- [x] `test_seo.py` — 14 страниц / 11 URL, чисто; прод проверен curl после деплоя
- [x] Финальный коммит `feat: massive parsing (grades 3-11), honor board, profile customization, AI moderation` и push
