#!/usr/bin/env python3
"""Очистка канала @gdz_nel через Telegram Bot API.

Бот должен быть администратором канала с правом can_delete_messages.
Bot API не отдаёт историю канала, поэтому скрипт перебирает message_id
в заданном диапазоне. Для старых сообщений Telegram может вернуть
"message can't be deleted" — это ограничение Bot API, не ошибка скрипта.

Примеры:
    python3 scripts/clean_telegram.py --dry-run
    python3 scripts/clean_telegram.py --max-id 500
    python3 scripts/clean_telegram.py --from-id 1 --to-id 200 --delay 0.08

Токен и канал берутся из .env:
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHANNEL_ID=@gdz_nel
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def api(token: str, method: str, **params):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode() if params else None
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", "replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "description": raw[:300]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-id", type=int, default=1)
    ap.add_argument("--to-id", type=int, default=0, help="0 — взять pinned/max-id")
    ap.add_argument("--max-id", type=int, default=1000, help="верхняя граница перебора")
    ap.add_argument("--delay", type=float, default=0.07, help="пауза между запросами")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    channel = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not token or not channel:
        print("нет TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID в .env")
        return 2

    me = api(token, "getMe")
    if not me.get("ok"):
        print("бот недоступен:", me.get("description", "неизвестная ошибка"))
        return 2
    chat = api(token, "getChat", chat_id=channel)
    if not chat.get("ok"):
        print("канал недоступен:", chat.get("description", "неизвестная ошибка"))
        print("проверь, что бот добавлен администратором канала с правом удалять сообщения")
        return 2

    info = chat["result"]
    print("канал:", info.get("username") or info.get("title") or channel)
    member = api(token, "getChatMember", chat_id=channel, user_id=me["result"]["id"])
    rights = member.get("result", {}) if member.get("ok") else {}
    if rights and not rights.get("can_delete_messages"):
        print("у бота нет права can_delete_messages — очистка невозможна")
        return 2

    pinned = info.get("pinned_message") or {}
    to_id = args.to_id or max(args.max_id, int(pinned.get("message_id") or 0))
    if to_id < args.from_id:
        print("пустой диапазон message_id")
        return 0

    print(f"диапазон message_id: {args.from_id}..{to_id}; запросов: {to_id - args.from_id + 1}")
    if args.dry_run:
        print("dry-run: ничего не удаляю")
        return 0

    deleted = 0
    forbidden = 0
    missing = 0
    errors = 0
    for message_id in range(to_id, args.from_id - 1, -1):
        res = api(token, "deleteMessage", chat_id=channel, message_id=message_id)
        if res.get("ok"):
            deleted += 1
            print(f"удалено: {message_id}")
        else:
            desc = str(res.get("description", ""))
            low = desc.lower()
            if "not found" in low:
                missing += 1
            elif "can't be deleted" in low or "forbidden" in low:
                forbidden += 1
            else:
                errors += 1
                print(f"ошибка {message_id}: {desc[:160]}")
        if message_id % 50 == 0:
            print(f"  проверено {to_id - message_id + 1}, удалено {deleted}")
        time.sleep(args.delay)

    print(
        f"итог: удалено {deleted}, старых/недоступных {forbidden}, "
        f"не найдено {missing}, ошибок {errors}"
    )
    if forbidden:
        print("часть сообщений старше лимита Bot API; удалить их можно только вручную в приложении Telegram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
