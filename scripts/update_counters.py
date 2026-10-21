#!/usr/bin/env python3
"""Обновляет статические счётчики в HTML и README по app/data/stats.json.

Динамически числа подтягивают assets/script.js и app/assets/script.js, но
поисковикам и пользователям без JS нужны актуальные цифры в разметке.

Запуск из корня репозитория:
    python3 scripts/update_counters.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
STATS = DATA / "stats.json"
CATALOG = DATA / "catalog.json"

HTML_FILES = sorted(ROOT.glob("*.html")) + [ROOT / "app" / "index.html"]


def ru(number: int) -> str:
    return f"{number:,}".replace(",", " ")


def tasks_word(number: int) -> str:
    tail = number % 100
    if tail in (11, 12, 13, 14):
        return "заданий"
    return {1: "задание", 2: "задания", 3: "задания", 4: "задания"}.get(number % 10, "заданий")


def books_word(number: int) -> str:
    tail = number % 100
    if tail in (11, 12, 13, 14):
        return "книгам"
    return "книге" if number % 10 == 1 else "книгам"


def subjects_count() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    ids = {s["id"] for g in catalog["grades"] for s in g.get("subjects", [])}
    return len(ids)


def main() -> int:
    if not STATS.exists():
        print("нет app/data/stats.json — сначала соберите данные")
        return 2
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    total = int(stats.get("total", 0))
    textbooks = int(stats.get("textbooks", 0))
    subjects = subjects_count()
    if not total or not textbooks:
        print("в stats.json нулевые счётчики")
        return 2
    ball = f"{ru(total)} заданий · {textbooks} учебников · {subjects} предметов"
    grade5 = (stats.get("grades") or {}).get("5") or {}
    g5_total = int(grade5.get("total") or 0)
    g5_books = int(grade5.get("textbooks") or 0)
    g5_text = (f"в 5 классе — {ru(g5_total)} {tasks_word(g5_total)} "
               f"по {g5_books} {books_word(g5_books)}") if g5_total and g5_books else ""

    changed = 0
    for path in HTML_FILES:
        text = path.read_text(encoding="utf-8")
        before = text
        text = re.sub(
            r'(<span id="footer-stats">)[^<]*(</span>)',
            lambda m: m.group(1) + ball + m.group(2), text)
        text = re.sub(
            r'(<dt id="stat-tasks">)[^<]*(</dt>)',
            lambda m: m.group(1) + ru(total) + m.group(2), text)
        text = re.sub(
            r'(<dt id="stat-books">)[^<]*(</dt>)',
            lambda m: m.group(1) + str(textbooks) + m.group(2), text)
        text = re.sub(
            r'(<dt id="stat-subjects">)[^<]*(</dt>)',
            lambda m: m.group(1) + str(subjects) + m.group(2), text)
        text = re.sub(r"\d[\d ]* заданий по \d[\d ]* учебникам",
                      f"{ru(total)} заданий по {textbooks} учебникам", text)
        text = re.sub(r"заданий — \d[\d ]* по \d[\d ]* учебникам",
                      f"заданий — {ru(total)} по {textbooks} учебникам", text)
        text = re.sub(r"\d[\d ]* заданиям из \d[\d ]* учебников",
                      f"{ru(total)} заданиям из {textbooks} учебников", text)
        if g5_text:
            text = re.sub(r"в 5 классе — [\d ]+ задани[йя] по \d+ книгам", g5_text, text)
        if text != before:
            path.write_text(text, encoding="utf-8")
            changed += 1

    readme = ROOT / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        before = text
        text = re.sub(r"\d[\d ]* заданий по \d[\d ]* учебникам",
                      f"{ru(total)} заданий по {textbooks} учебникам", text)
        text = re.sub(r"\d[\d ]* заданий, \d[\d ]* учебников, \d+ предметов",
                      f"{ru(total)} заданий, {textbooks} учебников, {subjects} предметов", text)
        if text != before:
            readme.write_text(text, encoding="utf-8")
            changed += 1

    print(f"счётчики: {ball}; обновлено файлов: {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
