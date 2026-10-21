#!/usr/bin/env python3
"""Добавляет собранные euroki-книги в app/data/catalog.json.

Читает app/data/_bulk_manifest.json (его пишет parse_euroki_bulk.py),
создаёт/дополняет классы 3, 4, 10, 11 и не трогает книги 6–9.
Идемпотентен: повторный запуск обновляет записи, а не плодит дубли.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
CATALOG = DATA / "catalog.json"
MANIFESTS = (sorted(DATA.glob("_bulk_manifest*.json")) + sorted(DATA.glob("_gdz_manifest*.json"))
             + sorted(DATA.glob("_otvet_manifest*.json")) + sorted(DATA.glob("_gdzru_manifest*.json")))

SUBJECTS = {
    "math": ("Математика", "math"),
    "russian": ("Русский язык", "russian"),
    "english": ("Английский язык", "english"),
    "world": ("Окружающий мир", "world"),
    "literature": ("Литература", "literature"),
    "algebra": ("Алгебра", "algebra"),
    "geometry": ("Геометрия", "geometry"),
    "physics": ("Физика", "physics"),
    "chemistry": ("Химия", "chemistry"),
    "biology": ("Биология", "biology"),
    "history": ("История", "history"),
    "social": ("Обществознание", "social"),
    "geo": ("География", "geo"),
    "informatics": ("Информатика", "informatics"),
}
LITERATURE_PRIMARY = "Литературное чтение"


def main() -> int:
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    manifest = []
    for mf in MANIFESTS:
        if mf.exists():
            manifest.extend(json.loads(mf.read_text(encoding="utf-8")))
    by_grade = defaultdict(lambda: defaultdict(list))
    for e in manifest:
        if e.get("author"):
            e["author"] = re.sub(r"\s+([,;])", r"\1", e["author"])
            e["author"] = re.sub(r"\s+", " ", e["author"]).strip()
        path = DATA / e["file"]
        if not path.exists():
            continue
        by_grade[int(e["grade"])][e["subject"]].append(e)

    grades = {g["id"]: g for g in cat["grades"]}
    for grade, subjects in sorted(by_grade.items()):
        gid = str(grade)
        g = grades.get(gid)
        if not g:
            g = {"id": gid, "title": f"{gid} класс", "active": True, "subjects": []}
            grades[gid] = g
        g["active"] = True
        existing = {s["id"]: s for s in g.get("subjects", [])}
        for sid, entries in sorted(subjects.items()):
            title, icon = SUBJECTS[sid]
            if grade in (3, 4) and sid == "literature":
                title = LITERATURE_PRIMARY
            subj = existing.get(sid)
            if not subj:
                subj = {"id": sid, "title": title, "active": True, "textbooks": [], "icon": icon}
                existing[sid] = subj
            subj["active"] = True
            subj["title"] = title
            subj["icon"] = icon
            books = {b["id"]: b for b in subj.get("textbooks", [])}
            for e in entries:
                book = {
                    "id": e["id"],
                    "title": e["title"],
                    "author": e["author"],
                    "year": e["year"],
                    "file": e["file"],
                }
                books[e["id"]] = book
            # одинаковые подписи у разных изданий — добавляем год
            seen_titles = defaultdict(int)
            for book in books.values():
                seen_titles[book["title"]] += 1
            for book in books.values():
                if seen_titles[book["title"]] > 1 and f"({book['year']})" not in book["title"]:
                    book["title"] = f"{book['title']} ({book['year']})"
            subj["textbooks"] = sorted(books.values(), key=lambda b: (b["title"].lower(), b["year"]))
        g["subjects"] = sorted(existing.values(), key=lambda s: list(SUBJECTS).index(s["id"]) if s["id"] in SUBJECTS else 99)
    cat["grades"] = sorted(grades.values(), key=lambda g: int(g["id"]))
    CATALOG.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = sum(len(s["textbooks"]) for g in cat["grades"] for s in g.get("subjects", []))
    print(f"каталог: {len(cat['grades'])} классов, {total} учебников")
    for g in cat["grades"]:
        print(f"  {g['id']}: " + ", ".join(f"{s['title']} {len(s['textbooks'])}" for s in g.get("subjects", [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
