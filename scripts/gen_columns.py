#!/usr/bin/env python3
"""
ГДЗ НЭЛ — генератор решений «в столбик» (этап 2.0, Ф4).

Ищет в текстах решений простые арифметические вычисления
(сложение, вычитание, умножение), проверяет их правильность и
добавляет в задачу поле "column_solution" — уже свёрстанное
моноширинным текстом вычисление в столбик.

Осторожность важнее охвата:
  - столбик появляется только там, где вычисление проверено
    (a × b = c, a + b = c, a − b = c);
  - десятичные дроби и проценты не трогаем (5.5 · 10, 175%);
  - деление в столбик не строим — у него другая схема записи.

Запуск:
  uv run --no-project python scripts/gen_columns.py            # все книги
  uv run --no-project python scripts/gen_columns.py vilenkin-6-1
  uv run --no-project python scripts/gen_columns.py --reset vilenkin-6-1
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "app" / "data"

NUMBER = r"\d[\d\s]{0,11}\d|\d"
MUL_RE = re.compile(r"(%s)\s*[·×xX*]\s*(%s)\s*=\s*(%s)" % (NUMBER, NUMBER, NUMBER))
ADD_RE = re.compile(r"(%s)\s*\+\s*(%s)\s*=\s*(%s)" % (NUMBER, NUMBER, NUMBER))
SUB_RE = re.compile(r"(%s)\s*[−–—]\s*(%s)\s*=\s*(%s)" % (NUMBER, NUMBER, NUMBER))
SUB_ASCII_RE = re.compile(r"(%s)\s*-\s*(%s)\s*=\s*(%s)" % (NUMBER, NUMBER, NUMBER))


def to_int(raw: str):
    digits = re.sub(r"\s+", "", raw)
    return int(digits) if digits.isdigit() else None


def clean_context(text: str, match, *groups: int) -> bool:
    """отсекаем десятичные дроби, проценты и прочий контекст"""
    for g in groups:
        start, end = match.span(g)
        before = text[start - 1] if start > 0 else " "
        after = text[end] if end < len(text) else " "
        if before in ".,:" or after in ".,:":  # 3,5 · 10 или 5.5
            return False
        tail = text[end:end + 3].lstrip()
        if tail.startswith("%"):  # 175% − 100%
            return False
        head = text[max(0, start - 3):start]
        if head.rstrip().endswith(("%",)) or re.search(r"[\d.,](?=\s*$)", head):
            return False
    return True


def mul_column(a: int, b: int) -> str:
    c = a * b
    width = max(len(str(a)), len(str(b)) + 1, len(str(c)))
    partials = []
    # промежуточные произведения пишем, только если множитель двухзначный
    if len(str(b)) >= 2 and all(d != "0" for d in str(b)):
        for i, d in enumerate(reversed(str(b))):
            part = a * int(d)
            partials.append((part, i))
            width = max(width, len(str(part)) + i)
    lines = [str(a).rjust(width), ("\u00d7" + str(b)).rjust(width), "-" * width]
    for part, shift in partials:
        lines.append(str(part).rjust(width - shift))
    if partials:
        lines.append("-" * width)
    lines.append(str(c).rjust(width))
    return "\n".join(lines)


def add_column(a: int, op: str, b: int, c: int) -> str:
    width = max(len(str(a)), len(str(b)) + 1, len(str(c)))
    return "\n".join([
        str(a).rjust(width),
        (op + str(b)).rjust(width),
        "-" * width,
        str(c).rjust(width),
    ])


def find_column(solution: str):
    """первое проверяемое вычисление — предпочитаем «покрупнее»"""
    best = None

    for m in MUL_RE.finditer(solution):
        if not clean_context(solution, m, 1, 2, 3):
            continue
        a, b, c = to_int(m.group(1)), to_int(m.group(2)), to_int(m.group(3))
        if a is None or b is None or c is None:
            continue
        if a * b != c or a < 10 or c < 100:
            continue
        weight = 2 * (len(str(a)) + len(str(b)))
        if best is None or weight > best[0]:
            best = (weight, mul_column(a, b))

    for regex, op, fn in ((ADD_RE, "+", lambda x, y: x + y),
                          (SUB_RE, "\u2212", lambda x, y: x - y),
                          (SUB_ASCII_RE, "\u2212", lambda x, y: x - y)):
        for m in regex.finditer(solution):
            if not clean_context(solution, m, 1, 2, 3):
                continue
            a, b, c = to_int(m.group(1)), to_int(m.group(2)), to_int(m.group(3))
            if a is None or b is None or c is None:
                continue
            if fn(a, b) != c or a < 100 or b < 100 or c < 100:
                continue
            weight = len(str(a)) + len(str(b)) - 2
            if best is None or weight > best[0]:
                best = (weight, add_column(a, op, b, c))

    return best[1] if best else None


def process_file(path: Path, reset: bool) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for task in data.get("tasks", []):
        if reset:
            task.pop("column_solution", None)
        if task.get("column_solution"):
            continue
        solution = task.get("solution") or ""
        if len(solution) > 600:
            continue  # большие решения — текстовые, не вычисления
        column = find_column(solution)
        if column:
            task["column_solution"] = column
            changed += 1
    if changed or reset:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return changed


def main():
    args = sys.argv[1:]
    reset = "--reset" in args
    only = [a for a in args if not a.startswith("--")] or None

    total = 0
    for path in sorted(DATA_DIR.glob("*/*.json")):
        if path.name in ("catalog.json", "stats.json"):
            continue
        if only and path.stem not in only:
            continue
        n = process_file(path, reset)
        if n:
            print(f"{path.name}: столбиков добавлено {n}")
        total += n
    print(f"итого: {total}")


if __name__ == "__main__":
    main()
