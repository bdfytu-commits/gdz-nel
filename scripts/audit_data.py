#!/usr/bin/env python3
"""Аудит данных ГДЗ НЭЛ.

Сканирует все учебники каталога, ищет битые символы, пустые задания,
подозрительно короткие условия, несовпадение номера и текста, а также
дубли целых книг, собранных только из картинок.

Использование:
  python3 scripts/audit_data.py                 # только отчёт
  python3 scripts/audit_data.py --apply         # отчёт + удаление мусора
  python3 scripts/audit_data.py --apply --json  # ещё и машинный отчёт

Отчёт: docs/DATA_AUDIT.md. Удалённые файлы складываются в
app/data/_audit_quarantine/ (каталог в .gitignore, на сайт не попадает).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter, defaultdict, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app" / "data"
CATALOG = DATA / "catalog.json"
REPORT = ROOT / "docs" / "DATA_AUDIT.md"
QUARANTINE = DATA / "_audit_quarantine"
REPORT_JSON = ROOT / "docs" / "data-audit.json"

BROKEN_RE = re.compile(r"\ufffd|[\u0000-\u0008\u000b\u000c\u000e-\u001f]|(?:Ð|Ñ|Â|Ã)[\x80-\xbf]")
PLACEHOLDER_RE = re.compile(
    r"^(?:\d+(?:[.,]\d+)?\s*[.)]?\s*)?(?:решение\s+на\s+изображении|ответ\s+на\s+изображении)\.?$",
    re.IGNORECASE,
)
EMPTY_ACTION_RE = re.compile(
    r"^(?:выполните\s+действие\s*:?|ход\s+решения\s*:?|решение\s*:?|см\.?\s*(?:решение|рисунок|изображение)|"
    r"смотри\s+(?:решение|рисунок|изображение))$",
    re.IGNORECASE,
)
LEADING_NUM_RE = re.compile(r"^\s*(?:№\s*)?(\d{1,4})(?:\s*[.)]|\s+)")
SECTION_NUM_RE = re.compile(r"^\s*(\d{1,3})[.)]\s+")
SENTENCE_RE = re.compile(r"[.!?…]")

WORD_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
STOPWORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще",
    "нет", "о", "из", "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли",
    "если", "уже", "или", "ни", "быть", "был", "него", "до", "вас", "нибудь",
    "опять", "уж", "вам", "ведь", "там", "потом", "себя", "ничего", "ей",
    "может", "они", "тут", "где", "есть", "надо", "ней", "для", "мы", "тебя",
    "их", "чем", "была", "сам", "чтоб", "без", "будто", "чего", "раз", "тоже",
    "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому",
    "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти",
    "мой", "тем", "чтобы", "нее", "были", "куда", "зачем", "всех", "никогда",
    "можно", "при", "наконец", "два", "об", "другой", "хоть", "после", "над",
    "больше", "тот", "через", "эти", "нас", "про", "всего", "них", "какая",
    "много", "разве", "три", "эту", "моя", "впрочем", "хорошо", "свою",
    "этой", "перед", "иногда", "лучше", "чуть", "том", "нельзя", "такой",
    "им", "более", "всегда", "конечно", "всю", "между",
}

SECTION_QUESTION_RE = re.compile(
    r"^(?:как|что|чем|почему|зачем|где|когда|какие|какой|какая|каково|сколько|"
    r"в\s+каком|с\s+какими|для\s+чего|о\s+чём|из\s+чего)\b",
    re.IGNORECASE,
)
TASK_VERB_RE = re.compile(
    r"^(?:прочитайте|спишите|выпишите|найдите|составьте|рассмотрите|придумайте|"
    r"объясните|определите|запишите|перепишите|ответьте|подберите|озаглавьте|"
    r"выполните|разберите|докажите|сравните|назовите|выделите|обозначьте|"
    r"расставьте|вставьте|раскройте|подчеркните|продолжите|перестройте|"
    r"исправьте|отредактируйте|подготовьте|расскажите)\b",
    re.IGNORECASE,
)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)


def norm_number(value: Any) -> str:
    return str(value if value is not None else "").strip().replace(",", ".")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def has_content(task: dict[str, Any]) -> bool:
    images = task.get("images") if isinstance(task.get("images"), list) else []
    return bool(
        clean_text(task.get("condition"))
        or clean_text(task.get("solution"))
        or clean_text(task.get("answer"))
        or clean_text(task.get("column_solution"))
        or images
    )


def look_like_placeholder(task: dict[str, Any]) -> bool:
    condition = clean_text(task.get("condition"))
    return bool(
        PLACEHOLDER_RE.match(condition)
        and not clean_text(task.get("solution"))
        and not clean_text(task.get("answer"))
        and (task.get("images") or [])
    )


def normalize_text(value: Any) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def content_tokens(value: Any) -> list[str]:
    words = WORD_RE.findall(normalize_text(value))
    return [word[:6] for word in words if len(word) > 1 and word not in STOPWORDS]


def token_overlap(left: Any, right: Any) -> float:
    a = set(content_tokens(left))
    b = set(content_tokens(right))
    if not a:
        return 0.0
    return len(a & b) / len(a)


def solution_copies_condition(task: dict[str, Any]) -> bool:
    condition = normalize_text(task.get("condition"))
    solution = normalize_text(task.get("solution"))
    if len(condition) < 40 or len(solution) < 40:
        return False
    if condition == solution or condition in solution:
        return True
    # Быстрый фильтр: берём окна из условия и смотрим, есть ли хоть одно
    # дословно в решении. Так отсекаются ответы, которые лишь пересказывают
    # вопрос теми же терминами.
    windows = [
        condition[i:i + 80]
        for i in range(0, max(0, min(len(condition) - 80, 320)) + 1, 80)
    ]
    if not any(window in solution for window in windows):
        return False
    import difflib
    matcher = difflib.SequenceMatcher(None, condition, solution, autojunk=False)
    if matcher.ratio() >= 0.85:
        return True
    longest = matcher.find_longest_match(0, len(condition), 0, len(solution))
    return longest.size >= 120 and longest.size / len(condition) >= 0.5


def fake_solution_reason(task: dict[str, Any]) -> str | None:
    solution = clean_text(task.get("solution"))
    if not solution:
        return None
    normalized = normalize_text(solution)
    if PLACEHOLDER_RE.match(solution):
        return "заглушка «решение на изображении»"
    if EMPTY_ACTION_RE.match(solution):
        return "пустой шаг «Выполните действие»"
    if solution_copies_condition(task):
        return "решение повторяет условие"
    if len(solution) < 12 and len(clean_text(task.get("condition"))) > 50:
        return "решение короче 12 символов"
    return None


def answer_unrelated_reason(task: dict[str, Any]) -> str | None:
    answer = clean_text(task.get("answer"))
    condition = clean_text(task.get("condition"))
    solution = clean_text(task.get("solution"))
    if not answer or not condition:
        return None
    if len(answer) < 30:
        return None
    cyrillic_words = re.findall(r"[а-яё]{3,}", answer.lower())
    if len(cyrillic_words) < 5:
        return None
    if re.match(r"^\d{1,3}\.\s", answer) and "синтаксическ" in answer.lower() \
            and "синтаксическ" not in condition.lower():
        return "ответ про синтаксис из другого задания"
    overlap = token_overlap(answer, condition + " " + solution)
    if overlap == 0:
        return "ответ не пересекается с условием и решением"
    return None


def section_anomalies(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    labels: list[str] = []
    for task in tasks:
        section = clean_text(task.get("section"))
        if section and (not labels or labels[-1] != section):
            labels.append(section)

    repeats = [
        label for label, count in Counter(labels).items()
        if count > 1
    ]
    numeric: list[tuple[int, str]] = []
    for label in labels:
        match = SECTION_NUM_RE.match(label)
        if match:
            numeric.append((int(match.group(1)), label))
    out_of_order = []
    for previous, current in zip(numeric, numeric[1:]):
        if current[0] < previous[0]:
            out_of_order.append((previous[1], current[1]))

    suspicious = [
        label for label in labels
        if len(label) > 90
        or label.rstrip().endswith("?")
        or SECTION_QUESTION_RE.match(label)
        or TASK_VERB_RE.match(label)
        or re.match(r"^\d{1,3}\.\s+[А-ЯЁ][а-яё]+\s+[а-яё]+\s+[а-яё]+", label)
    ]
    # все задания одного файла с пустым section — это не аномалия
    return {
        "labels": labels,
        "repeats": repeats,
        "out_of_order": out_of_order,
        "suspicious": suspicious,
        "broken": bool(repeats or out_of_order or suspicious),
    }


def number_mismatch(task: dict[str, Any]) -> bool:
    """Консервативная проверка: целый номер задачи против начала условия."""
    task_no = norm_number(task.get("number"))
    if not re.fullmatch(r"\d{1,4}", task_no):
        return False
    match = LEADING_NUM_RE.match(clean_text(task.get("condition")))
    if not match:
        return False
    return int(match.group(1)) != int(task_no)


def iter_catalog_books(catalog: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for grade in catalog.get("grades", []):
        for subject in grade.get("subjects", []):
            for book in subject.get("textbooks", []):
                yield {
                    "grade": str(grade.get("id", "")),
                    "grade_title": str(grade.get("title", "")),
                    "subject": str(subject.get("id", "")),
                    "subject_title": str(subject.get("title", "")),
                    "id": str(book.get("id", "")),
                    "title": str(book.get("title", "")),
                    "author": str(book.get("author", "")),
                    "year": str(book.get("year", "")),
                    "file": str(book.get("file", "")),
                }


def first_author(value: str) -> str:
    token = re.split(r"[\s,.;:]+", value.strip().lower())
    return token[0] if token else ""


def audit_book(meta: dict[str, Any]) -> dict[str, Any]:
    path = DATA / meta["file"]
    row: dict[str, Any] = {
        **meta,
        "exists": path.exists(),
        "tasks": 0,
        "broken": [],
        "empty": [],
        "short": [],
        "mismatch": [],
        "placeholder": [],
        "fake_solutions": [],
        "bad_answers": [],
        "sections": {"labels": [], "repeats": [], "out_of_order": [], "suspicious": [], "broken": False},
        "with_images": 0,
        "with_solution": 0,
        "quality_issues": 0,
    }
    if not path.exists():
        return row

    try:
        doc = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        row["load_error"] = str(exc)
        return row

    tasks = doc.get("tasks") if isinstance(doc, dict) else None
    if not isinstance(tasks, list):
        row["load_error"] = "нет массива tasks"
        return row

    row["tasks"] = len(tasks)
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            row["broken"].append({"index": index, "number": "", "reason": "задание не объект"})
            continue
        number = norm_number(task.get("number"))
        condition = clean_text(task.get("condition"))
        solution = clean_text(task.get("solution"))
        answer = clean_text(task.get("answer"))
        images = task.get("images") if isinstance(task.get("images"), list) else []

        if images:
            row["with_images"] += 1
        if solution:
            row["with_solution"] += 1

        text = "\n".join((condition, solution, answer, clean_text(task.get("column_solution"))))
        if BROKEN_RE.search(text):
            row["broken"].append({"index": index, "number": number, "reason": "битые символы"})
        if not has_content(task):
            row["empty"].append({"index": index, "number": number})
        if len(condition) < 10 and not images:
            row["short"].append({"index": index, "number": number, "condition": condition[:80]})
        if number_mismatch(task):
            row["mismatch"].append({
                "index": index,
                "number": number,
                "condition": condition[:120],
            })
        if look_like_placeholder(task):
            row["placeholder"].append({"index": index, "number": number})
        fake_reason = fake_solution_reason(task)
        if fake_reason:
            row["fake_solutions"].append({
                "index": index,
                "number": number,
                "reason": fake_reason,
                "solution": solution[:160],
            })
        bad_reason = answer_unrelated_reason(task)
        if bad_reason:
            row["bad_answers"].append({
                "index": index,
                "number": number,
                "reason": bad_reason,
                "answer": answer[:160],
            })

    row["sections"] = section_anomalies(tasks)
    row["quality_issues"] = (
        len(row["broken"]) + len(row["empty"]) + len(row["mismatch"])
        + len(row["placeholder"]) + len(row["fake_solutions"]) + len(row["bad_answers"])
    )
    return row


def find_duplicate_image_books(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Книга-дубль: почти целиком «решение на изображении» при наличии
    нормальной текстовой книги того же класса, предмета и автора."""
    duplicates: list[dict[str, Any]] = []
    for row in rows:
        total = row["tasks"]
        if not total or not row["placeholder"]:
            continue
        placeholder_ratio = len(row["placeholder"]) / total
        image_ratio = row["with_images"] / total
        if placeholder_ratio < 0.8 or image_ratio < 0.8:
            continue
        author = first_author(row["author"])
        if not author:
            continue

        alternatives = []
        for other in rows:
            if other is row or other["subject"] != row["subject"] or other["grade"] != row["grade"]:
                continue
            if not other["tasks"] or first_author(other["author"]) != author:
                continue
            solution_ratio = other["with_solution"] / other["tasks"]
            if other["tasks"] >= 30 and solution_ratio >= 0.5 and len(other["placeholder"]) / other["tasks"] < 0.2:
                alternatives.append(other)

        if alternatives:
            best = max(alternatives, key=lambda item: item["tasks"])
            # Автоматически убираем только очевидный дубль: у книги-картинки
            # нет пометки года/части в заголовке, а нормальная книга — это
            # часть того же года. Остальные издания (другие годы) оставляем:
            # это не мусор, а другой учебник.
            image_title = row["title"].lower()
            best_title = best["title"].lower()
            year_overlap = bool(set(re.findall(r"20\d{2}", row["year"])) &
                                set(re.findall(r"20\d{2}", best["year"])))
            auto_delete = (
                "(" not in image_title
                and "часть" in best_title
                and year_overlap
                and first_author(best["author"]) == author
            )
            duplicates.append({
                "file": row["file"],
                "id": row["id"],
                "title": row["title"],
                "author": row["author"],
                "tasks": total,
                "placeholder": len(row["placeholder"]),
                "replace_with": best["file"],
                "replace_tasks": best["tasks"],
                "auto_delete": auto_delete,
            })
    return duplicates


def remove_task_indexes(tasks: list[Any], indexes: set[int]) -> list[Any]:
    return [task for index, task in enumerate(tasks) if index not in indexes]


def quarantine_file(path: Path) -> str:
    """Переносит файл в карантин, сохраняя относительный путь."""
    try:
        relative = path.relative_to(DATA)
    except ValueError:
        relative = Path(path.name)
    target = QUARANTINE / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target = target.with_name(target.stem + "-" + datetime.now().strftime("%H%M%S") + target.suffix)
    shutil.move(str(path), str(target))
    return str(target.relative_to(ROOT))


def build_report(
    rows: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
    removed: dict[str, Any],
) -> str:
    total_tasks = sum(row["tasks"] for row in rows)
    total_books = sum(1 for row in rows if row["tasks"])
    broken = sum(len(row["broken"]) for row in rows)
    empty = sum(len(row["empty"]) for row in rows)
    short = sum(len(row["short"]) for row in rows)
    mismatch = sum(len(row["mismatch"]) for row in rows)
    placeholder = sum(len(row["placeholder"]) for row in rows)
    fake_solutions = sum(len(row["fake_solutions"]) for row in rows)
    bad_answers = sum(len(row["bad_answers"]) for row in rows)
    broken_sections = [row for row in rows if row["sections"]["broken"]]
    missing = [row for row in rows if not row["exists"]]
    load_errors = [row for row in rows if row.get("load_error")]

    worst = sorted(
        (row for row in rows if row["tasks"]),
        key=lambda row: (
            (row["quality_issues"] + len(row["short"]) * 0.2) / max(row["tasks"], 1),
            row["quality_issues"],
        ),
        reverse=True,
    )[:15]

    lines = [
        "# Аудит данных ГДЗ НЭЛ",
        "",
        f"Сформирован: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.",
        "Скрипт: `scripts/audit_data.py`.",
        "",
        "## Сводка",
        "",
        f"- учебников в каталоге: **{len(rows)}** (с заданиями: {total_books});",
        f"- заданий проверено: **{total_tasks:,}**;".replace(",", " "),
        f"- битые символы (`U+FFFD`, управляющие, кракозябры): **{broken}**;",
        f"- полностью пустые задания: **{empty}**;",
        f"- условия короче 10 символов: **{short}** (не всё мусор — бывают «Сравни.» с решением);",
        f"- несовпадение номера и начала условия: **{mismatch}**;",
        f"- задания-заглушки «решение на изображении»: **{placeholder}**;",
        f"- фейковые решения (повтор условия, «выполните действие», пустой текст): **{fake_solutions}**;",
        f"- ответы без связи с условием (эвристика, ручная проверка): **{bad_answers}**;",
        f"- сломанных сеток разделов: **{len(broken_sections)}** книг;",
        f"- отсутствующие файлы: **{len(missing)}**;",
        f"- ошибки чтения JSON: **{len(load_errors)}**.",
        "",
    ]

    if removed.get("books") or removed.get("tasks"):
        lines += [
            "## Что удалено",
            "",
        ]
        for item in removed.get("books", []):
            lines.append(
                f"- книга `{item['file']}` — дубль «{item['title']}» ({item['author']}), "
                f"{item['tasks']} заданий-картинок; вместо неё остаётся `{item['replace_with']}`."
            )
        if removed.get("tasks"):
            lines.append(f"- точечно удалено заданий: **{removed['tasks']}** (битые/пустые).")
        if removed.get("fake_solutions"):
            lines.append(f"- очищено фейковых решений: **{removed['fake_solutions']}**; связанные ответы удалены.")
        if removed.get("fake_answers"):
            lines.append(f"- очищено ответов от ранее удалённых фейковых решений: **{removed['fake_answers']}**.")
        if removed.get("bad_answers"):
            lines.append(f"- очищено ответов не по заданию: **{removed['bad_answers']}** (решение сохранено).")
        if removed.get("sections"):
            lines.append(
                f"- очищены сломанные сетки разделов: **{removed['sections']}** книг; "
                "задания снова сортируются по номеру, без чужих заголовков."
            )
        lines += ["", "Резервные копии: `app/data/_audit_quarantine/` (не публикуется).", ""]

    lines += [
        "## Дубли книг-картинок",
        "",
    ]
    if duplicates:
        lines += [
            "| файл | автор | заданий | заглушек | оставлена книга | действие |",
            "|---|---|---:|---:|---|---|",
        ]
        for item in duplicates:
            lines.append(
                f"| `{item['file']}` | {item['author']} | {item['tasks']} | {item['placeholder']} | "
                f"`{item['replace_with']}` ({item['replace_tasks']}) | "
                f"{'удалена' if item.get('auto_delete') else 'ручная проверка'} |"
            )
    else:
        lines.append("Дублей не найдено.")
    lines.append("")

    lines += [
        "## Фейковые решения",
        "",
    ]
    fake_rows = [row for row in rows if row["fake_solutions"]]
    if fake_rows:
        lines += [
            "| книга | класс | предмет | заданий | фейковых решений | примеры |",
            "|---|---:|---|---:|---:|---|",
        ]
        for row in sorted(fake_rows, key=lambda item: len(item["fake_solutions"]), reverse=True):
            examples = "; ".join(
                f"№{item['number']}: {item['reason']}"
                for item in row["fake_solutions"][:2]
            )
            lines.append(
                f"| `{row['file']}` | {row['grade']} | {row['subject_title']} | {row['tasks']} | "
                f"{len(row['fake_solutions'])} | {examples} |"
            )
        lines += [
            "",
            "Критерии: решение совпадает с условием или пересекается по содержательным "
            "словам на 80 % и более; текст «Решение на изображении» / «Выполните действие:» "
            "без действия; решение короче 12 символов при длинном условии.",
            "",
        ]
    else:
        lines += ["Не найдено.", ""]

    lines += [
        "## Ответы не по заданию",
        "",
    ]
    bad_rows = [row for row in rows if row["bad_answers"]]
    if bad_rows:
        lines += [
            "| книга | класс | предмет | заданий | подозрительных ответов | примеры |",
            "|---|---:|---|---:|---:|---|",
        ]
        for row in sorted(bad_rows, key=lambda item: len(item["bad_answers"]), reverse=True):
            examples = "; ".join(
                f"№{item['number']}: {item['reason']}"
                for item in row["bad_answers"][:2]
            )
            lines.append(
                f"| `{row['file']}` | {row['grade']} | {row['subject_title']} | {row['tasks']} | "
                f"{len(row['bad_answers'])} | {examples} |"
            )
        lines += [
            "",
            "Эвристика: ответ не имеет общих содержательных слов с условием и решением, "
            "либо начинается с нумерованного фрагмента про синтаксис, которого нет в условии. "
            "Это сигнал для ручной проверки, а не автоматический приговор.",
            "",
        ]
    else:
        lines += ["Не найдено.", ""]

    lines += [
        "## Сломанные сетки разделов",
        "",
    ]
    if broken_sections:
        lines += [
            "| книга | класс | предмет | разделов | повторы | порядок | подозрительные | примеры |",
            "|---|---:|---|---:|---:|---:|---|---|",
        ]
        for row in sorted(broken_sections, key=lambda item: len(item["sections"]["labels"]), reverse=True):
            info = row["sections"]
            examples = "; ".join(
                f"«{item[:70]}»" for item in (info["suspicious"] or info["repeats"])[:2]
            )
            lines.append(
                f"| `{row['file']}` | {row['grade']} | {row['subject_title']} | "
                f"{len(info['labels'])} | {len(info['repeats'])} | "
                f"{len(info['out_of_order'])} | {len(info['suspicious'])} | {examples} |"
            )
        lines += [
            "",
            "Сломанная сетка: одинаковый раздел встречается несколькими блоками, "
            "номера разделов идут назад или название раздела похоже на условие задания. "
            "Для книг gdz-raketa разделы очищаются до «Все задания»: источник не отдаёт "
            "оглавление на страницах заданий, поэтому лучше честная сортировка по номеру, "
            "чем чужие заголовки.",
            "",
        ]
    else:
        lines += ["Не найдено.", ""]

    lines += [
        "## Худшие книги по доле замечаний",
        "",
        "| книга | заданий | битые | пустые | короткие | номер | заглушки |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in worst:
        lines.append(
            f"| `{row['file']}` | {row['tasks']} | {len(row['broken'])} | {len(row['empty'])} | "
            f"{len(row['short'])} | {len(row['mismatch'])} | {len(row['placeholder'])} |"
        )
    lines.append("")

    mismatch_rows = [row for row in rows if row["mismatch"]]
    if mismatch_rows:
        lines += [
            "## Примеры несовпадения номера",
            "",
        ]
        for row in mismatch_rows[:8]:
            for item in row["mismatch"][:2]:
                lines.append(
                    f"- `{row['file']}` №{item['number']}: условие начинается с "
                    f"«{item['condition'][:90]}»"
                )
        lines.append("")

    if missing or load_errors:
        lines += ["## Ошибки целостности", ""]
        for row in missing:
            lines.append(f"- нет файла `{row['file']}`")
        for row in load_errors:
            lines.append(f"- `{row['file']}`: {row['load_error']}")
        lines.append("")

    lines += [
        "## Методика",
        "",
        "- битые символы: `U+FFFD`, управляющие байты, типичные пары cp1251→utf-8 (`Ð…`, `Ñ…`);",
        "- пустое задание: нет условия, решения, ответа, столбика и картинок;",
        "- короткое условие: меньше 10 символов без картинки; это сигнал, а не приговор;",
        "- номер: сравнивается только целый номер и число в начале условия (`12. …`), "
        "десятичные подпункты не трогаются;",
        "- заглушка: условие «Решение на изображении», нет текста, но есть картинки;",
        "- фейковое решение: повтор условия (80 % содержательных слов), пустой шаблон, "
        "«Решение на изображении» или слишком короткий текст;",
        "- ответ не по заданию: нет пересечения содержательных слов с условием/решением; "
        "служебные пометки вроде «Ответы могут отличаться» не считаются;",
        "- сломанная сетка: повтор/обратный порядок нумерованных разделов, заголовок "
        "в форме вопроса или инструкции;",
        "- дубль: >80 % заглушек и есть текстовая книга того же класса/предмета/автора.",
        "",
        "Автоматически удаляются только битые и полностью пустые задания, а также "
        "дубли целых книг-картинок. Короткие и спорные условия остаются: их нельзя "
        "безопасно удалять без ручной проверки.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Аудит учебников ГДЗ НЭЛ")
    parser.add_argument("--apply", action="store_true", help="удалить битые задания и дубли книг")
    parser.add_argument("--json", action="store_true", help="записать машинный отчёт docs/data-audit.json")
    args = parser.parse_args()

    catalog = load_json(CATALOG)
    books = list(iter_catalog_books(catalog))
    rows = [audit_book(book) for book in books]
    duplicates = find_duplicate_image_books(rows)
    removed: dict[str, Any] = {
        "books": [], "tasks": 0, "fake_solutions": 0,
        "fake_answers": 0, "bad_answers": 0, "sections": 0,
    }

    if args.apply:
        duplicate_files = {item["file"] for item in duplicates if item.get("auto_delete")}
        for item in duplicates:
            if not item.get("auto_delete"):
                continue
            path = DATA / item["file"]
            if path.exists():
                item["quarantined_to"] = quarantine_file(path)
        if duplicate_files:
            for grade in catalog.get("grades", []):
                for subject in grade.get("subjects", []):
                    subject["textbooks"] = [
                        book for book in subject.get("textbooks", [])
                        if str(book.get("file", "")) not in duplicate_files
                    ]
            dump_json(CATALOG, catalog)
            removed["books"] = [item for item in duplicates if item.get("auto_delete")]

        # Точечная чистка: битые, пустые задания, фейковые решения и разделы.
        for row in rows:
            if row["file"] in duplicate_files:
                continue
            needs_tasks = bool(
                row["broken"] or row["empty"] or row["fake_solutions"] or row["bad_answers"]
            )
            needs_sections = row["sections"]["broken"]
            if not needs_tasks and not needs_sections:
                continue
            path = DATA / row["file"]
            if not path.exists():
                continue
            doc = load_json(path)
            tasks = doc.get("tasks")
            if not isinstance(tasks, list):
                continue
            backups = QUARANTINE / "tasks" / row["file"]
            backups.parent.mkdir(parents=True, exist_ok=True)
            dump_json(backups, doc)

            indexes = {item["index"] for item in row["broken"]}
            indexes.update(item["index"] for item in row["empty"])
            bad_answer_indexes = {item["index"] for item in row["bad_answers"]}
            fake_solution_indexes = {
                item["index"] for item in row["fake_solutions"]
                if "изображении" not in item["reason"]
            }
            if needs_sections:
                removed["sections"] += 1
                for task in tasks:
                    task["section"] = ""
            for index, task in enumerate(tasks):
                if index in indexes:
                    continue
                if index in fake_solution_indexes:
                    if task.get("solution"):
                        task["solution"] = ""
                        removed["fake_solutions"] += 1
                    if task.get("answer"):
                        task["answer"] = ""
                        removed["fake_answers"] += 1
                elif index in bad_answer_indexes and task.get("answer"):
                    task["answer"] = ""
                    removed["bad_answers"] += 1
            if indexes:
                tasks = remove_task_indexes(tasks, indexes)
                doc["tasks"] = tasks
                removed["tasks"] += len(indexes)
            dump_json(path, doc)

    # после --apply пересчитываем сводку по актуальным файлам
    if args.apply:
        catalog = load_json(CATALOG)
        rows = [audit_book(book) for book in iter_catalog_books(catalog)]
        duplicates = find_duplicate_image_books(rows)

    report = build_report(rows, duplicates, removed)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "books": len(rows),
        "tasks": sum(row["tasks"] for row in rows),
        "broken_chars": sum(len(row["broken"]) for row in rows),
        "empty_tasks": sum(len(row["empty"]) for row in rows),
        "short_conditions": sum(len(row["short"]) for row in rows),
        "number_mismatch": sum(len(row["mismatch"]) for row in rows),
        "placeholders": sum(len(row["placeholder"]) for row in rows),
        "fake_solutions": sum(len(row["fake_solutions"]) for row in rows),
        "bad_answers": sum(len(row["bad_answers"]) for row in rows),
        "broken_sections": sum(1 for row in rows if row["sections"]["broken"]),
        "duplicates": duplicates,
        "removed": removed,
        "missing_files": [row["file"] for row in rows if not row["exists"]],
        "load_errors": [{"file": row["file"], "error": row["load_error"]} for row in rows if row.get("load_error")],
    }
    if args.json:
        REPORT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        key: summary[key]
        for key in ("books", "tasks", "broken_chars", "empty_tasks", "short_conditions",
                    "number_mismatch", "placeholders", "fake_solutions", "bad_answers",
                    "broken_sections", "missing_files", "load_errors")
    }, ensure_ascii=False, indent=2))
    if removed["books"]:
        print("удалены книги:", ", ".join(item["file"] for item in removed["books"]))
    if removed["tasks"]:
        print("удалено заданий:", removed["tasks"])
    print("отчёт:", REPORT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
