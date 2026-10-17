# ГДЗ НЭЛ

Статический сайт с готовыми домашними заданиями для 6 класса МАОУ «Новосибирский экономический лицей».
Никакого бэкенда: HTML + CSS + vanilla JS, данные — JSON-файлы, читаются через fetch.
Без фреймворков, сборщиков и минификации — так требует ТЗ.

Что уже есть:

- лендинг с описанием и живыми счётчиками (3601 задание, 8 учебников, 6 предметов);
- приложение `/app`: выбор предмета → учебник → сетка номеров → задание (условие, пошаговое решение, ответ);
- поиск по номерам и по тексту условия с подсветкой, избранное, история просмотров;
- тёмная тема, печатный вид, клавиши ←/→/Esc, свайпы, «поделиться», «сообщить об ошибке»;
- PWA (офлайн-режим) и подписанный `download/app.apk` для Android;
- данные собраны парсером с gdz-raketa.ru: все задания, доступные на источнике (3541 —
  разбивка по учебникам и правила обхода в docs/PARSING.md), ещё 60 пропусков добрано
  с euroki.org (`scripts/fill_gaps.py`) — всего 3601 задание.

## Структура

```
gdz-nel/
  index.html                  лендинг
  assets/                     стили, скрипт, эмблема, скриншоты лендинга
  download/app.apk            подписанный APK (Bubblewrap)
  app/
    index.html                приложение с ГДЗ
    assets/                   стили и скрипт приложения
    data/
      catalog.json            каталог: предметы, учебники, файлы заданий
      stats.json              счётчики заданий (генерируется)
      math/                   vilenkin-6-1.json, vilenkin-6-2.json
      russian/                ladyzhenskaya-6-1.json, ladyzhenskaya-6-2.json
      english/                vaulina-6.json
      biology/                pasechnik-6.json
      history/                medinsky-6.json
      social/                 bogolyubov-6.json
    manifest.json             PWA-манифест
    service-worker.js         офлайн-кэш (статика cache-first, JSON network-first)
  scripts/
    parse_gdz.py              парсер заданий (gdz-raketa.ru)
    validate_data.py          проверка JSON по схеме docs/data-schema.json
    write_stats.py            пересчёт app/data/stats.json
    take_screenshots.py       скриншоты лендинга (playwright)
    build_apk.sh              сборка APK (Bubblewrap)
  docs/                       ТЗ, правила, задачи, прогресс, лог парсинга
  .well-known/assetlinks.json Digital Asset Links для TWA-приложения
  .github/workflows/deploy.yml  публикация на GitHub Pages
```

## Запуск локально

```bash
cd gdz-nel
uv run python -m http.server 8000
```

Открыть http://localhost:8000

Важно: открывать index.html двойным кликом нельзя — браузер запрещает fetch с file://.
Нужен любой локальный сервер или хостинг.

## Деплой

GitHub Pages: репозиторий → Settings → Pages → Source: «GitHub Actions». Workflow
`.github/workflows/deploy.yml` сам проверит данные и опубликует сайт при пуше в `main`.

Cloudflare Pages: подключить репозиторий, build command оставить пустым, output directory — корень.
Все пути относительные, работает и там, и там.

После деплоя домен сайта прописан в canonical/og/twitter/sitemap/robots —
при смене адреса (см. «TWA и assetlinks» в docs/README.md) обновить и там.

## Формат данных

`app/data/catalog.json` — каталог предметов:

```json
{
  "id": "math",
  "title": "Математика",
  "active": true,
  "textbooks": [
    { "id": "vilenkin-6-1", "title": "Виленкин. Часть 1",
      "author": "Виленкин Н.Я., Жохов В.И., Чесноков А.С.",
      "year": "2021–2026", "file": "math/vilenkin-6-1.json" }
  ]
}
```

`active: false` — карточка предмета становится серой с надписью «скоро».

Файл учебника (`app/data/<предмет>/<учебник>.json`):

```json
{
  "subject": "math",
  "textbook": "vilenkin-6-1",
  "author": "Виленкин Н.Я., Жохов В.И., Чесноков А.С.",
  "year": "2021–2026",
  "part": 1,
  "source": "parsed",
  "sourceUrl": "https://gdz-raketa.ru/matematika/6-klass/uchebnik-vilenkin/",
  "parsedAt": "2026-10-16T21:14:00Z",
  "tasks": [
    {
      "number": "1.1",
      "section": "§1. Вычисления и построения",
      "condition": "текст условия",
      "solution": "шаг 1\nшаг 2\nшаг 3",
      "answer": "краткий ответ"
    }
  ]
}
```

`number` — строка: в новых учебниках номера с точкой («1.1», «4.13»), у учебников без
нумерации упражнений номер = «страница.K» («5.2»). `section` — раздел/параграф/модуль,
приложение группирует задания по нему. Полная схема — `docs/data-schema.json`.

## Как наполнить или поправить задания

Все задания уже собраны парсером (3601) — ниже инструкция на случай дополнения,
ручной правки или поломки источника.

```bash
# один учебник целиком (id — карта учебников в docs/PARSING.md)
uv run --with beautifulsoup4 scripts/parse_gdz.py vilenkin-6-1

# превью без записи или ограничение
uv run --with beautifulsoup4 scripts/parse_gdz.py vilenkin-6-1 --limit 10 --dry

# продолжить прерванный сбор: уже собранное не перекачивается
uv run --with beautifulsoup4 scripts/parse_gdz.py all --resume

# после любых изменений данных
uv run --with jsonschema scripts/validate_data.py
uv run python scripts/write_stats.py
```

Вручную: файл учебника — `app/data/<предмет>/<учебник>.json`, задание — объект в `tasks`
(`number`, `section`, `condition`, `solution`, `answer`; переносы строк в `solution`
становятся абзацами). Новый учебник: положить файл рядом, добавить запись в
`app/data/catalog.json` (id, title, author, year, file) и, если он должен собираться
парсером, в конфиг `BOOKS` в `scripts/parse_gdz.py`. Пропущенные номера в приложении —
серые некликабельные кнопки, это нормально.

Счётчики: `stats.json` генерируется (`write_stats.py`) — после правки данных достаточно
перезапустить скрипт. Скриншоты лендинга при желании обновляются так: поднять локальный
сервер и выполнить `scripts/venv-shots/bin/python scripts/take_screenshots.py`.

## Пересборка APK

APK — TWA-обёртка сайта (Bubblewrap). Нужны JDK 17, Android SDK и node/npm. Подпись —
`android-signing/keystore.jks` (в git не входит; пароли по умолчанию — в начале
`scripts/build_apk.sh`). Манифест Bubblewrap берёт с локального сервера, поэтому его
надо запустить заранее.

```bash
uv run python -m http.server 8000 &

# bubblewrap: если ещё не стоит — init поставит его сам в BUBBLEWRAP_DIR
# (текущая машина: BUBBLEWRAP_DIR=/tmp/opencode/bw)
BUBBLEWRAP_DIR="$HOME/.local/share/gdz-nel-bubblewrap" bash scripts/build_apk.sh init

# сборка: подписанный APK кладётся в download/app.apk
BUBBLEWRAP_DIR="$HOME/.local/share/gdz-nel-bubblewrap" bash scripts/build_apk.sh build
```

`versionCode`/`versionName` Bubblewrap поднимает сам. Отпечаток подписи для assetlinks:
`apksigner verify --print-certs download/app.apk`. Варианты, как убрать адресную строку
у TWA, — в `docs/README.md`, раздел «TWA и assetlinks».

## Маршруты (хэш-роутинг, ссылку можно скинуть)

```
#/                          выбор предмета
#/math                      выбор учебника
#/math/vilenkin-6-1         сетка заданий
#/math/vilenkin-6-1/1.12    задание 1.12
```

## Решения, принятые без согласования

- `assets/img/logo.svg` — нарисованная заглушка по описанию эмблемы (бирюзовая обводка, синяя птица, три столбика диаграммы). Чтобы поставить настоящую эмблему — заменить файл, имя оставить тем же.
- Предмет с одним учебником открывается сразу на сетке заданий, минуя экран выбора. С двумя (математика, русский) — показывает выбор частей.
- Номера страничных учебников (английский, биология, история, обществознание) условные — «страница.K»: на источнике у страниц нет номеров упражнений.
- Задачи без ответа на источнике не выдумываются: в приложении это серые зачёркнутые ячейки (например, мат. №2.540).
- Разделы математики приложение получает не со страниц источника (там нет заголовков), а маппингом по номеру задания — названия § сверены с учебником.

## Что дальше

- TWA без адресной строки: перенести сайт на user-root репозиторий (`bdfytu-commits.github.io`)
  или привязать свой домен — пошагово в `docs/README.md`, раздел «TWA и assetlinks».
- Если источник добавит новые задания — повторный `parse_gdz.py all --resume` дособерёт их
  без перекачки уже собранного; дальше `validate_data.py` и `write_stats.py`.
