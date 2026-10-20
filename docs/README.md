# Документация ГДЗ НЭЛ

Что где лежит и для чего.

| файл | о чём |
| --- | --- |
| `SPEC.md` | техническое задание: структура, палитра, шрифты, функционал, формат JSON |
| `RULES.md` | правила работы над проектом (главнее промпта): чистая статика, ответы строчными, коммиты после задач |
| `ABOUT.md` | о проекте коротко: что это, кто сделал, для кого, источники, ограничения, лицензия |
| `TASKS.md` | список задач со статусами (0–34) |
| `PROGRESS.md` | что сделано / в работе / ждёт, известные ограничения |
| `CHANGELOG.md` | решения и результаты проверок по датам (a11y, Lighthouse, APK, данные) |
| `PARSING.md` | как собраны задания: источник, карта учебников, ограничения, запуск парсера |
| `data-schema.json` | JSON-схема данных сайта (проверяет `scripts/validate_data.py`) |

Пояснения по репозиторию целиком — в корневом `README.md`; сопровождение (добавить или
поправить задания, stats.json, пересборка APK) — там же, разделы «Как поддерживать
проект» и «Пересборка APK».

## Уведомление Роскомнадзора (152-ФЗ)

На сайте есть форма обратной связи с именем и email — значит, проект стал оператором
персональных данных и должен подать уведомление в Роскомнадзор. Подать нужно в течение
30 дней после запуска формы, не откладывайте.

Электронная форма: <https://rkn.gov.ru/personal-data/forms/notification/>
(там же — «Проверка состояния уведомления»). Подаётся онлайн и бесплатно, форма сама
подсказывает поля по шагам.

Что вписать:

- оператор — физическое лицо: ФИО, паспортные данные, адрес, телефон; ИНН и СНИЛС,
  если есть; email — `bdfy.tu@yandex.ru`;
- цель обработки — обратная связь: ответы на сообщения формы на сайте;
- категории персональных данных — имя, адрес электронной почты, содержание сообщения;
- категории субъектов — посетители сайта;
- правовое основание — согласие субъекта (галочка «Я согласен на обработку персональных
  данных» в форме);
- способ обработки — смешанная, с использованием сети «Интернет»;
- передача третьим лицам — сервис Web3Forms (США), то есть трансграничная передача:
  отметить в форме;
- дата начала обработки — день, когда форма заработала.

Если что-то изменится (другая цель, другой сервис) — сведения обновляются отдельным
уведомлением об изменении.

## TWA и assetlinks: как убрать адресную строку

Приложение `download/app.apk` — TWA. Чтобы Android считал его доверенным и не показывал
адресную строку, он проверяет Digital Asset Links по адресу
`https://<origin>/.well-known/assetlinks.json`, где `<origin>` — **корень домена**.

Сайт живёт на Cloudflare Pages (`https://gdz-nel.pages.dev`). Это отдельный origin,
и файл `.well-known/assetlinks.json` лежит в корне репозитория, поэтому отдаётся
по адресу `https://gdz-nel.pages.dev/.well-known/assetlinks.json` — проверка проходит.

В `assetlinks.json` два отпечатка:

- `63:A6:…:EA:60` — текущий релиз **v2.1.0 (versionCode 8)**, собран Gradle
  и подписан ключом `android-twa/android.keystore`;
- `B8:A5:…:3A:1F` — старые сборки (v4/v5, `android-signing/keystore.jks`).

Важно: Android разрешает обновлять приложение только тем же ключом, которым
подписан текущий APK. `android-twa/android.keystore` лежит вне git — сделай
бэкап файла и пароля, иначе будущие версии в RuStore/Google Play не обновятся.
Если ключ потерян — единственный путь обновления: новый package id.

Если появится свой домен:

1. Привязать домен к проекту Cloudflare Pages: Custom domains → Set up a domain
   (если домен уже на Cloudflare, DNS-записи создаются сами).
2. Положить `.well-known/assetlinks.json` в корень сайта — на своём домене он отдаётся
   как `https://<домен>/.well-known/assetlinks.json` (файл тот же, путь тот же).
3. Обновить домен в `twa-manifest.json`, `android-twa/app/build.gradle` и
   `strings.xml`, canonical/og/twitter, sitemap.xml, robots.txt и UA парсеров;
   пересобрать APK тем же ключом. Полный порядок — в разделе
   «Переезд на gdz-nel.is-a.dev» ниже.

### Проверка

```bash
curl https://<origin>/.well-known/assetlinks.json   # 200 и JSON
apksigner verify --print-certs download/app.apk     # SHA-256 должен совпадать с JSON
```

Отпечаток в `assetlinks.json` уже соответствует подписи APK; при смене ключа —
обновить.

---

## Переезд на gdz-nel.is-a.dev: чеклист после апрува

Статус на 20.10.2026: PR [`is-a-dev/register#57491`](https://github.com/is-a-dev/register/pull/57491)
открыт, домен ещё не выдан — `https://gdz-nel.is-a.dev/` показывает страницу
is-a.dev «available». Production — `https://gdz-nel.pages.dev`; код и данные
заморожены на `ffb9954`, после него — только документация. **До апрува
`change_domain.py` не запускать**: canonical, sitemap и robots переедут на
несуществующий домен, поисковики это увидят.

### 0. Предусловия

- [ ] PR смёржен, `gdz-nel.is-a.dev` резолвится в Cloudflare (CNAME на
      `gdz-nel.pages.dev`). Проверка: `dig +short gdz-nel.is-a.dev`.
- [ ] `git pull --ff-only`, рабочее дерево чистое, CI зелёный.
- [ ] Тег для отката: `git tag pre-is-a-dev && git push origin pre-is-a-dev`.
- [ ] Бэкап `android-twa/android.keystore` и пароля к нему.
- [ ] В `android-twa/twa-manifest.json` host = `gdz-nel.pages.dev` (до переезда).

### 1. Замена домена в репозитории

```bash
cd /home/ivan/opencode/gdz-nel
python3 scripts/change_domain.py --dry-run   # посмотреть список файлов и число замен
python3 scripts/change_domain.py
git diff --stat
```

Ожидаемо: меняются только текстовые файлы (HTML, JS, JSON, XML, MD, PY, TXT);
APK, картинки и `android-twa/` в diff не попадают. После запуска:

```bash
grep -rn "gdz-nel.pages.dev" --exclude-dir=.git --exclude-dir=venv-shots --exclude-dir=android-twa . | head
python3 -c "import json;print(json.load(open('android-twa/twa-manifest.json'))['host'])"
```

`gdz-nel.pages.dev` может остаться только в самом `scripts/change_domain.py`
(он себя не переписывает). В `android-twa/twa-manifest.json` host должен стать
`gdz-nel.is-a.dev`. Скрипт патчит только этот манифест; Gradle-проект
`android-twa/app/build.gradle` и `strings.xml` он не трогает — они в `.gitignore`,
правятся руками в шаге 6.

Важно: скрипт заменяет домен и в документации, включая этот чеклист. После
переезда исторические упоминания старого домена в текстах исчезнут; для отката
ориентируйся на тег `pre-is-a-dev` и git-историю, а не на текст ниже.

### 2. Проверка до пуша

Сервер :8000 должен быть поднят (`uv run python -m http.server 8000`).

```bash
python3 scripts/validate_data.py
scripts/venv-shots/bin/python scripts/tests/test_seo.py
scripts/venv-shots/bin/python scripts/tests/test_mobile_375.py
```

SEO-тест берёт домен из canonical главной, поэтому после замены проверяет уже
is-a.dev. Мобильный тест — 26 страниц 375×812; без пароля админа вкладки админки
пропускаются, с `scripts/tests/.env.local` проверяются все.

### 3. Коммит и пуш

```bash
git add -A
git commit -m "feat: переезд на gdz-nel.is-a.dev"
git push origin main
```

Cloudflare Pages пересоберёт сайт за 1–2 минуты. Старый домен продолжает
работать — не удалять его, пока новый домен не проверен.

### 4. Cloudflare Pages → Custom domains

- [ ] Dashboard → Workers & Pages → `gdz-nel` → Custom domains → Set up a domain →
      `gdz-nel.is-a.dev`.
- [ ] Дождаться статуса Active (TLS-сертификат выпускается автоматически).
- [ ] Если CF просит DNS-запись, сверить с тем, что создал смёрженный PR в
      is-a.dev (CNAME на `gdz-nel.pages.dev`). Вторую/конфликтующую не создавать.
- [ ] `https://gdz-nel.is-a.dev/` открывается, canonical — is-a.dev, редиректа на
      pages.dev нет.
- [ ] `https://gdz-nel.is-a.dev/.well-known/assetlinks.json` — 200, оба отпечатка.

### 5. Supabase Auth → URL Configuration

- [ ] Authentication → URL Configuration → Site URL: `https://gdz-nel.is-a.dev/`.
- [ ] Redirect URLs: добавить `https://gdz-nel.is-a.dev/**`; старые
      `https://gdz-nel.pages.dev/**` пока оставить на переходный период.
- [ ] Проверить вход, регистрацию, подтверждение почты, сброс пароля и профиль на
      новом домене. Если ссылки в письмах ведут на старый домен — поправить
      шаблоны писем (Authentication → Email Templates).
- [ ] Если включены OAuth-провайдеры — добавить новый redirect URI в их кабинетах.

### 6. Lava.top: повторная модерация домена

- [ ] Личный кабинет Lava → настройки виджета/подписки → добавить
      `gdz-nel.is-a.dev`, отправить на модерацию.
- [ ] Дождаться апрува. До него iframe оплаты на новом домене будет заблокирован
      (`frame-ancestors` у Lava).
- [ ] После апрува проверить `premium.html`: виджет грузится, тестовая оплата
      проходит, вебхук создаёт/продлевает подписку.
- [ ] Старый домен в настройках Lava можно оставить до полного переезда.

### 7. APK: пересборка под новый домен

Текущий APK 2.1.0 (versionCode 8) подписан `android-twa/android.keystore`
(отпечаток `63:A6:…:EA:60`). Обновление должно быть подписано **тем же** ключом,
иначе Android не установит его поверх. `scripts/build_apk.sh` (Bubblewrap)
подписывает старым `android-signing/keystore.jks` — **не использовать его для
этого обновления**.

1. `change_domain.py` уже поправил `android-twa/twa-manifest.json` (host, iconUrl,
   webManifestUrl, fullScopeUrl).
2. Вручную в `android-twa/app/build.gradle`:
   - `hostName: 'gdz-nel.is-a.dev'`
   - `webManifestUrl: 'https://gdz-nel.is-a.dev/app/manifest.json'`
   - `fullScopeUrl: 'https://gdz-nel.is-a.dev/app/'`
   - `versionCode 9`, `versionName "2.2.0"`.
3. В `android-twa/app/src/main/res/values/strings.xml` заменить
   `https://gdz-nel.pages.dev` в `assetStatements` на новый домен.
4. В `android-twa/twa-manifest.json` обновить `appVersion`, `appVersionCode` и
   `appVersionName` (метаданные; на Gradle-сборку не влияют).
5. Собрать и подписать тем же ключом (алиас и пароль — как у v8):

   ```bash
   cd android-twa
   ./gradlew assembleRelease
   zipalign -f -p 4 app/build/outputs/apk/release/app-release-unsigned.apk /tmp/opencode/gdz-unsigned.apk
   apksigner sign --ks android.keystore --ks-key-alias <alias> \
     --out /tmp/opencode/gdz-2.2.0.apk /tmp/opencode/gdz-unsigned.apk
   cp /tmp/opencode/gdz-2.2.0.apk ../download/app.apk
   cd ..
   ```

6. Проверить:

   ```bash
   apksigner verify --print-certs download/app.apk   # 63:A6:…:EA:60
   aapt dump badging download/app.apk | head -5      # versionCode 9, versionName 2.2.0
   ```

7. Установить на телефон поверх v8 и открыть: адресной строки нет, сайт is-a.dev.
   Если строка появилась — проверить assetlinks на новом домене и отпечаток.
8. Закоммитить новый `download/app.apk` и запушить.

`assetlinks.json` менять не нужно: ключ тот же, оба отпечатка уже там.

### 8. Sitemap и поисковики

- [ ] Яндекс.Вебмастер: добавить `https://gdz-nel.is-a.dev`, подтвердить (файл
      верификации уже в корне), отправить `https://gdz-nel.is-a.dev/sitemap.xml`.
- [ ] Google Search Console: добавить URL-prefix `https://gdz-nel.is-a.dev/`
      (или Domain property), подтвердить, отправить sitemap.
- [ ] Проверить `robots.txt`: `Sitemap:` на is-a.dev, `Disallow` не сломан.
- [ ] Старые свойства старого домена не удалять 1–2 месяца.

### 9. Финальная приёмка

- [ ] 10–15 страниц на новом домене: 200, правильный canonical/OG, нет ошибок
      консоли.
- [ ] `/admin/`, вход, профиль, премиум, поиск, задача, 404.
- [ ] `/.well-known/assetlinks.json`, `_headers` (CSP), `/docs/` → `/`.
- [ ] APK на телефоне, оплата Lava, письма Supabase.
- [ ] CI зелёный, Cloudflare deployment success, мобильный тест 26/26.

### Если что-то пошло не так

- до коммита: `git restore .` (как 20.10) и вручную вернуть
  `android-twa/twa-manifest.json` на прежний домен — `git restore` его не вернёт,
  файл в `.gitignore`;
- после коммита, но до пуша: `git reset --hard pre-is-a-dev`;
- после пуша: `git revert <commit>` и пуш. Домены в Cloudflare, Supabase и Lava
  оставить оба, пока сайт не стабилизируется: старый домен продолжает
  работать, поэтому откат кода возвращает рабочий сайт.
