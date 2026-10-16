# Задачи (28 + задача 0)

Отметка: [x] сделано, [~] в работе, [ ] ждёт, [!] заблокировано.

- [x] 0. Сохранить ТЗ и правила на диск (docs/SPEC.md, docs/RULES.md, docs/TASKS.md, docs/PROGRESS.md)
- [x] 1. Улучшить лендинг (hero, крупные карточки с иконками и счётчиками, «как это работает», футер со ссылками)
- [x] 2. Улучшить /app (sticky-шапка с тенью, обложки-заглушки учебников, номера 56x56, группировка по разделам, блоки условия/решения/ответа, поделиться и сообщить об ошибке)
- [x] 3. SVG-иконки предметов и UI (/assets/img/icons/, stroke 2px, currentColor)
- [x] 4. Реальные скриншоты через playwright (scripts/take_screenshots.py, /assets/img/screens/, phone-frame на лендинге)
- [x] 5. Тёмная тема (переключатель, localStorage gdz-nel-theme, prefers-color-scheme, :root[data-theme="dark"], контраст AA)
- [x] 6. PWA (manifest.json, service-worker.js, регистрация, apple-touch-icon, офлайн)
- [!] 7. APK через Bubblewrap (заблокировано: нет JDK/Android SDK и sudo; заглушка + инструкция в docs)
- [x] 8. Клавиатурная навигация и свайпы (← → Esc, touch, подсказки)
- [x] 9. Улучшенный поиск (по номеру и тексту условия, подсветка, debounce 200ms)
- [x] 10. Закладки (localStorage gdz-nel-bookmarks, экран «Избранное»)
- [x] 11. История просмотров (20 последних, экран «Недавние»)
- [x] 12. Print-friendly CSS (@media print)
- [x] 13. Кнопка «поделиться» (navigator.share + clipboard fallback + toast)
- [x] 14. Кнопка «сообщить об ошибке» (mailto + issue-ссылка)
- [x] 15. Группировка заданий по главам (section в JSON, sticky-заголовки разделов)
- [x] 16. Accessibility-аудит (aria-label, alt, keyboard-only, focus visible, aria-live, семантика)
- [x] 17. SEO + Open Graph (og:*, twitter:card, favicon, sitemap.xml, robots.txt)
- [x] 18. Lighthouse-аудит (цели: P>90, A>95, BP>95, SEO>90; результаты в CHANGELOG)
- [x] 19. math/vilenkin-6-1.json — наполнение части 1
- [x] 20. math/vilenkin-6-2.json — наполнение части 2
- [x] 21. russian/ladyzhenskaya-6-1.json — наполнение части 1
- [x] 22. russian/ladyzhenskaya-6-2.json — наполнение части 2
- [x] 23. english/vaulina-6.json — наполнение
- [x] 24. biology/pasechnik-6.json — наполнение
- [x] 25. history/medinsky-6.json — наполнение
- [x] 26. social/bogolyubov-6.json — наполнение
- [x] 27. README + документация (docs/README.md, CHANGELOG.md, PARSING.md, корневой README)
- [x] 28. GitHub Pages deploy (.github/workflows/deploy.yml, инструкция в README)

## Метод наполнения (задачи 19–26)

Источники в порядке предпочтения:
1. Прямой парсинг HTML (requests + BeautifulSoup): gdz-raketa.ru, euroki.org, otvet.plus, reshalka.com
2. Если Cloudflare — playwright headless
3. Если не работает — генерация через ИИ с проверкой, поле source: "ai-generated"

Гигиена парсинга: robots.txt, rate limit 1 запрос/сек, честный User-Agent, при 429/403 — стоп и план Б,
лог в docs/PARSING.md. Валидация JSON через jsonschema. Первые 30 заданий каждого учебника — показать на проверку.
