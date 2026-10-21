#!/usr/bin/env python3
"""Проверка JSON-данных сайта по схеме docs/data-schema.json (jsonschema).

Использование:
    uv run --with jsonschema scripts/validate_data.py

Проверяет:
  * app/data/catalog.json       — по схеме $defs.catalog
  * app/data/stats.json         — по схеме $defs.stats
  * app/data/<subject>/*.json   — по схеме $defs.book (кроме catalog/stats)
  * дополнительно: уникальность номеров задач, совпадение состава каталога,
    файлов и счётчиков stats.json.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
SCHEMA_FILE = ROOT / "docs" / "data-schema.json"


def load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    schema = load(SCHEMA_FILE)["$defs"]
    errors: list[str] = []

    metadata = [DATA / "catalog.json", DATA / "stats.json"]
    books = sorted(DATA.glob("*/*.json"))
    book_counts: dict[str, int] = {}
    total_tasks = 0

    def check_meta(path: Path, kind: str) -> object:
        try:
            data = load(path)
        except json.JSONDecodeError as err:
            errors.append(f"{path}: не JSON ({err})")
            return None
        try:
            jsonschema.validate(data, schema[kind])
        except jsonschema.ValidationError as err:
            where = "/".join(str(p) for p in err.absolute_path)
            errors.append(f"{path}: {err.message} ({where or 'корень'})")
            return None
        return data

    def check_book(path: Path) -> None:
        nonlocal total_tasks
        rel = path.relative_to(DATA).as_posix()
        try:
            data = load(path)
        except json.JSONDecodeError as err:
            errors.append(f"{path}: не JSON ({err})")
            return
        try:
            jsonschema.validate(data, schema["book"])
        except jsonschema.ValidationError as err:
            where = "/".join(str(p) for p in err.absolute_path)
            errors.append(f"{path}: {err.message} ({where or 'корень'})")
            return

        numbers = [t["number"] for t in data["tasks"]]
        dupes = sorted(n for n, count in Counter(numbers).items() if count > 1)
        if dupes:
            errors.append(f"{path}: дубли номеров задач: {dupes[:5]}")
        if data["textbook"] != path.stem:
            errors.append(f"{path}: textbook «{data['textbook']}» не совпадает с именем файла")
        for task in data["tasks"]:
            for src in task.get("images", []):
                if src.startswith("data/") and not (DATA.parent / src).exists():
                    errors.append(f"{path}: нет файла картинки {src} (задача {task['number']})")
        book_counts[rel] = len(data["tasks"])
        total_tasks += len(data["tasks"])

    catalog = check_meta(DATA / "catalog.json", "catalog")
    stats = check_meta(DATA / "stats.json", "stats")
    for path in books:
        check_book(path)

    # --- согласованность каталога, файлов и счётчиков ---
    catalog_files: list[str] = []
    if isinstance(catalog, dict):
        for grade in catalog.get("grades", []):
            for subject in grade.get("subjects", []):
                for book in subject.get("textbooks", []):
                    catalog_files.append(book["file"])

    catalog_set = set(catalog_files)
    disk_set = set(book_counts)
    if len(catalog_files) != len(catalog_set):
        errors.append(f"catalog.json: повторяющиеся файлы учебников ({len(catalog_files)} ссылок на {len(catalog_set)} файлов)")
    for rel in sorted(catalog_set - disk_set):
        errors.append(f"catalog.json: нет файла {rel}")
    for rel in sorted(disk_set - catalog_set):
        errors.append(f"лишний файл вне каталога: {rel}")

    if isinstance(stats, dict):
        if stats.get("textbooks") != len(book_counts):
            errors.append(f"stats.json: textbooks={stats.get('textbooks')}, а книг {len(book_counts)}")
        if stats.get("total") != total_tasks:
            errors.append(f"stats.json: total={stats.get('total')}, а заданий {total_tasks}")
        stats_books = stats.get("books") or {}
        if set(stats_books) != disk_set:
            errors.append(
                f"stats.json: список books не совпадает с файлами "
                f"(нет в stats: {len(disk_set - set(stats_books))}, лишних: {len(set(stats_books) - disk_set)})"
            )
        for rel, count in book_counts.items():
            if rel in stats_books and stats_books[rel] != count:
                errors.append(f"stats.json: {rel}={stats_books[rel]}, а в файле {count}")
        if sum(book_counts.values()) != sum(stats_books.values()):
            errors.append("stats.json: сумма books не совпадает с суммой заданий в файлах")

    for message in errors:
        print("ОШИБКА:", message)
    print(
        f"книг: {len(book_counts)}; ссылок в каталоге: {len(catalog_files)}; "
        f"метаданных: {len(metadata)}; всего JSON: {len(book_counts) + len(metadata)}; "
        f"заданий: {total_tasks}; ошибок: {len(errors)}"
    )
    if not errors and len(book_counts) == len(catalog_files):
        print(f"сверка: {len(book_counts)}={len(catalog_files)} — книги, каталог и stats.json согласованы")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
