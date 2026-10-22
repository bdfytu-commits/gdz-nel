#!/usr/bin/env python3
"""Литература 10–11 классов с gdz.ru: решения лежат изображениями.

На странице книги gdz.ru перечислены ссылки `.../N-prt-M/`, а на странице
задания — `figure.task-container` с картинками решения. Скрипт собирает
по одной задаче на страницу, чтобы закрыть литературу 10–11, которой нет
в euroki и gdz-raketa.

Запуск:
    uv run --with beautifulsoup4 scripts/parse_gdzru_images.py --dry --limit 1
    uv run --with beautifulsoup4 scripts/parse_gdzru_images.py
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
MANIFEST = DATA / "_gdzru_manifest.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

BOOKS = [
    ("10", "literature", "lebedev", "Лебедев. Литература 10"),
    ("10", "literature", "zinin", "Зинин, Сахаров. Литература 10"),
    ("10", "literature", "korovin-uglublennyj-uroven", "Коровин. Литература 10 (углублённый)"),
    ("10", "literature", "kurdyumova", "Курдюмова. Литература 10"),
    ("11", "literature", "mihajlov-2-chastyah-bazovyj-uroven", "Михайлов, Шайтанов. Литература 11"),
    ("11", "literature", "zinin", "Зинин, Чалмаев. Литература 11"),
    ("11", "literature", "korovin-uglublennyj-uroven", "Коровин. Литература 11 (углублённый)"),
    ("11", "literature", "kurdyumova", "Курдюмова. Литература 11"),
    ("11", "physics", "rymkevich", "Рымкевич. Физика 10–11, задачник"),
    ("11", "history", "zagladin", "Загладин, Петров. История 11"),
    ("11", "english", "reshebnik-enjoy-english-biboletova-2014", "Биболетова. Enjoy English 11"),
    ("2", "russian", "aleksandrova", "Александрова. Русский язык 2"),
    ("2", "english", "spotlight-bikova", "Быкова, Дули. Spotlight 2"),
    ("2", "english", "rainbow-afanasjeva", "Афанасьева, Михеева. Rainbow English 2"),
    ("2", "english", "starlight-baranova", "Баранова, Дули. Starlight 2"),
    ("2", "english", "brilliant-komarova", "Комарова, Ларионова. Brilliant 2"),
    ("2", "english", "enjoy-english-biboletova-m-z-2012", "Биболетова. Enjoy English 2"),
]


def fetch(url: str, retries: int = 2) -> str:
    last: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru"})
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt >= retries:
                break
            time.sleep(5 * (attempt + 1))
    raise last  # type: ignore[misc]


def book_meta(soup: BeautifulSoup) -> tuple[str, str]:
    author = ""
    year = ""
    for p in soup.select(".book__description p"):
        text = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
        m = re.search(r"Авторы?:\s*(.+)", text)
        if m:
            author = m.group(1).strip()
        m = re.search(r"Год:\s*(.+)", text)
        if m:
            year = m.group(1).strip()
    if not author:
        node = soup.select_one("meta[name=description]")
        if node:
            m = re.search(r"авторов?\s+([^,.]+)", node.get("content", ""), re.I)
            if m:
                author = m.group(1).strip()
    return author, year


def task_links(soup: BeautifulSoup, base: str) -> list[str]:
    out: list[str] = []
    for a in soup.select("a.task__button[href]"):
        href = urllib.parse.urljoin(base, a["href"])
        if href not in out:
            out.append(href)
    return out


def task_images(soup: BeautifulSoup, base: str) -> list[str]:
    out: list[str] = []
    for card in soup.select("figure.task-container .solution-card"):
        for img in card.select("div.task-img-container img[src]"):
            src = urllib.parse.urljoin(base, img["src"])
            if src not in out:
                out.append(src)
    return out


SUBJECT_PATH = {"literature": "literatura", "physics": "fizika", "history": "istoriya", "english": "english", "russian": "russkii_yazik"}


def task_number(link: str, fallback: int) -> str:
    m = re.search(r"/(\d+)-nom/?$", link)
    if m:
        return m.group(1)
    m = re.search(r"/(\d+)-item-(\d+)/?$", link)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    m = re.search(r"/(\d+)-prt-(\d+)/?$", link)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    return str(fallback)


def parse_book(grade: str, subject: str, slug: str, title: str, limit: int | None, dry: bool) -> tuple[dict, dict] | None:
    url = f"https://gdz.ru/class-{grade}/{SUBJECT_PATH.get(subject, subject)}/{slug}/"
    soup = BeautifulSoup(fetch(url), "html.parser")
    author, year = book_meta(soup)
    links = task_links(soup, url)
    if limit:
        links = links[:limit]
    if not links:
        print(f"!! {slug}: ссылок на задания нет", flush=True)
        return None
    print(f"   страниц: {len(links)}", flush=True)
    tasks: list[dict] = []
    for i, link in enumerate(links, 1):
        try:
            page = BeautifulSoup(fetch(link), "html.parser")
        except Exception as exc:  # noqa: BLE001
            print(f"   !! {link}: {exc}", flush=True)
            continue
        images = task_images(page, link)
        if not images:
            continue
        number = task_number(link, i)
        section = f"Задание {number}"
        tasks.append({
            "number": number,
            "section": section,
            "condition": f"Задание {number}. Решение на изображении.",
            "solution": "Решение на изображении.",
            "answer": "См. изображение.",
            "images": images,
            "source": "gdz.ru",
            "sourceUrl": link,
        })
        if i % 25 == 0:
            print(f"   ... {i}/{len(links)}", flush=True)
        time.sleep(1)
    if not tasks:
        print(f"!! {slug}: решений-картинок нет", flush=True)
        return None
    doc = {
        "subject": subject,
        "textbook": f"{slug}-{grade}",
        "author": author or "—",
        "year": year or "2024",
        "source": "parsed",
        "sourceUrl": url,
        "parsedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tasks": tasks,
    }
    entry = {
        "grade": int(grade),
        "subject": subject,
        "id": f"{slug}-{grade}",
        "file": f"{subject}/{slug}-{grade}.json",
        "title": title,
        "author": doc["author"],
        "year": doc["year"],
        "tasks": len(tasks),
        "source": "gdz.ru",
        "sourceUrl": url,
    }
    return doc, entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="страниц на книгу, для проверки")
    ap.add_argument("--only", default="")
    ap.add_argument("--slugs", default="", help="список slug через запятую")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    known: dict[str, dict] = {}
    if MANIFEST.exists():
        try:
            known = {e["id"]: e for e in json.loads(MANIFEST.read_text(encoding="utf-8"))}
        except (OSError, json.JSONDecodeError):
            known = {}
    wanted = {x.strip() for x in args.slugs.split(",") if x.strip()}
    books = [b for b in BOOKS if not args.only or args.only in b[2]]
    if wanted:
        books = [b for b in books if b[2] in wanted]
    for i, (grade, subject, slug, title) in enumerate(books, 1):
        print(f"\n[{i}/{len(books)}] {grade} {subject} {slug}", flush=True)
        try:
            result = parse_book(grade, subject, slug, title, args.limit, args.dry)
        except Exception as exc:  # noqa: BLE001
            print(f"!! книга упала: {exc}", flush=True)
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
    if not args.dry:
        MANIFEST.write_text(
            json.dumps(sorted(known.values(), key=lambda e: (e["grade"], e["subject"], e["id"])),
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"\nманифест: {MANIFEST} — {len(known)} книг", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
