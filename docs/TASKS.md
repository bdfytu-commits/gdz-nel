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
- [x] 29. Деплой: репозиторий bdfytu-commits/gdz-nel, источник Pages — GitHub Actions, домен bdfytu-commits.github.io/gdz-nel в canonical/og/sitemap/UA
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
