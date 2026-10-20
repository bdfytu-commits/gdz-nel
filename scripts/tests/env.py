"""Локальные креды тестов: scripts/tests/.env.local (не коммитится).

Формат — обычный KEY=VALUE, без экспорта:

    GDZ_ADMIN_EMAIL=admin@gdz-nel.test
    GDZ_ADMIN_PASSWORD=...
    GDZ_USER1_EMAIL=user1@gdz-nel.test
    GDZ_USER2_EMAIL=user2@gdz-nel.test
    GDZ_TEST_PASSWORD=...

Переменные окружения имеют приоритет над файлом.
"""

from __future__ import annotations

import os
from pathlib import Path


def load() -> None:
    path = Path(__file__).with_name(".env.local")
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
