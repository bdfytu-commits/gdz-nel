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

import json
import os
import urllib.request
from pathlib import Path

SUPABASE_URL = os.environ.get("GDZ_SUPABASE_URL", "https://qncqeoklwblztbnoktwk.supabase.co")
SUPABASE_KEY = os.environ.get(
    "GDZ_SUPABASE_KEY", "sb_publishable_uyBIZ2gNPuDqxre3ea989w_WbctezF4")


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


def account_ready(email: str, password: str) -> bool:
    """Есть ли аккаунт и профиль: после уборки тестовых юзеров тесты скипаются."""
    if not password:
        return False
    try:
        req = urllib.request.Request(
            SUPABASE_URL + "/auth/v1/token?grant_type=password",
            data=json.dumps({"email": email, "password": password}).encode(),
            headers={"apikey": SUPABASE_KEY, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        uid, token = data["user"]["id"], data["access_token"]
        req = urllib.request.Request(
            SUPABASE_URL + f"/rest/v1/profiles?select=id&id=eq.{uid}",
            headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + token},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return len(json.loads(resp.read())) == 1
    except Exception:  # noqa: BLE001
        return False
