#!/usr/bin/env python3
"""Живой тест fail-safe ИИ-модерации: Groq отвечает HTTP 500.

Сценарий:
  1. временно ставим секрет GROQ_API_URL=https://httpstat.us/500;
  2. создаём отзыв от админа (RLS разрешает только свой pending-отзыв);
  3. ждём вебхук moderate-review;
  4. проверяем: отзыв опубликован, ai_status=approved, ai_reason содержит HTTP 500;
  5. всегда возвращаем секрет и удаляем тестовый отзыв.

Запуск:
    python3 scripts/tests/test_ai_failsafe.py --live

Без --live проверяется только наличие fail-safe в исходнике.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from env import SUPABASE_KEY, SUPABASE_URL, load

load()

ROOT = Path(__file__).resolve().parent.parent.parent
FUNC = ROOT / "supabase/functions/moderate-review/index.ts"
GROQ_500_URL = os.environ.get("GDZ_GROQ_500_URL", "https://httpbin.org/status/500")


def request(method: str, path: str, token: str | None = None, body=None, prefer: str | None = None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(SUPABASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        raw = err.read()
        try:
            return err.code, json.loads(raw)
        except Exception:
            return err.code, raw.decode("utf-8", "replace")


def login() -> tuple[str, str]:
    email = os.environ.get("GDZ_ADMIN_EMAIL", "")
    password = os.environ.get("GDZ_ADMIN_PASSWORD", "")
    if not email or not password:
        raise SystemExit("нет GDZ_ADMIN_EMAIL/GDZ_ADMIN_PASSWORD в scripts/tests/.env.local")
    status, data = request(
        "POST", "/auth/v1/token?grant_type=password",
        body={"email": email, "password": password},
    )
    if status != 200 or not isinstance(data, dict):
        raise SystemExit(f"не удалось войти админом: HTTP {status}")
    return data["access_token"], data["user"]["id"]


def cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["supabase", *args], cwd=ROOT, text=True, capture_output=True, timeout=120)


def static_check() -> int:
    source = FUNC.read_text(encoding="utf-8")
    checks = {
        "fail-safe обновляет отзыв": "approveFallback" in source,
        "HTTP 500 не перебирает модели": "if (res.status >= 500) break;" in source,
        "причина пишется в ai_reason": "ai_reason: reason" in source,
        "адрес Groq переопределяется": "GROQ_URL" in source,
    }
    for name, ok in checks.items():
        print(("ok   " if ok else "FAIL ") + name)
    return 0 if all(checks.values()) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="временно подменить GROQ_API_URL и проверить вебхук")
    args = ap.parse_args()
    if not args.live:
        return static_check()

    token, user_id = login()
    review_id = None
    secret_set = False
    try:
        print("ставлю GROQ_API_URL =", GROQ_500_URL)
        res = cli("secrets", "set", f"GROQ_API_URL={GROQ_500_URL}")
        if res.returncode != 0:
            print(res.stdout[-500:], res.stderr[-500:])
            raise SystemExit("не удалось поставить тестовый секрет")
        secret_set = True
        time.sleep(8)

        stamp = str(int(time.time() * 1000))
        status, data = request(
            "POST", "/rest/v1/reviews", token,
            {
                "task_id": "test:ai-failsafe-" + stamp,
                "user_id": user_id,
                "username": "fail-safe-test",
                "rating": 5,
                "text": "Проверка fail-safe: Groq отвечает 500, отзыв должен опубликоваться.",
                "ai_status": "pending",
                "is_approved": False,
            },
            "return=representation",
        )
        if status not in (200, 201) or not data:
            raise SystemExit(f"не удалось создать отзыв: HTTP {status} {str(data)[:300]}")
        review_id = data[0]["id"]
        print("отзыв создан:", review_id)

        row = None
        for _ in range(45):
            time.sleep(2)
            status, data = request(
                "GET", f"/rest/v1/reviews?id=eq.{review_id}&select=id,is_approved,ai_status,ai_reason",
                token,
            )
            if status == 200 and data:
                row = data[0]
                if row.get("ai_status") != "pending":
                    break
        print("состояние:", row)
        if not row:
            raise SystemExit("отзыв не найден после модерации")
        if row.get("is_approved") is not True or row.get("ai_status") != "approved":
            raise SystemExit("fail-safe не опубликовал отзыв")
        reason = str(row.get("ai_reason") or "")
        if "HTTP 500" not in reason:
            raise SystemExit(f"в ai_reason нет HTTP 500: {reason[:200]}")
        print("ok: отзыв опубликован, ai_reason содержит HTTP 500")
        return 0
    finally:
        if review_id:
            request("DELETE", f"/rest/v1/reviews?id=eq.{review_id}", token)
        if secret_set:
            res = cli("secrets", "unset", "GROQ_API_URL")
            print("секрет GROQ_API_URL снят" if res.returncode == 0 else "не удалось снять GROQ_API_URL: " + res.stderr[-300:])


if __name__ == "__main__":
    sys.exit(main())
