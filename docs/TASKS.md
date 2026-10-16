# Задачи (28 + задача 0)

Отметка: [x] сделано, [~] в работе, [ ] ждёт, [!] заблокировано.
Обновляется после каждой задачи.

- [x] 0. Сохранить ТЗ и правила на диск (docs/SPEC.md, docs/RULES.md, docs/TASKS.md, docs/PROGRESS.md)
- [x] 1. Лендинг: hero clamp(48px,8vw,96px), карточки субъектов ≥280px с SVG-иконками и счётчиками, 3D-tilt, «Как это работает» (3 шага), футер со ссылками
- [x] 2. /app: sticky-шапка с поиском и темой, обложки учебников, сетка ≥56×56 с разделами, блоки условия/решения/ответа, «поделиться» и «сообщить об ошибке»
- [x] 3. SVG-иконки предметов и UI в /assets/img/icons/ (stroke 2px, currentColor)
- [x] 4. Реальные скриншоты через playwright (scripts/take_screenshots.py, /assets/img/screens/, 390×844 и 1440×900), заменить CSS-мокапы
- [x] 5. Тёмная тема: localStorage gdz-nel-theme, prefers-color-scheme, контраст AA, палитра #1A1A1A/#242424/#E8E8E8/#9A9A9A/#1AA3A3
- [ ] 6. PWA: manifest.json, service-worker.js (cache-first статика, network-first JSON), apple-touch-icon 180×180, регистрация
- [ ] 7. APK через Bubblewrap (если нет JDK/SDK — честно сказать и оставить заглушку)
- [ ] 8. Клавиши ←/→/Esc + свайпы в /app + подсказки
- [ ] 9. Поиск по тексту условия с подсветкой, debounce 200ms
- [ ] 10. Закладки (gdz-nel-bookmarks) + экран «Избранное»
- [ ] 11. История последних 20 просмотров
- [ ] 12. Print-friendly CSS
- [ ] 13. «Поделиться» (navigator.share, fallback clipboard + toast)
- [ ] 14. «Сообщить об ошибке» (mailto, тема «Ошибка в задании X учебника Y»)
- [ ] 15. Группировка по section со sticky-заголовками и «следующий раздел»
- [ ] 16. a11y-аудит: aria-label, alt, keyboard-only, фокус, семантика, aria-live
- [ ] 17. SEO + Open Graph (og:image скриншот, sitemap.xml, robots.txt, favicon SVG + .ico)
- [ ] 18. Lighthouse: Performance >90, A11y >95, BP >95, SEO >90; результаты в docs/CHANGELOG.md
- [ ] 19. math/vilenkin-6-1.json — реальные задания
- [ ] 20. math/vilenkin-6-2.json — реальные задания
- [ ] 21. russian/ladyzhenskaya-6-1.json — реальные задания
- [ ] 22. russian/ladyzhenskaya-6-2.json — реальные задания
- [ ] 23. english/vaulina-6.json — реальные задания
- [ ] 24. biology/pasechnik-6.json — реальные задания
- [ ] 25. history/medinsky-6.json — реальные задания
- [ ] 26. social/bogolyubov-6.json — реальные задания
- [ ] 27. Документация: docs/README.md, docs/CHANGELOG.md, docs/PARSING.md, корневой README
- [ ] 28. GitHub Pages deploy (.github/workflows/deploy.yml)

## Метод наполнения (задачи 19–26)

Источники в порядке предпочтения:
1. Прямой парсинг HTML (requests + BeautifulSoup): gdz-raketa.ru, euroki.org, otvet.plus, reshalka.com
2. Если Cloudflare — playwright headless
3. Если не работает — генерация с проверкой, поле source: "ai-generated"

Гигиена: уважать robots.txt, 1 запрос/сек, честный User-Agent, при 429/403 — стоп и план Б,
лог в docs/PARSING.md, валидация JSON через jsonschema. Первые 30 заданий каждого учебника — показать заказчику.
