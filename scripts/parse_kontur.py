#!/usr/bin/env python3
"""Контурные карты с gdz.ru: страницы-развороты → локальные сканы + JSON.

Каждая страница книги на gdz.ru — разворот «Страница 2–3» со сканом решённой
карты (attachments/images/tasks/...). Сканы скачиваются ЛОКАЛЬНО:

    app/data/<subject>/img/<book>/str-2-3.jpg   (jpeg, ширина ≤ 1600, q84)

в JSON задачи хранятся относительные пути «data/<subject>/img/<book>/str-2-3.jpg»,
поэтому приложение не зависит от чужого сайта.

Запуск (из корня gdz-nel):

    uv run --no-project --with beautifulsoup4 --with pillow scripts/parse_kontur.py
    uv run ... scripts/parse_kontur.py matveev-6 --force   # только одну книгу

Скрипт идемпотентный: HTML страниц кэшируется в /tmp/opencode/kontur-cache,
готовые книги по умолчанию пропускаются (--force перекачивает).
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
CACHE = Path("/tmp/opencode/kontur-cache")
UA = "Mozilla/5.0 (X11; Linux x86_64; gdz-nel data parser; +https://gdz-nel.pages.dev/)"
PAUSE = 1.1  # секунда между запросами к источнику
MAX_WIDTH = 1600
JPEG_QUALITY = 84

# география — контурные карты «Полярная звезда» (Матвеев), 6–9
# история — контурные карты Торопа (Средние века / История России), 6–9
BOOKS = [
    dict(subject="geo", id="matveev-6", grade=6,
         title="Матвеев. Контурные карты",
         author="Матвеев А.В., Петрова В.В.",
         year="2023–2026",
         url="https://gdz.ru/class-6/geografiya/konturnie-karti-matveev/"),
    dict(subject="geo", id="matveev-7", grade=7,
         title="Матвеев. Контурные карты",
         author="Матвеев А.В., Петрова В.В.",
         year="2023–2026",
         url="https://gdz.ru/class-7/geografiya/konturnie-karti-matveev/"),
    dict(subject="geo", id="matveev-8", grade=8,
         title="Матвеев. Контурные карты",
         author="Матвеев А.В., Петрова В.В.",
         year="2023–2026",
         url="https://gdz.ru/class-8/geografiya/konturnie-karti-matveev/"),
    dict(subject="geo", id="matveev-9", grade=9,
         title="Матвеев. Контурные карты",
         author="Матвеев А.В., Петрова В.В.",
         year="2023–2026",
         url="https://gdz.ru/class-9/geografiya/konturnie-karti-matveev/"),
    dict(subject="history-maps", id="torop-6", grade=6,
         title="Тороп. Контурные карты",
         author="Тороп В.В., Курбский Н.А.",
         year="2023–2026",
         url="https://gdz.ru/class-6/istoriya/konturnie-karti-srednie-veka-torop/"),
    dict(subject="history-maps", id="torop-7", grade=7,
         title="Тороп. Контурные карты",
         author="Тороп В.В., Арсентьев Н.М.",
         year="2023–2026",
         url="https://gdz.ru/class-7/istoriya/konturnie-karti-torop/"),
    dict(subject="history-maps", id="torop-8", grade=8,
         title="Тороп. Контурные карты",
         author="Тороп В.В., Арсентьев Н.М.",
         year="2023–2026",
         url="https://gdz.ru/class-8/istoriya/konturnie-karti-torop/"),
    dict(subject="history-maps", id="torop-9", grade=9,
         title="Тороп. Контурные карты",
         author="Тороп В.В., Арсентьев Н.М.",
         year="2023–2026",
         url="https://gdz.ru/class-9/istoriya/konturnie-karti-torop/"),
    dict(subject="geo", id="letyagin-5", grade=5,
         title="Летягин. Атлас с контурными картами",
         author="Летягин А.А.",
         year="2023–2026",
         url="https://gdz.ru/class-5/geografiya/atlas-konturnie-karti-letyagin/"),
    dict(subject="geo", id="privalovskiy-10", grade=10,
         title="Приваловский. Контурные карты, 10–11 класс",
         author="Приваловский А.Н.",
         year="2023–2026",
         url="https://gdz.ru/class-10/geografiya/konturnie-karti-privalovskij/"),
    dict(subject="geo", id="kuznetsov-10", grade=10,
         title="Кузнецов. Атлас с контурными картами, 10–11 класс",
         author="Кузнецов А.П.",
         year="2023–2026",
         url="https://gdz.ru/class-10/geografiya/atlas-s-konturnimi-kartami-kuznecov/"),
    dict(subject="history-maps", id="gushina-5", grade=5,
         title="Гущина. Контурные карты. Древний мир",
         author="Гущина Т.А.",
         year="2023–2026",
         url="https://gdz.ru/class-5/istoriya/konturnie-karti-drevnij-mir-gushina/"),
    dict(subject="history-maps", id="kolpakov-5", grade=5,
         title="Колпаков. Атлас с контурными картами",
         author="Колпаков С.В., Пономарев М.В.",
         year="2023–2026",
         url="https://gdz.ru/class-5/istoriya/atlas-s-konturnimi-kartami-i-zadaniyami-kolpakov/"),
    dict(subject="history-maps", id="torop-pereligin-10", grade=10,
         title="Тороп, Перелыгин. Контурные карты, 10–11 класс",
         author="Тороп В.В., Перелыгин В.В.",
         year="2023–2026",
         url="https://gdz.ru/class-10/istoriya/konturnie-karti-torop-pereligin/"),
]


def fetch(url: str) -> str:
    """GET с кэшем в /tmp, паузой и честным UA."""
    key = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-") + ".html"
    path = CACHE / key
    if path.exists():
        return path.read_text(encoding="utf-8")
    time.sleep(PAUSE)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    text = raw.decode("utf-8", errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def page_links(book: dict) -> list[tuple[str, str]]:
    """Страницы книги: (номер, полный URL). Поддерживает -s/ и -trnom/."""
    html = fetch(book["url"])
    slug = book["url"].rstrip("/").rsplit("/", 1)[-1]
    pages: dict[str, str] = {}
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"/" + re.escape(slug) + r"/(\d+)(?:-[a-z0-9-]+)?/?$", href)
        if not m:
            continue
        num = m.group(1)
        if num in pages:
            continue
        if href.startswith("http"):
            pages[num] = href
        elif href.startswith("/"):
            pages[num] = "https://gdz.ru" + href
    return sorted(pages.items(), key=lambda x: int(x[0]))


def task_number(html: str, fallback: str) -> str:
    title = ""
    m = re.search(r"<title>([^<]*)", html)
    if m:
        title = m.group(1)
    m = re.search(r"страница\s+(\d+)\s*[-–—]\s*(\d+)", title)
    if m:
        return m.group(1) + "–" + m.group(2)
    m = re.search(r"страница\s+(\d+)", title)
    if m:
        return m.group(1)
    return fallback


def image_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for img in soup.find_all("img"):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if "attachments/images/tasks" not in src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://gdz.ru" + src
        if src not in urls:
            urls.append(src)
    return urls


def save_scan(url: str, dest: Path) -> None:
    """Скачивает скан и сохраняет jpeg'ом с ограничением ширины."""
    if dest.exists():
        return
    time.sleep(PAUSE)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    im = Image.open(io.BytesIO(raw))
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    elif im.mode == "L":
        im = im.convert("RGB")
    if im.width > MAX_WIDTH:
        height = round(im.height * MAX_WIDTH / im.width)
        im = im.resize((MAX_WIDTH, height), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)


def process_book(book: dict, force: bool) -> None:
    out_path = DATA / book["subject"] / (book["id"] + ".json")
    if out_path.exists() and not force:
        print("книга уже собрана, пропуск:", book["id"], "(для пересборки --force)")
        return

    pages = page_links(book)
    print(f"=== {book['id']}: страниц на источнике — {len(pages)}: {', '.join(n for n, _ in pages)}")
    if not pages:
        print("!! ссылок на страницы не найдено — пропуск книги")
        return

    img_dir = DATA / book["subject"] / "img" / book["id"]
    tasks = []
    fails = 0
    for num, page_url in pages:
        try:
            html = fetch(page_url)
        except Exception as exc:  # noqa: BLE001
            print("  !! страница", num, "не скачалась:", exc)
            fails += 1
            if fails > 5:
                print("  !! больше 5 сбоев подряд — стоп книге")
                break
            continue
        fails = 0
        number = task_number(html, num)
        urls = image_urls(html)
        if not urls:
            print(f"  -- стр. {num} ({number}): картинок нет, пропуск")
            continue
        files = []
        for i, iu in enumerate(urls):
            fname = "str-" + number.replace("–", "-") + ("" if i == 0 else f"-{i + 1}") + ".jpg"
            dest = img_dir / fname
            try:
                save_scan(iu, dest)
            except Exception as exc:  # noqa: BLE001
                print(f"  !! стр. {num}: картинка {i + 1} не скачалась:", exc)
                continue
            files.append(str(dest.relative_to(DATA.parent)).replace("\\", "/"))
        if not files:
            print(f"  -- стр. {num} ({number}): ни одной картинки, пропуск")
            continue
        tasks.append({
            "number": number,
            "section": "Контурные карты",
            "condition": f"Страница {number} контурных карт.",
            "solution": "",
            "answer": "",
            "images": files,
        })
        print(f"  + стр. {num} ({number}): {len(files)} карт.")
        time.sleep(0.2)

    if not tasks:
        print("!! ни одной задачи — JSON не записан")
        return
    tasks.sort(key=lambda t: [int(p) for p in re.split(r"[–-]", t["number"]) if p.isdigit()])
    doc = {
        "subject": book["subject"],
        "textbook": book["id"],
        "author": book["author"],
        "year": book["year"],
        "source": "parsed",
        "sourceUrl": book["url"],
        "parsedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tasks": tasks,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"записано: {out_path} — задач {len(tasks)}")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    force = "--force" in sys.argv
    books = [b for b in BOOKS if not args or b["id"] in args]
    if not books:
        print("нет книг под указанные id:", args)
        return 1
    for book in books:
        try:
            process_book(book, force)
        except Exception as exc:  # noqa: BLE001
            print(f"!! книга {book['id']} упала: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
