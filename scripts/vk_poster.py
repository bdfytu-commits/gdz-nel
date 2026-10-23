#!/usr/bin/env python3
"""Ежедневный постинг ВК — только в свою группу.

Жёсткое правило: owner_id всегда отрицательный VK_GROUP_ID из окружения.
Скрипт не принимает чужой group_id аргументом и не умеет постить в чужие
сообщества. Для чужих пабликов — только ручная договорённость с админом.

Нужны:
  VK_ACCESS_TOKEN — пользовательский токен с правами wall, groups;
  VK_GROUP_ID — числовой id своей группы.

Запуск:
    python3 scripts/vk_poster.py --check
    python3 scripts/vk_poster.py --dry-run
    python3 scripts/vk_poster.py --once
"""

from __future__ import annotations

import argparse
import json
import re
import sys
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
    vk_token,
)

LOG = Path("/tmp/vk_poster.log")
STATE = Path("/tmp/vk_poster_state.json")
API = "https://api.vk.com/method/"
API_VERSION = "5.199"


def vk_call(token: str, method: str, **params) -> dict:
    query = {"access_token": token, "v": API_VERSION, **params}
    data = urllib.parse.urlencode(query).encode("utf-8")
    request = urllib.request.Request(API + method, data=data)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"VK HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"VK network: {error.reason}") from error
    if "error" in payload:
        raise RuntimeError(f"VK API: {payload['error'].get('error_msg', 'unknown error')}")
    return payload.get("response", {})


def own_group_id(env: dict[str, str]) -> str:
    raw = (env.get("VK_GROUP_ID") or "").strip()
    digits = re.sub(r"\D", "", raw)
    return str(abs(int(digits))) if digits else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="проверить токен и доступ к группе")
    parser.add_argument("--dry-run", action="store_true", help="показать пост без отправки")
    parser.add_argument("--once", action="store_true", help="отправить один пост за сегодня")
    parser.add_argument("--force", action="store_true", help="разрешить повтор в тот же день")
    args = parser.parse_args()

    env = load_env()
    token = vk_token(env)
    group_id = own_group_id(env)
    if not token:
        print("нет VK_ACCESS_TOKEN. Нужен пользовательский токен VK с правами wall, groups.")
        print("Без него автопостинг и поиск сообществ не запускаю.")
        return 2
    if not group_id:
        print("нет VK_GROUP_ID — id своей группы. В чужие группы скрипт не постит.")
        return 2

    owner_id = -abs(int(group_id))
    try:
        group = vk_call(token, "groups.getById", group_ids=group_id, fields="members_count")
        groups = group.get("groups", []) if isinstance(group, dict) else group
        if groups:
            print("своя группа:", groups[0].get("name"), "id", group_id)
        else:
            print("группа не найдена или токен не имеет доступа")
            return 1
        wall = vk_call(token, "wall.get", owner_id=owner_id, count=1)
        print("wall доступен, постов в группе:", wall.get("count", 0))
    except RuntimeError as error:
        print(f"проверка не прошла: {error}")
        return 1
    if args.check:
        return 0

    posts = parse_posts("VK")
    if not posts:
        print(f"нет постов в {POSTS_FILE}")
        return 2
    state = load_state(STATE)
    index, state = daily_post(posts, state, force=args.force)
    post = posts[index]
    print(f"пост: {post['id']}, {len(post['text'])} символов")
    if args.dry_run:
        print("\n" + post["text"])
        return 0
    if not args.once:
        print("укажите --once, --dry-run или --check")
        return 2
    if state.get("date") == date.today().isoformat() and state.get("sent") and not args.force:
        print("пост за сегодня уже отправлен")
        return 0

    try:
        result = vk_call(
            token, "wall.post", owner_id=owner_id, from_group=1,
            message=post["text"], guid=f"gdznel-{date.today().isoformat()}-{post['id']}",
        )
        state.update({"date": date.today().isoformat(), "index": index, "sent": [group_id]})
        save_state(STATE, state)
        append_log(LOG, f"sent {post['id']} -> {group_id} post_id={result.get('post_id')}")
        print("отправлено, post_id:", result.get("post_id"))
        return 0
    except RuntimeError as error:
        append_log(LOG, f"error {post['id']} -> {group_id}: {error}")
        print("ошибка:", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
