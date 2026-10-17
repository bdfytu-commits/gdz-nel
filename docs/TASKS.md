# Задачи (28 + задача 0)

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

## Метод наполнения (задачи 19–26) — выполнено

Источник: **gdz-raketa.ru** (первый в списке ТЗ с текстовыми ответами; gdz.ru — картинки,
euroki.org — 404, otvet.plus — устаревшая редакция, reshalka.com — закодированные ответы).
Парсер: `scripts/parse_gdz.py` (robots.txt, 1 запрос/сек, честный UA). Собрано по 30 заданий
на каждый из 8 учебников = 240 заданий; проверка `scripts/validate_data.py`, лог — `docs/PARSING.md`.
Задачи без ответа на источнике честно отсутствуют — в приложении это серые зачёркнутые ячейки.
