#!/usr/bin/env python3
"""Добор новых классов с gdz-raketa.ru (русский 3–4, английский 3–4, химия 11, общество 11).

Скрипт сам находит учебники на странице предмета/класса, обходит оглавление,
вытаскивает задания существующими парсерами `parse_gdz` и пишет JSON в
`app/data/<subject>/<id>.json`. Книги, где текста нет (только скан), пропускаются.

Запуск из корня проекта:

    uv run --with beautifulsoup4 scripts/parse_gdz_bulk.py --dry --limit 2
    nohup uv run --with beautifulsoup4 scripts/parse_gdz_bulk.py \
        > /tmp/opencode/parse_gdz_new_grades.log 2>&1 &
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse_gdz as p  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
MANIFEST = DATA / "_gdz_manifest.json"

UA_POOL = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def translit(text: str) -> str:
    out = "".join(TRANSLIT.get(ch.lower(), ch) for ch in text)
    return re.sub(r"[^a-z0-9]+", "-", out.lower()).strip("-") or "book"


def fetch_page(url: str, retries: int = 2) -> object | None:
    for attempt in range(retries + 1):
        try:
            return p.fetch(url)
        except p.SourcesBlocked as exc:
            print(f"  !! {exc}", flush=True)
            if attempt >= retries:
                return None
            p.UA = UA_POOL[(attempt + 1) % len(UA_POOL)]
            print("  !! пауза 60 с и смена User-Agent", flush=True)
            time.sleep(60)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! {url}: {exc}", flush=True)
            if attempt >= retries:
                return None
            time.sleep(5)
    return None


def extract_meta(soup, fallback_author: str = "") -> tuple[str, str]:
    text = soup.get_text(" ", strip=True)
    author = fallback_author
    m = re.search(r"Авторы?:\s*(.+?)\s*(?:Год:|Часть:|Серия:|Издательство:|$)", text)
    if m:
        author = re.sub(r"\s+", " ", m.group(1)).strip(" .,")
    author = re.sub(r"\s+Части?:.*$", "", author).strip(" .,")
    year = ""
    m = re.search(r"Год:\s*([0-9]{4}(?:\s*[-–]\s*[0-9]{4})?)", text)
    if m:
        year = m.group(1).replace(" ", "")
    if not year:
        year = "2024"
    return author or fallback_author, year


def discover_targets() -> list[dict]:
    targets: list[dict] = []
    subjects = [
        ("english", 3, "https://gdz-raketa.ru/english/3-klass/"),
        ("english", 4, "https://gdz-raketa.ru/english/4-klass/"),
        ("russian", 3, "https://gdz-raketa.ru/russkiy-yazyk/3-klass/"),
        ("russian", 4, "https://gdz-raketa.ru/russkiy-yazyk/4-klass/"),
        ("english", 11, "https://gdz-raketa.ru/english/11-klass/"),
    ]
    skip = ("tetrad", "rabochaya", "trenazher", "azbuka", "kontrolnye", "domashnie")
    for subject, grade, url in subjects:
        soup = fetch_page(url)
        if soup is None:
            continue
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = urllib.parse.urljoin(url, a["href"]).rstrip("/") + "/"
            m = re.search(r"/uchebnik-([a-z0-9-]+)/$", href)
            if not m:
                continue
            if any(w in m.group(1) for w in skip):
                continue
            if href in seen:
                continue
            seen.add(href)
            targets.append({
                "subject": subject, "grade": grade, "index": href,
                "slug": m.group(1), "author": "", "year": "2024",
            })
    targets.append({
        "subject": "chemistry", "grade": 10,
        "index": "https://gdz-raketa.ru/himiya/10-klass/uchebnik-gabrielyan/",
        "slug": "uchebnik-gabrielyan-10", "author": "Габриелян О.С.", "year": "2023",
    })
    targets.append({
        "subject": "chemistry", "grade": 11,
        "index": "https://gdz-raketa.ru/himiya/11-klass/uchebnik-gabrielyan/",
        "slug": "uchebnik-gabrielyan", "author": "Габриелян О.С.", "year": "2022",
    })
    targets.append({
        "subject": "social", "grade": 11,
        "index": "https://gdz-raketa.ru/obshhestvoznanie/11-klass/uchebnik-bogolubov/",
        "slug": "uchebnik-bogolubov",
        "author": "Боголюбов Л.Н., Городецкая Н.И., Лазебникова А.Ю. и др.", "year": "2024",
    })
    return targets


PAGE_RX = re.compile(r"/(?:(1|2)-chast-)?(?:stranitsa|stranica)-(\d+)/$")


def book_links(index_soup, index_url: str) -> dict[int, list[tuple[int, str]]]:
    """{часть: [(страница, url), ...]}"""
    out: dict[int, list[tuple[int, str]]] = {}
    for a in index_soup.find_all("a", href=True):
        href = urllib.parse.urljoin(index_url, a["href"])
        m = PAGE_RX.search(href)
        if not m:
            continue
        part = int(m.group(1)) if m.group(1) else 0
        page = int(m.group(2))
        out.setdefault(part, [])
        if all(page != x[0] for x in out[part]):
            out[part].append((page, href))
    for part in out:
        out[part].sort(key=lambda x: x[0])
    return out


def parse_page_qa(soup, page: str) -> list[dict]:
    """Fallback: страница с вопросом и блоком «Ответ:» (общество/химия/история)."""
    lines = p._main_lines(soup)
    marks = [i for i, l in enumerate(lines) if re.match(r"^ответ\s*:?\s*$", l, re.I)]
    out: list[dict] = []
    for idx in marks:
        start = idx
        while start > 0:
            prev = lines[start - 1]
            if (p._is_stop(prev) or re.match(r"^ответ\s*:?", prev, re.I)
                    or p._is_meta(prev) or prev.startswith("§")
                    or re.match(r"^Глава\s", prev) or len(prev) > 500):
                break
            start -= 1
        cond = [l for l in lines[start:idx]
                if l and not l.startswith("§") and not re.match(r"^Глава\s", l)]
        end = idx + 1
        sol: list[str] = []
        while end < len(lines):
            line = lines[end]
            if p._is_stop(line) or re.match(r"^ответ\s*:?", line, re.I):
                break
            if line.startswith("§") or re.match(r"^Глава\s", line):
                break
            if p._is_meta(line):
                end += 1
                continue
            sol.append(line)
            end += 1
        if cond and sol:
            section = p._heading_before(lines, start, default="")
            out.append({
                "number": f"{page}.{len(out) + 1}",
                "section": section or f"Страница {page}",
                "condition": "\n".join(cond),
                "solution": "\n".join(sol),
                "answer": sol[-1],
            })
    return out


def parse_page(soup, page: str) -> list[dict]:
    for fn in (p.parse_page_tasks, p.parse_exercise_tasks, p.parse_rubric_tasks, p.parse_qa_tasks):
        try:
            tasks = fn(soup, page)
        except Exception:  # noqa: BLE001
            tasks = []
        if tasks:
            return tasks
    return parse_page_qa(soup, page)


def process_target(target: dict, force: bool, dry: bool, limit: int | None) -> list[dict]:
    index_soup = fetch_page(target["index"])
    if index_soup is None:
        return []
    links = book_links(index_soup, target["index"])
    if not links:
        print("-- ссылок на страницы нет, пропуск", flush=True)
        return []
    author, year = extract_meta(index_soup, target.get("author") or "")
    surname = re.split(r"[\s,;]+", author.strip())[0] if author.strip() else target["slug"]
    base = f"{translit(surname)}-{target['grade']}"
    multi = len(links) > 1 or (len(links) == 1 and 0 not in links)
    entries: list[dict] = []
    for part, pages in sorted(links.items()):
        suffix = f"-{part}" if multi and part > 0 else ""
        book_id = base + suffix
        out_path = DATA / target["subject"] / f"{book_id}.json"
        if out_path.exists() and not force:
            print(f"-- {book_id}: уже есть, пропуск", flush=True)
            continue
        if limit:
            pages = pages[:limit]
        print(f"== {book_id}: {len(pages)} страниц", flush=True)
        tasks: list[dict] = []
        for page_num, url in pages:
            soup = fetch_page(url)
            if soup is None:
                continue
            got = parse_page(soup, str(page_num))
            if not got:
                continue
            for task in got:
                task["source"] = "gdz-raketa.ru"
                task["sourceUrl"] = url
                task["section"] = (task.get("section") or f"Страница {page_num}").strip()
                task["condition"] = (task.get("condition") or f"Страница {page_num}.").strip()
            tasks.extend(got)
        if not tasks:
            print(f"!! {book_id}: текста нет, пропуск", flush=True)
            continue
        # уникальные номера
        seen: dict[str, int] = {}
        for task in tasks:
            n = task["number"]
            if n in seen:
                seen[n] += 1
                task["number"] = f"{n}-{seen[n]}"
            else:
                seen[n] = 1

        def sort_key(t: dict) -> tuple:
            return tuple(int(x) for x in re.findall(r"\d+", t["number"])) or (0,)

        tasks.sort(key=sort_key)
        doc = {
            "subject": target["subject"],
            "textbook": book_id,
            "author": author,
            "year": year,
            "source": "parsed",
            "sourceUrl": target["index"],
            "parsedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tasks": tasks,
        }
        if multi and part > 0:
            doc["part"] = part
        if not dry:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        title = surname + (f". Часть {part}" if multi and part > 0 else "")
        entries.append({
            "grade": target["grade"], "subject": target["subject"], "id": book_id,
            "file": f"{target['subject']}/{book_id}.json", "title": title,
            "author": author, "year": year, "tasks": len(tasks),
            "part": part if multi and part > 0 else None,
            "sourceUrl": target["index"], "source": "gdz-raketa",
        })
        print(f"   записано: {out_path} — {len(tasks)} задач", flush=True)
    return entries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--manifest", default=str(MANIFEST))
    args = ap.parse_args()
    targets = discover_targets()
    if args.only:
        targets = [t for t in targets if args.only in t["index"] or args.only in t["slug"]]
    print(f"целей: {len(targets)}", flush=True)
    manifest_path = Path(args.manifest)
    known: dict[str, dict] = {}
    if manifest_path.exists():
        try:
            for e in json.loads(manifest_path.read_text(encoding="utf-8")):
                known[e["id"]] = e
        except Exception:  # noqa: BLE001
            pass
    for i, target in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] {target['grade']} {target['subject']} {target['slug']}", flush=True)
        try:
            entries = process_target(target, args.force, args.dry, args.limit)
        except Exception as exc:  # noqa: BLE001
            print(f"!! цель упала: {exc}", flush=True)
            continue
        for e in entries:
            known[e["id"]] = e
    if not args.dry:
        manifest_path.write_text(json.dumps(sorted(known.values(), key=lambda e: (e["grade"], e["subject"], e["id"])),
                                            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\nманифест: {manifest_path} — {len(known)} книг", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
