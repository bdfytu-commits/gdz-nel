#!/usr/bin/env python3
"""Ежедневный постинг в Telegram — только там, где бот администратор.

Правила:
  * канал берётся из TELEGRAM_CHANNEL_IDS / TELEGRAM_CHANNEL_ID или
    marketing/tg_channels.txt;
  * перед отправкой проверяется getChatMember: бот должен быть creator или
    administrator и иметь can_post_messages;
  * один пост в день, состояние в /tmp/tg_poster_state.json;
  * лог в /tmp/tg_poster.log;
  * никаких рассылок в чужие чаты.

Запуск:
    python3 scripts/tg_poster.py --check
    python3 scripts/tg_poster.py --dry-run
    python3 scripts/tg_poster.py --once

Для cron:
    0 10 * * * cd /path/to/gdz-nel && /usr/bin/python3 scripts/tg_poster.py --once
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from marketing_common import (
    POSTS_FILE,
    append_log,
    daily_post,
    load_env,
    load_state,
    parse_posts,
    save_state,
    telegram_channels,
    telegram_token,
)

LOG = Path("/tmp/tg_poster.log")
STATE = Path("/tmp/tg_poster_state.json")
API = "https://api.telegram.org/bot{token}/{method}"


def tg_call(token: str, method: str, **params) -> dict:
    data = urllib.parse.urlencode(params).encode("utf-8") if params else None
    request = urllib.request.Request(API.format(token=token, method=method), data=data)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            payload = json.load(error)
        except Exception:  # noqa: BLE001
            payload = {"ok": False, "description": f"HTTP {error.code}"}
        if error.code == 429 and payload.get("parameters", {}).get("retry_after"):
            time.sleep(min(int(payload["parameters"]["retry_after"]), 60))
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        else:
            raise RuntimeError(payload.get("description", f"HTTP {error.code}")) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"network: {error.reason}") from error
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description", "Telegram API error"))
    return payload.get("result", {})


def resolve_channels(token: str, channels: list[str]) -> list[dict]:
    me = tg_call(token, "getMe")
    bot_id = me["id"]
    allowed: list[dict] = []
    for channel in channels:
        try:
            chat = tg_call(token, "getChat", chat_id=channel)
            member = tg_call(token, "getChatMember", chat_id=channel, user_id=bot_id)
        except RuntimeError as error:
            append_log(LOG, f"skip {channel}: {error}")
            continue
        status = member.get("status")
        can_post = bool(member.get("can_post_messages", member.get("can_send_messages", False)))
        if status not in {"creator", "administrator"} or not can_post:
            append_log(LOG, f"skip {channel}: status={status}, can_post={can_post}")
            continue
        allowed.append({
            "id": channel,
            "title": chat.get("title") or channel,
            "username": chat.get("username") or "",
            "type": chat.get("type") or "channel",
        })
        append_log(LOG, f"admin ok: {channel} ({chat.get('title', '')})")
    return allowed


def select_post(posts: list[dict], force: bool) -> tuple[int, dict]:
    state = load_state(STATE)
    index, state = daily_post(posts, state, force=force)
    state["index"] = index
    return index, state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="только проверить права бота")
    parser.add_argument("--dry-run", action="store_true", help="показать пост без отправки")
    parser.add_argument("--once", action="store_true", help="отправить один пост за сегодня")
    parser.add_argument("--force", action="store_true", help="разрешить повтор в тот же день")
    args = parser.parse_args()

    env = load_env()
    token = telegram_token(env)
    if not token:
        print("нет TELEGRAM_BOT_TOKEN в .env или окружении")
        return 2

    channels = telegram_channels(env)
    if not channels:
        print("нет каналов: заполните TELEGRAM_CHANNEL_ID или marketing/tg_channels.txt")
        return 2

    posts = parse_posts("Telegram")
    if not posts:
        print(f"нет постов в {POSTS_FILE}")
        return 2

    allowed = resolve_channels(token, channels)
    if not allowed:
        print("бот не админ ни в одном канале — постить некуда")
        return 1
    print("разрешено:", ", ".join(f"{item['title']} ({item['id']})" for item in allowed))
    if args.check:
        return 0

    index, state = select_post(posts, args.force)
    post = posts[index]
    print(f"пост: {post['id']}, {len(post['text'])} символов")
    if args.dry_run:
        print("\n" + post["text"])
        return 0

    if not args.once:
        print("укажите --once, --dry-run или --check")
        return 2

    sent = set(state.get("sent", []))
    failures = 0
    for channel in allowed:
        chat_id = channel["id"]
        if chat_id in sent and not args.force:
            print(f"уже отправлено сегодня: {channel['title']}")
            continue
        try:
            message = tg_call(
                token, "sendMessage", chat_id=chat_id, text=post["text"],
                disable_web_page_preview=False,
            )
            sent.add(chat_id)
            append_log(LOG, f"sent {post['id']} -> {chat_id} message_id={message.get('message_id')}")
            print(f"отправлено: {channel['title']} message_id={message.get('message_id')}")
            time.sleep(1)
        except RuntimeError as error:
            failures += 1
            append_log(LOG, f"error {post['id']} -> {chat_id}: {error}")
            print(f"ошибка {channel['title']}: {error}")

    state["sent"] = sorted(sent)
    save_state(STATE, state)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
