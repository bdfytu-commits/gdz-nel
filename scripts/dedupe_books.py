#!/usr/bin/env python3
"""Убирает дубли учебников и битые «части» после массового парсинга.

Две проблемы:
  * один и тот же учебник пришёл из euroki и gdz-raketa — в каталоге две
    карточки с одинаковым названием и автором;
  * при обрыве парсера остался файл `book.json` с парой заданий, хотя рядом
    лежат полноценные `book-1.json` и `book-2.json`.

Скрипт без `--apply` только показывает, что нашёл. С `--apply` удаляет
проигравшие файлы и вычищает их из catalog.json.

    python3 scripts/dedupe_books.py
    python3 scripts/dedupe_books.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
CATALOG = DATA / "catalog.json"


def tasks_of(path: Path) -> int:
    try:
        return len(json.loads(path.read_text(encoding="utf-8")).get("tasks") or [])
    except (OSError, json.JSONDecodeError):
        return -1


def norm(value: str) -> str:
    value = re.sub(r"\s*\(\d{4}\)\s*$", "", str(value or "")).strip().lower()
    return re.sub(r"\s+", " ", value)


def part_of(book_id: str) -> str:
    m = re.search(r"-(\d+)$", book_id)
    return m.group(1) if m else ""


def merge_key(book: dict) -> tuple:
    return (norm(book.get("title", "")), norm(book.get("author", "")), part_of(book["id"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    removals: dict[str, str] = {}  # file -> причина

    for grade in catalog.get("grades", []):
        for subject in grade.get("subjects", []):
            books = subject.get("textbooks", [])
            info = {}
            for book in books:
                path = DATA / book["file"]
                info[book["id"]] = {"book": book, "tasks": tasks_of(path) if path.exists() else -1}

            # 1. битые огрызки: X.json при живых X-1.json / X-2.json
            for bid, meta in list(info.items()):
                if not re.fullmatch(r".+", bid) or re.search(r"-\d+$", bid):
                    continue
                sibs = [other for other in info if re.fullmatch(re.escape(bid) + r"-\d+", other)]
                if not sibs:
                    continue
                best_sib = max(info[other]["tasks"] for other in sibs)
                if meta["tasks"] < best_sib:
                    removals[meta["book"]["file"]] = f"огрызок {bid} ({meta['tasks']} против {best_sib})"

            # 2. одинаковые книги из разных источников
            groups: dict[tuple, list[str]] = defaultdict(list)
            for bid, meta in info.items():
                if meta["book"]["file"] in removals:
                    continue
                groups[merge_key(meta["book"])].append(bid)
            for key, ids in groups.items():
                if len(ids) < 2:
                    continue
                ids.sort(key=lambda b: info[b]["tasks"], reverse=True)
                leader = ids[0]
                for loser in ids[1:]:
                    leader_year = info[leader]["book"].get("year")
                    loser_year = info[loser]["book"].get("year")
                    if leader_year and loser_year and str(leader_year) != str(loser_year):
                        continue  # разные издания с одинаковым названием
                    # не трогаем записи с тем же числом заданий — возможно, это
                    # разные издания с совпавшим названием
                    if info[loser]["tasks"] == info[leader]["tasks"] and info[loser]["tasks"] > 0:
                        continue
                    removals[info[loser]["book"]["file"]] = (
                        f"дубль «{info[leader]['book'].get('title')}»: "
                        f"{leader} — {info[leader]['tasks']}, {loser} — {info[loser]['tasks']}")

    if not removals:
        print("дублей и огрызков нет")
        return 0

    print(f"найдено {len(removals)} лишних файлов:")
    for rel, why in sorted(removals.items()):
        print(f"  {rel}: {why}")

    if not args.apply:
        print("это предпросмотр, запусти с --apply, чтобы применить")
        return 0

    remove_set = set(removals)
    for grade in catalog.get("grades", []):
        for subject in grade.get("subjects", []):
            subject["textbooks"] = [b for b in subject.get("textbooks", []) if b["file"] not in remove_set]
            subject["textbooks"] = sorted(
                subject["textbooks"], key=lambda b: (b.get("title", "").lower(), b.get("year", 0)))

    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for rel in sorted(remove_set):
        path = DATA / rel
        if path.exists():
            path.unlink()
            print("удалён файл", rel)
    print("готово")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
