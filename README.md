# ГДЗ НЭЛ

Статический сайт с готовыми домашними заданиями для 1–11 классов МАОУ «Новосибирский экономический лицей».
Никакого бэкенда: HTML + CSS + vanilla JS, данные — JSON-файлы, читаются через fetch.
Без фреймворков, сборщиков и минификации — так требует ТЗ.

Что уже есть:

- лендинг с описанием и живыми счётчиками (310 022 заданий, 577 учебников, 15 предметов);
- приложение `/app`: выбор предмета → учебник → сетка номеров → задание (условие, пошаговое решение, ответ);
- поиск по номерам и по тексту условия с подсветкой, избранное, история просмотров;
- тёмная тема, печатный вид, клавиши ←/→/Esc, свайпы, «поделиться», «сообщить об ошибке»;
- PWA и офлайн-учебники: кнопка «Скачать» на карточке книги, IndexedDB, SW v12; подписанный `download/app.apk` для Android;
- доска почёта, кастомизация профиля (ГДЗ+), комментарии к профилям и ИИ-модерация отзывов;
- данные собраны парсерами с euroki.org, gdz-raketa.ru, gdz.ru (контурные карты, литература, физика, история, английский) и otvet.plus:
  310 022 заданий по 577 учебникам 1–11 классов, правила обхода и разбивка —
  в docs/PARSING.md.

## Структура

```
gdz-nel/
  index.html                  лендинг
  honor.html                  доска почёта
  profile.html                профиль, кастомизация, комментарии
  assets/                     стили, скрипт, эмблема, скриншоты лендинга
  download/app.apk            подписанный APK (3.1.0, versionCode 9)
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
    parse_euroki_bulk.py      массовый парсер euroki.org (3–5, 10–11 классы)
    parse_gdz.py              парсер заданий (gdz-raketa.ru)
    discover_euroki.py        автосбор инвентаря учебников
    sync_bulk_catalog.py      слияние манифестов в catalog.json
    validate_data.py          проверка JSON по схеме docs/data-schema.json
    write_stats.py            пересчёт app/data/stats.json
    take_screenshots.py       скриншоты лендинга (playwright)
    build_apk.sh              сборка APK (Bubblewrap)
  docs/                       ТЗ, правила, задачи, прогресс, лог парсинга
  .well-known/assetlinks.json Digital Asset Links для TWA-приложения
  .github/workflows/tg-notify.yml  телеграм-уведомления о пушах
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

Хостинг — Cloudflare Pages, проект `gdz-nel`, сайт: **https://gdz-nel.pages.dev**.
Cloudflare собирает репозиторий сам при пуше в `main`: framework preset — None,
build command — пустой, output directory — `/`. Никаких сборщиков и Actions для
публикации нет; `.github/workflows/tg-notify.yml` только шлёт уведомления в Telegram.

Домен сайта прописан в canonical/og/twitter/sitemap/robots —
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

## Как поддерживать проект

Данные — обычные JSON в `app/data/`, счётчики — `app/data/stats.json`, все операции —
скриптами из `scripts/`. Порядок любого обновления: собрать/поправить → `validate_data.py` →
`write_stats.py` → коммит в `main` (workflow сам проверит данные и опубликует сайт).

### Собрать или обновить учебник парсером

Парсер запускается по id учебника из карты `docs/PARSING.md` — отдельного аргумента
«предмет» нет, предмет известен по id (`vilenkin-6-1` → математика):

```bash
# один учебник целиком
uv run --with beautifulsoup4 scripts/parse_gdz.py vilenkin-6-1

# превью без записи (в /tmp) или ограничение диапазона
uv run --with beautifulsoup4 scripts/parse_gdz.py vilenkin-6-1 --limit 10 --dry

# все учебники; --resume продолжит с места обрыва, не перекачивая собранное
uv run --with beautifulsoup4 scripts/parse_gdz.py all --resume
```

Совсем новый учебник: добавить запись в конфиг `BOOKS` (`scripts/parse_gdz.py`) и в карту
`docs/PARSING.md`, затем запись в `app/data/catalog.json` (id, title, author, year, file) —
разведка и правила в разделе «Как добавить новый учебник» (`docs/PARSING.md`).

### Добрать пропуски с альтернативных источников

```bash
uv run --with beautifulsoup4 scripts/fill_gaps.py --dry-run   # показать, что найдётся
uv run --with beautifulsoup4 scripts/fill_gaps.py             # записать
```

Скрипт идёт только по серым номерам, условие берёт с gdz-raketa.ru, решение — с первого
подошедшего источника (euroki.org → otvet.plus → reshalka.com), в задаче появляются
`source` и `sourceUrl`. Ненайденное остаётся серым — ничего не выдумывается.

### Добавить задание вручную

Файл учебника — `app/data/<предмет>/<учебник>.json`, задание — объект в `tasks`:

```json
{
  "number": "1.27",
  "section": "§1. Вычисления и построения",
  "condition": "текст условия",
  "solution": "решение; строки — абзацы, нумерованные пункты — шаги",
  "answer": "краткий ответ"
}
```

`number` — строка как в приложении («1.27», «5.4», «47.2», «407»), уникальна внутри файла;
`section` — группа в сетке заданий, должна совпадать с соседями по разделу. Необязательные
`source`/`sourceUrl` (допустимые значения — enum в `docs/data-schema.json`) ставит
`fill_gaps.py` задачам, добранным с альтернативных сайтов. Пропущенные номера в приложении —
серые некликабельные кнопки, это нормально.

### Проверка и счётчики после правок

```bash
uv run --with jsonschema scripts/validate_data.py   # схема и уникальность номеров (то же гоняет CI)
uv run python scripts/write_stats.py                # пересобрать app/data/stats.json
grep -n 'stat-tasks\|footer-stats' index.html       # счётчики лендинга — обновить вручную
```

Скриншоты лендинга при желании обновляются так: поднять локальный сервер
(`uv run python -m http.server 8000`) и выполнить
`scripts/venv-shots/bin/python scripts/take_screenshots.py`.

Пересборка APK — отдельный раздел ниже. После обновления данных это не нужно: TWA
подтягивает сайт.

### Форма обратной связи (Web3Forms)

Форма в `contact.html` отправляет письма на bdfy.tu@yandex.ru через бесплатный сервис
Web3Forms (до 250 писем в месяц, бэкенд не нужен):

1. на <https://web3forms.com> нажать «Create your Form» и указать bdfy.tu@yandex.ru —
   access key придёт на эту почту;
2. вставить ключ в `contact.html` в `value` скрытого поля `access_key` (сейчас там
   плейсхолдер `PASTE-WEB3FORMS-ACCESS-KEY`);
3. в кабинете Web3Forms включить AutoResponder — отправителю придёт автоматическое
   письмо-подтверждение.

Ключ публичный (секрета в нём нет: он только указывает почту-получателя). Пока ключ
не вставлен, форма честно предлагает написать на почту напрямую. Юридическая часть —
в `docs/README.md` (раздел «Уведомление Роскомнадзора»).

### Документация

- `docs/PARSING.md` — источники, правила обхода, карта учебников, отчёты о сборах;
- `docs/data-schema.json` — схема данных (её проверяет CI при каждом пуше);
- `docs/TASKS.md`, `docs/PROGRESS.md`, `docs/CHANGELOG.md` — задачи, статус, история решений;
- `docs/README.md` — индекс всей документации (включая TWA и assetlinks);
- `docs/ABOUT.md` — о проекте коротко, для школы.

## Пересборка APK

APK — TWA-обёртка сайта. Текущий релиз собран Gradle в `android-twa/`; старые
сборки — Bubblewrap. Нужны JDK 17, Android SDK и node/npm.

Важно: команды ниже относятся к старым Bubblewrap-сборкам и подписывают
`android-signing/keystore.jks`. Текущий APK 3.1.0 (versionCode 9) подписан
`android-twa/android.keystore` — для обновления поверх v8 нужен **тот же** ключ,
иначе Android отклонит установку. Пересборка под новый домен — в `docs/README.md`,
раздел «Переезд на gdz-nel.is-a.dev».

```bash
uv run python -m http.server 8000 &

# bubblewrap: если ещё не стоит — init поставит его сам в BUBBLEWRAP_DIR
# (текущая машина: BUBBLEWRAP_DIR=/tmp/opencode/bw)
BUBBLEWRAP_DIR="$HOME/.local/share/gdz-nel-bubblewrap" bash scripts/build_apk.sh init

# сборка: подписанный APK кладётся в download/app.apk
BUBBLEWRAP_DIR="$HOME/.local/share/gdz-nel-bubblewrap" bash scripts/build_apk.sh build
```

Текущий релиз — 3.1.0 (versionCode 9), собран в Android Studio/Gradle и подписан
ключом `android-twa/android.keystore` (вне git). Для обновлений нужен **тот же**
ключ. Отпечаток подписи: `apksigner verify --print-certs download/app.apk`.
Варианты, как убрать адресную строку у TWA, — в `docs/README.md`, раздел
«TWA и assetlinks».

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

- Свой домен: привязать к Cloudflare Pages и пересобрать APK — пошагово
  в `docs/README.md`, раздел «TWA и assetlinks».
- Если источник добавит новые задания — повторный `parse_gdz.py all --resume` дособерёт их
  без перекачки уже собранного; дальше `validate_data.py` и `write_stats.py`.
