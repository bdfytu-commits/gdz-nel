# Изменения и проверки

Здесь фиксируются решения по ходу работы и результаты проверок (a11y, lighthouse).

## 2026-10-16

### задача 16 — доступность (axe-core 4.10.2)

Проверялись страницы: лендинг, /app главная, сетка заданий, задание, избранное.
Набор правил: wcag2a, wcag2aa, wcag21a, wcag21aa, best-practice, плюс показ тоста и подсказки.

- нарушений: 0 (после правок)
- правки по итогам:
  - `#hint` получил `role="region"` + `aria-label` (иначе axe: region — контент вне landmark)
  - у поля поиска в /app добавлена видимая рамка `:focus-visible` (был только outline: none)
- клавиатура: Tab обходит лендинг (14 остановок) и приложение (15), фокус видим у всех,
  поиск достижим, Enter на карточке предмета открывает предмет — ок.
- контраст: scripts/audit_contrast.py — все пары ≥ 4.5:1 (текст) и ≥ 3:1 (графика);
  для белого текста затемнены hero-градиент (20%) и кнопочный градиент (#128080 → #005CA8).

### решение: плейсхолдеры домена

Домен сайта на момент работы неизвестен, поэтому:
- canonical, og:url и sitemap.xml содержат помеченный плейсхолдер
  `https://USER.github.io/gdz-nel/` — заменить после деплоя (задача 28);
- относительные пути внутри сайта работают и на GitHub Pages, и на Cloudflare Pages.

### задача 7 — APK (bubblewrap 1.27.0)

- подпись: `android-signing/keystore.jks` (alias `gdz-nel`, пароли в env), DN: CN/OU/O=Gdz Nel, L/ST=Novosibirsk, C=RU;
- итоговый файл: `download/app.apk` — ru.nel.gdz, versionCode 2 / versionName 2, minSdk 24, targetSdk 36, подпись проверена `apksigner verify`;
- грабли: bubblewrap требует `sdkmanager` в `$SDK/bin` (симлинки из cmdline-tools/latest/bin);
  androidbrowserhelper 2.7.4 требует minSdk ≥ 24 (в twa-manifest поднято с 21);
  `bubblewrap build` при изменённом twa-manifest.json задаёт вопрос — нужен TTY (или pty-драйвер `/tmp/opencode/bw_run.py`);
- домен TWA сейчас `gdz-nel.example` — после деплоя пересобрать APK и добавить `/.well-known/assetlinks.json`.

### задача 18 — Lighthouse 13.5.0

Мобильный профиль (throttle по умолчанию), chrome-headless-shell 1243, локальный сервер.

| страница | performance | accessibility | best-practices | seo |
|---|---|---|---|---|
| лендинг `/` | 98 | 100 | 100 | 100 |
| `/app/` (главная) | 100 | 100 | 100 | 100 |
| `/app/#/…/задание` | 99 | 100 | 100 | 100 |

Пороги ТЗ: P>90, A>95, BP>95, SEO>90 — пройдены.

Что дало рост:
- шрифты Unbounded не блокируют рендер (`media="print" onload="this.media='all'"` + noscript-фолбэк) — render-blocking savings ~2.4с;
- логотипы под DPR 2.625: logo-120 (шапки), logo-160 (футер), logo-280 (hero) вместо одного логотипа 225px;
- og-картинка 1200×630 из скриншота лендинга.

Осознанные решения против идеального счёта:
- CSS/JS не минифицируем — прямое требование ТЗ («без минификации»);
- кэш-заголовки локального python-сервера пустые; на GitHub Pages статика кэшируется нормально.

