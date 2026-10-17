#!/usr/bin/env python3
"""Проверка JSON-данных сайта по схеме docs/data-schema.json (jsonschema).

Использование:
    uv run --with jsonschema scripts/validate_data.py

Проверяет:
  * app/data/catalog.json       — по схеме $defs.catalog
  * app/data/stats.json         — по схеме $defs.stats
  * app/data/<subject>/*.json   — по схеме $defs.book (кроме catalog/stats)
  * дополнительно: уникальность номеров задач внутри учебника
"""

from __future__ import annotations

import json
import sys
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
    checked = 0

    def check(path: Path, kind: str) -> None:
        nonlocal checked
        checked += 1
        try:
            data = load(path)
        except json.JSONDecodeError as err:
            errors.append(f"{path}: не JSON ({err})")
            return
        try:
            jsonschema.validate(data, schema[kind])
        except jsonschema.ValidationError as err:
            where = "/".join(str(p) for p in err.absolute_path)
            errors.append(f"{path}: {err.message} ({where or 'корень'})")
            return
        if kind == "book":
            numbers = [t["number"] for t in data["tasks"]]
            dupes = {n for n in numbers if numbers.count(n) > 1}
            if dupes:
                errors.append(f"{path}: дубли номеров задач: {sorted(dupes)[:5]}")
            if data["textbook"] != path.stem:
                errors.append(f"{path}: textbook «{data['textbook']}» не совпадает с именем файла")

    check(DATA / "catalog.json", "catalog")
    check(DATA / "stats.json", "stats")
    for path in sorted(DATA.glob("*/*.json")):
        check(path, "book")

    for message in errors:
        print("ОШИБКА:", message)
    print(f"проверено файлов: {checked}, ошибок: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
