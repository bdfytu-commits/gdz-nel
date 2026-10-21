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
# Cloudflare Pages не принимает файлы больше ~25 МБ, поэтому крупный
# индекс режем на части по 18 МБ, а в search-index.json кладём манифест.
SHARD_LIMIT = 18 * 1024 * 1024


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
    }
    body = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    size = len(body.encode("utf-8"))

    for old in DATA.glob("search-index-*.json"):
        old.unlink()

    if size <= SHARD_LIMIT:
        payload["tasks"] = records
        OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        print(f"готово: {len(records)} заданий, {OUT.stat().st_size / 1024:.0f} КБ -> {OUT.relative_to(ROOT)}")
        return

    # режем на шарды, чтобы каждый файл проходил лимит Cloudflare Pages
    shards: list[str] = []
    chunk: list[dict] = []
    chunk_size = 0
    for record in records:
        record_size = len(json.dumps(record, ensure_ascii=False, separators=(",", ":"))) + 1
        if chunk and chunk_size + record_size > SHARD_LIMIT:
            name = f"search-index-{len(shards) + 1}.json"
            (DATA / name).write_text(
                json.dumps({"tasks": chunk}, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8")
            shards.append(name)
            chunk = []
            chunk_size = 0
        chunk.append(record)
        chunk_size += record_size
    if chunk:
        name = f"search-index-{len(shards) + 1}.json"
        (DATA / name).write_text(
            json.dumps({"tasks": chunk}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
        shards.append(name)

    payload["shards"] = shards
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"готово: {len(records)} заданий, {len(shards)} шардов по ~{SHARD_LIMIT / 1024 / 1024:.0f} МБ"
          f" -> {OUT.relative_to(ROOT)}")
    for name in shards:
        print(f"  {name}: {(DATA / name).stat().st_size / 1024 / 1024:.1f} МБ")


if __name__ == "__main__":
    main()
