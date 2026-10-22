#!/usr/bin/env python3
"""Собирает книги с otvet.plus, где решения лежат картинками.

Сейчас это физика 10–11 Мякишева: на странице книги есть готовая структура
`div.task__list` с заголовком параграфа и ссылками на PNG. Скрипт делает по
одной задаче на изображение, чтобы предметы 10–11 классов были заполнены
даже там, где euroki/gdz-raketa отдают только сканы.

Запуск:
    uv run --with beautifulsoup4 scripts/parse_otvet_images.py
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
MANIFEST = DATA / "_otvet_manifest.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

BOOKS = [
    {
        "id": "myakishev-10",
        "grade": 10,
        "subject": "physics",
        "url": "https://otvet.plus/10-klass/fizika/myakishev/",
        "title": "Мякишев. Физика 10",
    },
    {
        "id": "myakishev-11",
        "grade": 11,
        "subject": "physics",
        "url": "https://otvet.plus/11-klass/fizika/myakishev/",
        "title": "Мякишев. Физика 11",
    },
    {
        "id": "rudzitis-11",
        "grade": 11,
        "subject": "chemistry",
        "url": "https://otvet.plus/11-klass/himija/rudzitis/",
        "title": "Рудзитис. Химия 11",
    },
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read().decode("utf-8", "replace")


def meta(soup: BeautifulSoup) -> tuple[str, str]:
    author = ""
    year = ""
    node = soup.select_one(".books__desc__author")
    if node:
        author = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
    node = soup.select_one(".books__desc__izd")
    if node:
        text = node.get_text(" ", strip=True)
        m = re.search(r"(19|20)\d{2}", text)
        if m:
            year = m.group(0)
    return author, year


def clean_label(text: str) -> str:
    return re.sub(r"[;,.\s]+$", "", text.strip()) or "1"


def parse_book(book: dict) -> tuple[dict, dict] | None:
    html = fetch(book["url"])
    soup = BeautifulSoup(html, "html.parser")
    author, year = meta(soup)
    tasks: list[dict] = []
    seen: dict[str, int] = {}
    for block in soup.select("div.task__list"):
        section_node = block.select_one("div.t")
        section = re.sub(r"\s+", " ", section_node.get_text(" ", strip=True)) if section_node else ""
        section = re.sub(r"\s*\(стр\..*?\)\s*$", "", section).strip() or "Задания"
        para_match = re.search(r"§\s*(\d+)", section)
        para = para_match.group(1) if para_match else ""
        for a in block.select("a[href]"):
            href = a.get("href", "")
            if not re.search(r"\.(?:png|jpe?g|webp)(?:\?|$)", href, re.I):
                continue
            label = clean_label(a.get_text(" ", strip=True))
            base = f"{para}.{label}" if para else label
            seen[base] = seen.get(base, 0) + 1
            number = base if seen[base] == 1 else f"{base}-{seen[base]}"
            image = urllib.parse.urljoin(book["url"], href)
            tasks.append({
                "number": number,
                "section": section,
                "condition": f"Задание {label}. Решение на изображении.",
                "solution": "Решение на изображении.",
                "answer": "См. изображение.",
                "images": [image],
                "source": "otvet.plus",
                "sourceUrl": book["url"],
            })
    if not tasks:
        print(f"!! {book['id']}: заданий нет", flush=True)
        return None
    doc = {
        "subject": book["subject"],
        "textbook": book["id"],
        "author": author or "Мякишев Г.Я. и др.",
        "year": year or "2018",
        "source": "parsed",
        "sourceUrl": book["url"],
        "parsedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tasks": tasks,
    }
    entry = {
        "grade": book["grade"],
        "subject": book["subject"],
        "id": book["id"],
        "file": f"{book['subject']}/{book['id']}.json",
        "title": book["title"],
        "author": doc["author"],
        "year": doc["year"],
        "tasks": len(tasks),
        "source": "otvet.plus",
        "sourceUrl": book["url"],
    }
    return doc, entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    known: dict[str, dict] = {}
    if MANIFEST.exists():
        try:
            known = {e["id"]: e for e in json.loads(MANIFEST.read_text(encoding="utf-8"))}
        except (OSError, json.JSONDecodeError):
            known = {}
    for i, book in enumerate(BOOKS, 1):
        print(f"[{i}/{len(BOOKS)}] {book['grade']} {book['subject']} {book['id']}", flush=True)
        try:
            result = parse_book(book)
        except Exception as exc:  # noqa: BLE001
            print(f"!! {book['id']}: {exc}", flush=True)
            continue
        if not result:
            continue
        doc, entry = result
        print(f"   задач: {len(doc['tasks'])}", flush=True)
        if not args.dry:
            path = DATA / entry["file"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            known[entry["id"]] = entry
            print(f"   записано: {path}", flush=True)
        time.sleep(1)
    if not args.dry:
        MANIFEST.write_text(
            json.dumps(sorted(known.values(), key=lambda e: (e["grade"], e["subject"], e["id"])),
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"манифест: {MANIFEST} — {len(known)} книг", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
