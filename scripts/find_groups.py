#!/usr/bin/env python3
"""Поиск открытых сообществ ВК по школьным запросам.

Используется только официальный VK API (groups.search + groups.getById).
Скрипт не вступает в группы, не пишет админам и не собирает закрытые чаты.
Нужен пользовательский токен VK с доступом к groups; положите его в
VK_ACCESS_TOKEN в .env.keys. Без токена скрипт создаёт честный отчёт
с инструкцией, а не выдумывает сообщества.

Запуск:
    python3 scripts/find_groups.py
    python3 scripts/find_groups.py --limit 100 --min-members 100
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from marketing_common import ROOT, load_env, vk_token

OUT = ROOT / "docs" / "TARGET_GROUPS.md"
API = "https://api.vk.com/method/"
API_VERSION = "5.199"
KEYWORDS = ("НЭЛ", "Новосибирск школа", "ГДЗ 6 класс", "домашка", "лицей")


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=False).replace("|", "\\|").replace("\n", " ")


def vk_call(method: str, token: str, **params) -> dict:
    query = {"access_token": token, "v": API_VERSION, **params}
    url = API + method + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"User-Agent": "GdzNelMarketing/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"VK HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"VK network: {error.reason}") from error
    if "error" in payload:
        message = payload["error"].get("error_msg", "unknown error")
        raise RuntimeError(f"VK API: {message}")
    return payload.get("response", {})


def search(token: str, query: str, limit: int) -> list[dict]:
    found: list[dict] = []
    offset = 0
    while len(found) < limit:
        page_size = min(100, limit - len(found))
        response = vk_call(
            "groups.search", token, q=query, type="group",
            count=page_size, offset=offset, sort=0,
        )
        items = response.get("items", []) if isinstance(response, dict) else []
        if not items:
            break
        found.extend(items)
        offset += len(items)
        if len(items) < page_size:
            break
        time.sleep(0.34)  # VK: не больше 3 запросов в секунду
    return found


def details(token: str, ids: list[int]) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        response = vk_call(
            "groups.getById", token,
            group_ids=",".join(str(item) for item in chunk),
            fields="members_count,contacts,description,links,is_closed,type",
        )
        groups = response.get("groups", []) if isinstance(response, dict) else response
        for group in groups or []:
            if isinstance(group, dict) and group.get("id"):
                result[int(group["id"])] = group
        time.sleep(0.34)
    return result


def group_link(group: dict) -> str:
    screen_name = str(group.get("screen_name") or "").strip()
    if screen_name:
        return f"https://vk.com/{screen_name}"
    return f"https://vk.com/club{group['id']}"


def admin_contact(group: dict) -> str:
    parts: list[str] = []
    for contact in group.get("contacts") or []:
        if not isinstance(contact, dict):
            continue
        user_id = contact.get("user_id")
        email = str(contact.get("email") or "").strip()
        note = str(contact.get("desc") or "").strip()
        if user_id:
            label = f"id{user_id}"
            parts.append(f"[{label}](https://vk.com/id{user_id})" + (f" — {note}" if note else ""))
        elif email:
            parts.append(email + (f" — {note}" if note else ""))
    for link in (group.get("links") or [])[:2]:
        if isinstance(link, dict) and link.get("url"):
            parts.append(str(link["url"]))
    return "; ".join(parts) or "нет публичных контактов"


def write_empty(reason: str) -> None:
    text = f"""# Целевые сообщества ВК

Дата: {date.today().isoformat()}

Статус: **не собрано**.

Причина: {reason}

## Что нужно

1. Создайте пользовательский токен VK с доступом к `groups` (и `wall` — для
   автопостинга в свою группу).
2. Добавьте в `.env.keys`:

```env
VK_ACCESS_TOKEN=...
VK_GROUP_ID=...
```

3. Запустите `python3 scripts/find_groups.py`.

Скрипт ищет только **открытые сообщества** через официальный
`groups.search`; закрытые чаты, личные страницы и участники не собираются.
Контакт админа берётся только из публичного блока `contacts` сообщества.

## Ключевые слова

{", ".join(KEYWORDS)}

## Таблица

| № | Название | Ссылка | Размер | Контакт админа |
|---:|---|---|---:|---|
| — | нет данных без VK_ACCESS_TOKEN | — | — | — |
"""
    OUT.write_text(text, encoding="utf-8")


def write_report(groups: list[dict], source: dict[int, dict]) -> None:
    lines = [
        "# Целевые сообщества ВК",
        "",
        f"Дата: {date.today().isoformat()}",
        "",
        f"Найдено открытых сообществ: **{len(groups)}**.",
        "Источник: официальный VK API, `groups.search` + `groups.getById`.",
        "В таблицу попадают только открытые сообщества; закрытые и чаты не включены.",
        "",
        "| № | Название | Ссылка | Размер | Контакт админа |",
        "|---:|---|---|---:|---|",
    ]
    for number, group in enumerate(groups, 1):
        full = source.get(int(group["id"]), group)
        members = full.get("members_count", group.get("members_count", 0)) or 0
        members_text = f"{int(members):,}".replace(",", " ")
        lines.append(
            f"| {number} | {esc(full.get('name'))} | {group_link(full)} | "
            f"{members_text} | {admin_contact(full)} |"
        )
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100, help="сколько сообществ собрать (50–100)")
    parser.add_argument("--min-members", type=int, default=0, help="минимальный размер")
    args = parser.parse_args()
    limit = max(0, min(args.limit, 100))

    env = load_env()
    token = vk_token(env)
    if not token:
        write_empty("в `.env.keys` нет `VK_ACCESS_TOKEN` (или `VK_TOKEN`).")
        print("нет VK_ACCESS_TOKEN. Отчёт создан: docs/TARGET_GROUPS.md")
        print("нужен пользовательский токен VK с доступом к groups; без него поиск не запускаю.")
        return 2

    seen: dict[int, dict] = {}
    try:
        for keyword in KEYWORDS:
            for group in search(token, keyword, max(40, limit // len(KEYWORDS) + 20)):
                group_id = int(group["id"])
                if group_id not in seen:
                    group["_keyword"] = keyword
                    seen[group_id] = group
            if len(seen) >= limit:
                break
    except RuntimeError as error:
        write_empty(str(error))
        print(f"ошибка VK API: {error}")
        return 1

    ids = list(seen)[:limit]
    try:
        source = details(token, ids)
    except RuntimeError as error:
        source = {}
        print(f"не удалось получить контакты: {error}")

    groups = []
    for group_id in ids:
        group = source.get(group_id, seen[group_id])
        if int(group.get("is_closed", 0) or 0) != 0:
            continue
        members = int(group.get("members_count", seen[group_id].get("members_count", 0)) or 0)
        if members < args.min_members:
            continue
        group["id"] = group_id
        groups.append(group)
    groups.sort(key=lambda item: int(item.get("members_count", 0) or 0), reverse=True)
    groups = groups[:limit]
    write_report(groups, source)
    print(f"найдено: {len(groups)}; отчёт: docs/TARGET_GROUPS.md")
    return 0 if groups else 1


if __name__ == "__main__":
    sys.exit(main())
