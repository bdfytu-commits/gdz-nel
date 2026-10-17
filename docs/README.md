# Документация ГДЗ НЭЛ

Что где лежит и для чего.

| файл | о чём |
| --- | --- |
| `SPEC.md` | техническое задание: структура, палитра, шрифты, функционал, формат JSON |
| `RULES.md` | правила работы над проектом (главнее промпта): чистая статика, ответы строчными, коммиты после задач |
| `TASKS.md` | список задач со статусами (0–31) |
| `PROGRESS.md` | что сделано / в работе / ждёт, известные ограничения |
| `CHANGELOG.md` | решения и результаты проверок по датам (a11y, Lighthouse, APK, данные) |
| `PARSING.md` | как собраны задания: источник, карта учебников, ограничения, запуск парсера |
| `data-schema.json` | JSON-схема данных сайта (проверяет `scripts/validate_data.py`) |

Пояснения по репозиторию целиком — в корневом `README.md`; сопровождение (добавить или
поправить задания, stats.json, пересборка APK) — там же, разделы «Как наполнить или
поправить задания» и «Пересборка APK».

## TWA и assetlinks: как убрать адресную строку

Приложение `download/app.apk` — TWA. Чтобы Android считал его доверенным и не показывал
адресную строку, он проверяет Digital Asset Links по адресу
`https://<origin>/.well-known/assetlinks.json`, где `<origin>` — **корень домена**.

Сейчас сайт — project-страница `https://bdfytu-commits.github.io/gdz-nel/`, её origin —
`bdfytu-commits.github.io`, а project-репозиторий не может положить файл в корень origin:
он отдаётся только по пути `/gdz-nel/.well-known/assetlinks.json`. Поэтому TWA может
открыться с адресной строкой. Два варианта решения на будущее:

### Вариант А — user-root репозиторий GitHub Pages (бесплатно)

1. Создать репозиторий `bdfytu-commits.github.io` (имя = `<username>.github.io`).
2. Перенести сайт в его корень: лендинг — `https://bdfytu-commits.github.io/`,
   приложение — `https://bdfytu-commits.github.io/app/` (путь `/gdz-nel/` уходит,
   старые ссылки перестанут работать).
3. Скопировать `/.well-known/assetlinks.json` в корень нового репозитория — файл начнёт
   отдаваться с `https://bdfytu-commits.github.io/.well-known/assetlinks.json`.
4. Обновить домен: `twa-manifest.json` (host, startUrl `/app/`), canonical/og/twitter,
   sitemap.xml, robots.txt и UA парсера; пересобрать APK (см. корневой README).

### Вариант Б — свой домен (надёжнее)

1. Купить домен и привязать к GitHub Pages: Settings → Pages → Custom domain
   (DNS: A-записи на IP GitHub Pages либо CNAME на `bdfytu-commits.github.io`).
2. Положить `.well-known/assetlinks.json` в корень сайта — на своём домене он отдаётся
   как `https://<домен>/.well-known/assetlinks.json`.
3. Обновить домен там же, что и в варианте А (манифест, canonical/og/sitemap/robots, UA),
   и пересобрать APK. Плюс: адрес не зависит от имени репозитория, HTTPS форсится
   галочкой Enforce HTTPS.

### Проверка (после любого варианта)

```bash
curl https://<origin>/.well-known/assetlinks.json   # 200 и JSON
apksigner verify --print-certs download/app.apk     # SHA-256 должен совпадать с JSON
```

Отпечаток в `assetlinks.json` уже соответствует подписи APK; при смене ключа —
обновить.
