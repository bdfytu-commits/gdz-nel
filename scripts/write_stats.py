#!/usr/bin/env python3
"""Генерирует app/data/stats.json — лёгкие счётчики для лендинга и приложения.

Читает catalog.json (классы → предметы → учебники) и файлы учебников.
Счётчики верхнего уровня — сумма по всем классам (лендинг), grades.<id> —
по конкретному классу (приложение).
Запуск: uv run python scripts/write_stats.py  (из корня gdz-nel)
"""
import json
import pathlib
import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"


def empty_scope() -> dict:
    return {"subjects": {}, "books": {}, "total": 0, "textbooks": 0}


def main() -> None:
    catalog = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
    out = {
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "subjects": {},
        "books": {},
        "grades": {},
        "total": 0,
        "textbooks": 0,
    }

    for grade in catalog["grades"]:
        scope = empty_scope()
        for subject in grade.get("subjects", []):
            count = 0
            for book in subject.get("textbooks", []):
                path = DATA / book["file"]
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    book_count = len(data.get("tasks", []))
                    count += book_count
                    scope["books"][book["file"]] = book_count
                    scope["textbooks"] += 1
                except (OSError, json.JSONDecodeError) as exc:
                    print(f"пропуск {path}: {exc}")
            scope["subjects"][subject["id"]] = {
                "title": subject["title"],
                "icon": subject.get("icon", subject["id"]),
                "tasks": count,
            }
            scope["total"] += count

        out["grades"][grade["id"]] = {
            "title": grade["title"],
            "subjects": scope["subjects"],
            "books": scope["books"],
            "total": scope["total"],
            "textbooks": scope["textbooks"],
        }

        # верхний уровень — сумма по всем классам
        out["total"] += scope["total"]
        out["textbooks"] += scope["textbooks"]
        out["books"].update(scope["books"])
        for subject_id, info in scope["subjects"].items():
            if subject_id in out["subjects"]:
                out["subjects"][subject_id]["tasks"] += info["tasks"]
            else:
                out["subjects"][subject_id] = dict(info)

    target = DATA / "stats.json"
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"stats.json готов: {out['total']} заданий, {out['textbooks']} учебников, "
          f"{len(out['grades'])} классов")


if __name__ == "__main__":
    main()
