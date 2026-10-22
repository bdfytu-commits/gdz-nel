# Тесты (playwright + seo)

Смоуки на живом локальном сервере и статический SEO-аудит.

Запуск:

```bash
# из корня репозитория, в отдельном терминале
uv run python -m http.server 8000

# все тесты подряд
bash scripts/tests/run_all.sh

# один тест
scripts/venv-shots/bin/python scripts/tests/smoke_app.py
```

| файл | что проверяет |
| --- | --- |
| `smoke_app.py` | приложение: сетка номеров, экран задания, избранное, поиск (23 проверки) |
| `test_offline.py` | офлайн: скачивание учебника в IndexedDB, отключение сети, задание и JSON из SW, `app/offline.html` |
| `smoke_lit.py` | литература Коровиной: 8 книг, разделы, задачи |
| `smoke_premium2.py` | премиум: шпаргалки, PDF, модели фото, PRO-бейджи, рекламная плашка для анонима/премиума/бесплатного |
| `smoke_kontur.py` | контурные карты: сканы страниц |
| `smoke_review.py` | отзывы: добавление и отображение |
| `smoke_admin.py` | админка: список юзеров, фильтры, CSV |
| `test_admin_premium.py` | админка: выдача/снятие ГДЗ+ |
| `smoke_visual.py` | визуалы математики: шаги, координатные прямые, диаграммы |
| `test_seo.py` | canonical, OG, twitter, JSON-LD, sitemap, robots — без браузера |
| `test_mobile_375.py` | 26 страниц на 375×812: горизонтальный скролл, вылезающие блоки, длинные формулы, все вкладки админки и 404 |

Требования:

- сервер на `127.0.0.1:8000`; другой адрес — переменная `GDZ_BASE`
  (например, `GDZ_BASE=https://gdz-nel.pages.dev`);
- тест-аккаунты в Supabase: `user1@gdz-nel.test` (ГДЗ+), `user2@gdz-nel.test`
  (бесплатный), `admin@gdz-nel.test` (админ). Пароли — только локально в
  `scripts/tests/.env.local` (файл в `.gitignore`, образец — `env.py`),
  в репозиторий и документацию пароли не коммитим;
- `smoke_premium2.py`, `smoke_review.py` и `test_admin_premium.py` требуют
  тестовые аккаунты: после финальной уборки (`supabase/cleanup_test_data.sql`)
  они печатают «тестовый аккаунт удалён» и пропускаются, а не падают;
- playwright — `scripts/venv-shots` (см. `scripts/take_screenshots.py`);
- `GDZ_SKIP_AUTH=1` — пропустить сценарии с логином (так гоняет CI, где
  тестовых аккаунтов нет).

Артефакты (скриншоты) складываются в `/tmp/opencode/*.png` и
`/tmp/opencode/mobile375/*.png`. Ошибки консоли браузера собираются каждым
смоуком и печатаются в конце (`errors: []` — чисто).

CI: `.github/workflows/tests.yml` — валидация данных, SEO, смоуки на данных
(`smoke_app`, `smoke_lit`, `smoke_kontur`, `smoke_visual`) и мобильная
верстка. Сценарии с логином в CI не запускаются: они ходят в прод-Supabase.
