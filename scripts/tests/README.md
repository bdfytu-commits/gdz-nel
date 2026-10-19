# Смоук-тесты (playwright)

Восемь сценариев на живом локальном сервере.

Запуск:

```bash
# из корня репозитория, в отдельном терминале
uv run python -m http.server 8000

# все смоуки подряд
bash scripts/tests/run_all.sh

# один смоук
scripts/venv-shots/bin/python scripts/tests/smoke_app.py
```

| файл | что проверяет |
| --- | --- |
| `smoke_app.py` | приложение: сетка номеров, экран задания, избранное, поиск (23 проверки) |
| `smoke_lit.py` | литература Коровиной: 8 книг, разделы, задачи |
| `smoke_premium2.py` | премиум: шпаргалки, PDF, модели фото, PRO-бейджи, рекламная плашка для анонима/премиума/бесплатного |
| `smoke_kontur.py` | контурные карты: сканы страниц |
| `smoke_review.py` | отзывы: добавление и отображение |
| `smoke_admin.py` | админка: список юзеров, фильтры, CSV |
| `test_admin_premium.py` | админка: выдача/снятие ГДЗ+ |
| `smoke_visual.py` | визуалы математики: шаги, координатные прямые, диаграммы |

Требования:

- сервер на `127.0.0.1:8000`; другой адрес — переменная `GDZ_BASE`
  (например, `GDZ_BASE=https://gdz-nel.pages.dev`);
- тест-аккаунты в Supabase: `user1@gdz-nel.test` (ГДЗ+), `user2@gdz-nel.test`
  (бесплатный), `admin@gdz-nel.test` (админ) — пароль у всех
  `GdzNel-Test-2026!`;
- playwright — `scripts/venv-shots` (см. `scripts/take_screenshots.py`).

Артефакты (скриншоты) складываются в `/tmp/opencode/*.png`. Ошибки консоли
браузера собираются каждым смоуком и печатаются в конце (`errors: []` — чисто).
