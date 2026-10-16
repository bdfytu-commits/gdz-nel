#!/usr/bin/env python3
"""Генерирует app/data/stats.json — лёгкие счётчики для лендинга и приложения.

Читает catalog.json и файлы учебников, считает количество заданий.
Запуск: uv run python scripts/write_stats.py  (из корня gdz-nel)
"""
import json
import pathlib
import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"


def main() -> None:
    catalog = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
    out = {"generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "subjects": {}, "books": {}, "total": 0, "textbooks": 0}

    for subject in catalog["subjects"]:
        count = 0
        for book in subject.get("textbooks", []):
            path = DATA / book["file"]
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                book_count = len(data.get("tasks", []))
                count += book_count
                out["books"][book["file"]] = book_count
                out["textbooks"] += 1
            except (OSError, json.JSONDecodeError) as exc:
                print(f"пропуск {path}: {exc}")
        out["subjects"][subject["id"]] = {
            "title": subject["title"],
            "icon": subject.get("icon", subject["id"]),
            "tasks": count,
        }
        out["total"] += count

    target = DATA / "stats.json"
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"stats.json готов: {out['total']} заданий, {out['textbooks']} учебников")


if __name__ == "__main__":
    main()
