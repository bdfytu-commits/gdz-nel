#!/usr/bin/env python3
"""Собирает инвентарь учебников euroki.org для указанных классов.

Ходит по страницам предметов, оставляет только «Тип: учебник», дописывает
новые записи в scripts/euroki_books.json без дублей. Нужен для классов,
которых не было в первоначальной ручной выборке (например, 5-го).

    uv run --with beautifulsoup4 scripts/discover_euroki.py --grades 5
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "scripts" / "euroki_books.json"
BASE = "https://www.euroki.org/gdz/ru"
SUBJECTS = (
    "matematika", "russkiy", "angliyskiy", "biologiya", "geografiya",
    "istoriya", "literatura", "obshestvoznanie", "fizika", "himiya",
    "algebra", "geometriya", "informatika",
)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def fetch(url: str) -> str | None:
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                wait = 60
            elif exc.code >= 500:
                wait = 10
            else:
                return None
            print(f"  !! {url}: HTTP {exc.code}, пауза {wait} с", flush=True)
            time.sleep(wait)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! {url}: {exc}", flush=True)
            time.sleep(5)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grades", default="5")
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    grades = [int(x) for x in args.grades.split(",") if x.strip()]

    existing: list[dict] = []
    if INVENTORY.exists():
        existing = json.loads(INVENTORY.read_text(encoding="utf-8"))
    seen = {(e["grade"], e["url"]) for e in existing}
    found: list[dict] = []

    for grade in grades:
        for subject in SUBJECTS:
            url = f"{BASE}/{subject}/{grade}_klass"
            html = fetch(url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            count = 0
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not re.search(rf"/gdz/ru/{re.escape(subject)}/{grade}_klass/[^/?#]+$", href):
                    continue
                if href.startswith("/"):
                    href = "https://www.euroki.org" + href
                text = " ".join(a.get_text(" ", strip=True).split())
                if "Тип: учебник" not in text:
                    continue
                if (grade, href) in seen:
                    continue
                seen.add((grade, href))
                found.append({
                    "source_subject": subject,
                    "grade": grade,
                    "slug": href.rstrip("/").rsplit("/", 1)[-1],
                    "url": href,
                    "text": text,
                })
                count += 1
            print(f"{grade} {subject}: +{count}", flush=True)
            time.sleep(0.7)

    print(f"новых учебников: {len(found)}", flush=True)
    if args.dry or not found:
        return 0
    merged = existing + found
    merged.sort(key=lambda e: (e["grade"], e["source_subject"], e["slug"]))
    INVENTORY.write_text(json.dumps(merged, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"инвентарь: {INVENTORY} — {len(merged)} книг", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
