#!/usr/bin/env python3
"""
ГДЗ НЭЛ — лёгкий поисковый индекс для страницы /search.html (Ф17).

Из всех учебников собирается компактный файл app/data/search-index.json:
по одной записи на задание — номер, книга, класс, предмет, раздел и
укороченное условие. Полные условия на страницу поиска не грузятся:
индекс ~ в 20 раз легче исходников.

Запуск (из корня репозитория):
    python3 scripts/build_search_index.py
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app" / "data"
OUT = DATA / "search-index.json"

SNIPPET_LIMIT = 150


def short(text: str, limit: int = SNIPPET_LIMIT) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit * 0.6 else cut) + "…"


def catalog_index() -> dict[str, dict]:
    """book_id -> класс/предмет/название по catalog.json"""
    index: dict[str, dict] = {}
    try:
        catalog = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return index

    for grade in catalog.get("grades", []):
        for subject in grade.get("subjects", []):
            for book in subject.get("textbooks", []):
                index[book["id"]] = {
                    "grade": grade["id"],
                    "subject": subject["id"],
                    "subjectTitle": subject.get("title", subject["id"]),
                    "bookTitle": book.get("title", book["id"]),
                }
    return index


def main() -> None:
    books = catalog_index()
    records = []

    for path in sorted(DATA.glob("*/*.json")):
        if path.name in ("catalog.json", "stats.json", "search-index.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            print(f"  ! {path.name}: {err}")
            continue

        book_id = data.get("textbook") or path.stem
        info = books.get(book_id, {})
        subject = data.get("subject") or info.get("subject", "")
        subject_title = info.get("subjectTitle") or subject
        grade = info.get("grade")
        book_title = info.get("bookTitle") or data.get("title") or book_id

        for task in data.get("tasks", []):
            number = str(task.get("number", "")).strip()
            if not number:
                continue
            records.append({
                "b": book_id,          # книга
                "n": number,           # номер задания
                "g": str(grade or ""), # класс
                "s": subject,          # предмет (код)
                "st": subject_title,   # предмет (подпись)
                "bt": book_title,      # учебник
                "sec": short(task.get("section", ""), 70),
                "c": short(task.get("condition", "")),
            })

    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(records),
        "tasks": records,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    size = OUT.stat().st_size
    print(f"готово: {len(records)} заданий, {size / 1024:.0f} КБ -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
