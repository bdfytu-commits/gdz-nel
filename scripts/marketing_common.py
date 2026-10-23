#!/usr/bin/env python3
"""Общие функции для легального маркетинга ГДЗ НЭЛ.

Только стандартная библиотека: скрипты должны запускаться на сервере без
установки зависимостей. Секреты читаются из окружения, затем из .env и
.env.keys. Значения из окружения имеют приоритет.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_FILE = ROOT / "docs" / "MARKETING_POSTS.md"
LOG_DIR = Path("/tmp")


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_env() -> dict[str, str]:
    """Окружение > .env > .env.keys. Секреты не печатаем."""
    values = dict(os.environ)
    for name in (".env", ".env.keys"):
        for key, value in _parse_env_file(ROOT / name).items():
            values.setdefault(key, value)
    return values


def parse_posts(section: str) -> list[dict[str, str]]:
    """Достаёт посты из docs/MARKETING_POSTS.md.

    Формат: секция ``## Telegram`` или ``## VK``, внутри заголовки
    ``### tg01 — ...`` и текст до следующего ``###``. Markdown-заголовки
    в тело поста не попадают.
    """
    if not POSTS_FILE.exists():
        raise FileNotFoundError(POSTS_FILE)
    text = POSTS_FILE.read_text(encoding="utf-8")
    start = re.search(rf"^##\s+{re.escape(section)}\s*$", text, flags=re.M)
    if not start:
        raise ValueError(f"в {POSTS_FILE} нет секции ## {section}")
    tail = text[start.end():]
    next_section = re.search(r"^##\s+\S", tail, flags=re.M)
    if next_section:
        tail = tail[:next_section.start()]

    matches = list(re.finditer(r"^###\s+(\S+)[^\n]*\n", tail, flags=re.M))
    posts: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(tail)
        body = tail[match.end():body_end].strip()
        body = re.sub(r"^\s*---\s*$", "", body, flags=re.M).strip()
        if body:
            posts.append({"id": match.group(1).strip(), "text": body})
    return posts


def append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{date.today().isoformat()} {message}\n")


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def daily_post(posts: list[dict[str, str]], state: dict, force: bool = False) -> tuple[int, dict]:
    """Возвращает индекс поста на сегодня и обновлённое состояние.

    Один и тот же пост не отправляется повторно в один день. При новом дне
    указатель сдвигается на следующий пост.
    """
    today = date.today().isoformat()
    if force or state.get("date") != today:
        index = (int(state.get("index", -1)) + 1) % len(posts)
        state = {"date": today, "index": index, "sent": []}
    return int(state.get("index", 0)), state


def telegram_token(env: dict[str, str]) -> str:
    return (env.get("TELEGRAM_BOT_TOKEN") or "").strip()


def telegram_channels(env: dict[str, str]) -> list[str]:
    raw = env.get("TELEGRAM_CHANNEL_IDS") or env.get("TELEGRAM_CHANNEL_ID") or ""
    channels = [item.strip() for item in re.split(r"[,;\s]+", raw) if item.strip()]
    config = ROOT / "marketing" / "tg_channels.txt"
    if config.exists():
        for line in config.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                channels.append(line)
    result: list[str] = []
    for channel in channels:
        if channel not in result:
            result.append(channel)
    return result


def vk_token(env: dict[str, str]) -> str:
    for key in ("VK_ACCESS_TOKEN", "VK_TOKEN", "VK_SERVICE_TOKEN"):
        value = (env.get(key) or "").strip()
        if value:
            return value
    return ""
