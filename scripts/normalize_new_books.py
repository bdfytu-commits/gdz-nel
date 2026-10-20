#!/usr/bin/env python3
"""Нормализует только новые (untracked) JSON-книги после массового парсинга.

- убирает дубли ответа, когда `answer` целиком повторяет `solution`;
- заполняет пустые `section`/`condition`;
- выбрасывает задачи без решения и без картинок;
- схлопывает полностью одинаковые задачи;
- чистит автора от «Части: 1 и 2» и лишних пробелов.

Старые книги 6–9 классов не трогаются: берутся только untracked-файлы git.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def new_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "app/data"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [ROOT / p for p in out if p.endswith(".json") and "/_" not in p]


def last_line(text: str) -> str:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    return lines[-1][:1000] if lines else ""


def main() -> int:
    changed = 0
    removed = 0
    total = 0
    paths = new_files()
    for path in paths:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if "tasks" not in doc:
            continue
        tasks = doc.get("tasks") or []
        file_changed = False
        out = []
        seen = set()
        used_numbers = set()
        for task in tasks:
            solution = str(task.get("solution") or "").strip()
            images = task.get("images") or []
            if not solution and not images:
                removed += 1
                continue
            number = str(task.get("number") or "").strip()
            if not number:
                number = str(len(out) + 1)
            base_number = number
            suffix = 1
            while number in used_numbers:
                suffix += 1
                number = f"{base_number}-{suffix}"
            if number != base_number:
                file_changed = True
            used_numbers.add(number)
            task["number"] = number
            section = str(task.get("section") or "").strip()
            if not section:
                base = number.split(".")[0]
                section = f"Страница {base}" if base.isdigit() else f"Задание {base}"
                task["section"] = section
                file_changed = True
            if not str(task.get("condition") or "").strip():
                task["condition"] = f"Задание {number}."
                file_changed = True
            answer = str(task.get("answer") or "").strip()
            if answer and answer == solution:
                task["answer"] = last_line(solution)
            key = (
                task.get("number"), task.get("section"), task.get("condition"),
                task.get("solution"), tuple(task.get("images") or []),
            )
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            out.append(task)
        if len(out) != len(tasks):
            doc["tasks"] = out
            file_changed = True
        author = str(doc.get("author") or "")
        author = re.sub(r"\s+Части?:\s*.*$", "", author)
        author = re.sub(r"\s+([,;])", r"\1", author)
        author = re.sub(r"\s+", " ", author).strip(" .,")
        if author and author != doc.get("author"):
            doc["author"] = author
            file_changed = True
        if file_changed:
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed += 1
        total += len(out)
    print(f"новых книг: {len(paths)}, задач: {total}, изменено: {changed}, удалено дублей/пустых: {removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
