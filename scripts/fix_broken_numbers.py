#!/usr/bin/env python3
"""Пересчитывает номера задач по sourceUrl и убирает дубли.

Проблема: euroki перезапускает нумерацию внутри главы, а старый парсер
брал только последнее число из URL. В итоге в книге было много задач
с номером "1" и одинаковыми секциями.

Скрипт:
- вытаскивает главу/часть из URL и делает номера уникальными (2.1, 2.2);
- для страниц "Вопросы к параграфам" берёт номер из section/condition;
- склеивает полные дубли (одинаковый номер и раздел), объединяя картинки;
- оставляет номера страничных книг (str-N) как page.question.

По умолчанию только показывает отчёт; запись — с --apply.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
SUBJECTS = {
    "math", "russian", "english", "world", "literature", "algebra",
    "geometry", "physics", "chemistry", "biology", "history", "social",
    "geo", "informatics",
}
MATH_LIKE = {"math", "algebra", "geometry", "physics", "chemistry"}


def chapter_from_url(url: str) -> int:
    m = re.search(r"glava-(\d+)", url)
    if m:
        return int(m.group(1))
    path = url.split("?", 1)[0].rstrip("/")
    seg = path.rsplit("/", 1)[-1]
    if seg.startswith("chast-"):
        return 0
    m = re.match(r"(\d+)-", seg)
    if m and int(m.group(1)) <= 30:
        return int(m.group(1))
    return 0


def part_from_url(url: str) -> int:
    m = re.search(r"chast-(\d+)-zadanie-", url)
    return int(m.group(1)) if m else 0


def tasknum_from_url(url: str) -> str:
    m = re.search(r"(?:^|-)zadanie-(\d+)(?:-|$)", url)
    return m.group(1) if m else ""


def dotted_from_text(text: str) -> tuple[str, str] | None:
    m = re.match(r"^\s*(\d+\.\d+)\.?\s*(.*)$", text or "")
    if not m:
        return None
    return m.group(1), m.group(2).strip(" .")


def normalize_task(task: dict, subject: str) -> tuple[bool, bool]:
    """Возвращает (номер_изменён, раздел_изменён)."""
    url = str(task.get("sourceUrl") or "")
    old_num = str(task.get("number") or "")
    old_sec = str(task.get("section") or "")
    num = old_num
    sec = old_sec

    # 1. "Вопросы к параграфам": настоящий номер вида 5.1 лежит в section/condition
    if "voprosy-k-paragrafam" in url or re.search(r"zadanie-\d+-[a-z]", url):
        for source in (old_sec, str(task.get("condition") or "")):
            got = dotted_from_text(source)
            if got:
                num, rest = got
                sec = rest or old_sec
                break

    # 2. глава в URL: для точных наук номер глава.задание
    ch = chapter_from_url(url)
    n = tasknum_from_url(url)
    if n and "voprosy-k-paragrafam" not in url:
        if ch:
            if subject in MATH_LIKE:
                num = f"{ch}.{n}"
            else:
                num = n
        elif re.match(r"^\d+\.\d+$", old_num):
            num = old_num
        else:
            num = n

    # 3. раздел: число вместо названия — это не заголовок
    if re.fullmatch(r"\d+(?:\.\d+)*", sec.strip()):
        part = part_from_url(url)
        if ch:
            sec = f"Глава {ch}"
        elif part:
            sec = f"Часть {part}"
        elif "voprosy-k-paragrafam" in url:
            sec = "Вопросы к параграфам"
        elif not url.rstrip("/").split("/")[-1].startswith("str-"):
            sec = "Задания"
    if "voprosy-k-paragrafam" in url:
        sec = "Вопросы к параграфам"
    if num != old_num or sec != old_sec:
        task["number"] = num
        task["section"] = sec[:180]
    return num != old_num, sec != old_sec


def dedupe(tasks: list[dict]) -> tuple[list[dict], int]:
    merged: dict[tuple[str, str], dict] = {}
    out: list[dict] = []
    dropped = 0
    for t in tasks:
        key = (str(t.get("number") or ""), str(t.get("section") or ""))
        if key in merged:
            keep = merged[key]
            imgs = list(dict.fromkeys((keep.get("images") or []) + (t.get("images") or [])))
            if imgs:
                keep["images"] = imgs
            if len(str(t.get("solution") or "")) > len(str(keep.get("solution") or "")):
                keep["solution"] = t.get("solution") or ""
                keep["condition"] = t.get("condition") or keep.get("condition", "")
                keep["answer"] = t.get("answer") or keep.get("answer", "")
            dropped += 1
            continue
        merged[key] = t
        out.append(t)
    return out, dropped


def uniquify(tasks: list[dict]) -> int:
    counts: dict[str, int] = defaultdict(int)
    for t in tasks:
        counts[str(t.get("number") or "")] += 1
    used: set[str] = set()
    changed = 0
    for t in tasks:
        old = str(t.get("number") or "")
        n = old
        if counts.get(n, 0) > 1 or n in used:
            ch = chapter_from_url(str(t.get("sourceUrl") or ""))
            base = f"{ch}.{n}" if ch and "." not in n else n
            cand = base
            k = 2
            while cand in used:
                cand = f"{base}-{k}"
                k += 1
            t["number"] = cand
            changed += 1
        used.add(str(t["number"]))
    return changed


def sort_key(task: dict) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(task.get("number") or ""))) or (0,)


def task_sort_key(task: dict) -> tuple:
    sec = str(task.get("section") or "")
    m = re.match(r"Глава\s+(\d+)", sec)
    if m:
        return (int(m.group(1)), 0, sec)
    m = re.match(r"Часть\s+(\d+)", sec)
    if m:
        return (int(m.group(1)) - 0.5, 0, sec)
    if sec in {"Задания", "Все задания"}:
        return (-1, 0, sec)
    m = re.match(r"(\d+)\.", str(task.get("number") or ""))
    if m:
        return (int(m.group(1)), 1, sec)
    return (500, 0, sec)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--subjects", default="")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    subjects = {x.strip() for x in args.subjects.split(",") if x.strip()}
    files = []
    for subject in SUBJECTS:
        if subjects and subject not in subjects:
            continue
        for path in sorted((DATA / subject).glob("*.json")):
            if args.only and args.only not in path.name:
                continue
            files.append(path)
    if args.limit:
        files = files[:args.limit]

    total_files = changed_files = 0
    before = after = 0
    num_changed = sec_changed = dropped_total = uniq_changed = 0
    samples: list[str] = []
    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        tasks = doc.get("tasks")
        if not isinstance(tasks, list):
            continue
        total_files += 1
        before += len(tasks)
        raw = path.read_text(encoding="utf-8")
        subject = doc.get("subject") or path.parent.name
        for t in tasks:
            a, b = normalize_task(t, subject)
            num_changed += a
            sec_changed += b
        tasks, dropped = dedupe(tasks)
        uniq_changed += uniquify(tasks)
        dropped_total += dropped
        tasks.sort(key=lambda t: (task_sort_key(t), sort_key(t)))
        after += len(tasks)
        new_doc = dict(doc)
        new_doc["tasks"] = tasks
        text = json.dumps(new_doc, ensure_ascii=False, indent=2) + "\n"
        if text != raw:
            changed_files += 1
            if len(samples) < 12:
                nums = [str(t.get("number")) for t in tasks[:8]]
                samples.append(f"{path.relative_to(DATA)}: {nums}")
            if args.apply:
                tmp = path.with_suffix(".json.part")
                tmp.write_text(text, encoding="utf-8")
                tmp.replace(path)
    print(f"файлов: {total_files}, изменено: {changed_files}")
    print(f"задач было: {before}, стало: {after}, склеено дублей: {dropped_total}")
    print(f"номеров исправлено: {num_changed}, разделов: {sec_changed}, уникализировано: {uniq_changed}")
    if samples:
        print("примеры:")
        for s in samples:
            print(" ", s)
    if not args.apply:
        print("это предпросмотр, запусти с --apply, чтобы применить")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
