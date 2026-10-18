#!/usr/bin/env python3
"""разовый фикс уже собранных данных: latex-формулы → читаемый текст.

конвертер живёт в parse_gdz.py (_latex_to_text) и применяется при будущих
прогонах парсера; этот скрипт прогоняет его по существующим json.
трогает только поля, где есть «\\» или «$» (сейчас это 6 задач виленкина-6-1:
2.507, 2.511, 2.512, 2.515, 2.516, 2.539), плюс ручные правки.

запуск: uv run --no-project python scripts/fix_latex.py
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parse_gdz import _latex_to_text  # noqa: E402

DATA = os.path.join(ROOT, "app", "data")

# ручные правки после конвертера: (файл, номер, поле) → итоговый текст
MANUAL = {
    ("vilenkin-6-1.json", "2.511", "answer"): "а) 1 1/3; б) 11 2/3; в) 5/18; г) 5",
}


def postfix(filename: str, number: str, fld: str, s: str) -> str:
    """мелкая вычитка только по математике виленкина-6-1 (в других книгах латиница «a)» легитимна)"""
    if filename != "vilenkin-6-1.json":
        return s
    s = re.sub(r"(?<![A-Za-zА-Яа-яЁё])a\)", "а)", s)  # a) → а)
    s = re.sub(r"(?m)^\s*6\)\s*(?=\()", "б) ", s)  # распознанный «6)» с «(» — это «б)»
    if fld == "answer":
        s = re.sub(r"^=\s+", "", s)  # хвост от разорванной формулы в начале ответа
    return s


def clean(text: str) -> str:
    lines = [l.strip() for l in _latex_to_text(text).split("\n")]
    return "\n".join(l for l in lines if l)


def detect_indent(raw: str) -> int:
    m = re.match(r"\{\n( +)", raw)
    return len(m.group(1)) if m else 2


def main() -> int:
    changed = []
    for dirpath, _dirs, files in os.walk(DATA):
        for fn in sorted(files):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(dirpath, fn)
            raw = open(path, encoding="utf-8").read()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            tasks = data.get("tasks")
            if not isinstance(tasks, list):
                continue
            dirty = False
            for t in tasks:
                number = str(t.get("number", ""))
                for fld in ("condition", "solution", "answer"):
                    val = t.get(fld)
                    if not isinstance(val, str) or ("$$" not in val and "\\frac" not in val):
                        continue
                    new = postfix(fn, number, fld, clean(val)).strip()
                    manual = MANUAL.get((fn, number, fld))
                    if manual is not None:
                        new = manual
                    if new != val:
                        t[fld] = new
                        dirty = True
            if dirty:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(data, ensure_ascii=False, indent=detect_indent(raw)) + "\n")
                changed.append(os.path.relpath(path, ROOT))
    for p in changed:
        print("изменён:", p)
    print("файлов изменено:", len(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
