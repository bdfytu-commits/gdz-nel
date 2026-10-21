#!/usr/bin/env python3
"""Массовый сбор учебников 3, 4, 10 и 11 классов с euroki.org.

Источник отдаёт готовые решения текстом (у части книг — сканы, такие книги
пропускаются). Скрипт сам разбирает оглавление книги, поддерживает части,
постраничные и пономерные ссылки, чистит LaTeX и пишет по JSON на книгу.

Запуск из корня проекта:

    uv run --with beautifulsoup4 scripts/parse_euroki_bulk.py --dry --limit 3
    uv run --with beautifulsoup4 scripts/parse_euroki_bulk.py --grades 3,4
    uv run --with beautifulsoup4 scripts/parse_euroki_bulk.py --only moro
    nohup uv run --with beautifulsoup4 scripts/parse_euroki_bulk.py \
        > /tmp/opencode/parse_new_grades.log 2>&1 &

Скрипт идемпотентный: готовые файлы по умолчанию пропускаются (--force
перекачивает). HTML кэшируется в /tmp/opencode/euroki-bulk-cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
INVENTORY = ROOT / "scripts" / "euroki_books.json"
CACHE = Path(os.environ.get("EUROKI_CACHE", "/tmp/opencode/euroki-bulk-cache"))
MANIFEST = DATA / "_bulk_manifest.json"
IMAGE_CACHE: dict[str, bool] = {}
CHECK_IMAGES = True
UA_POOL = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]
PAUSE = float(os.environ.get("EUROKI_PAUSE", "0.8"))
_last_request = 0.0
_ua_index = 0
_consecutive_errors = 0

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def translit(text: str) -> str:
    out = "".join(TRANSLIT.get(ch.lower(), ch) for ch in text)
    out = re.sub(r"[^a-z0-9]+", "-", out.lower()).strip("-")
    return out or "book"


def wait() -> None:
    global _last_request
    pause = PAUSE - (time.time() - _last_request)
    if pause > 0:
        time.sleep(pause)
    _last_request = time.time()


def cache_path(url: str) -> Path:
    """Куда класть HTML в кэш.

    Linux не даёт имена длиннее 255 байт, а slug из URL легко уходит за
    тысячу символов — раньше это валило парсер с Errno 36. Поэтому имя по
    умолчанию — md5 от URL; старое «читаемое» имя ищем только если файл там
    уже лежит (совместимость с прогретым кэшем).
    """
    hashed = CACHE / ("h-" + hashlib.md5(url.encode("utf-8")).hexdigest() + ".html")
    if hashed.exists():
        return hashed
    legacy = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-") + ".html"
    if len(legacy.encode("utf-8")) <= 240:
        old = CACHE / legacy
        if old.exists():
            return old
    return hashed


def fetch(url: str, force: bool = False) -> str:
    """GET с дисковым кэшем, паузой и повторами при 403/429/5xx."""
    global _ua_index, _consecutive_errors
    path = cache_path(url)
    if path.exists() and not force:
        return path.read_text(encoding="utf-8")
    last_exc: Exception | None = None
    for attempt in range(3):
        wait()
        ua = UA_POOL[_ua_index % len(UA_POOL)]
        safe_url = urllib.parse.quote(url, safe=":/?&=%#")
        req = urllib.request.Request(safe_url, headers={"User-Agent": ua, "Accept-Language": "ru"})
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            _consecutive_errors = 0
            return text
        except urllib.error.HTTPError as exc:
            last_exc = exc
            _consecutive_errors += 1
            if exc.code in (403, 429):
                print(f"  !! HTTP {exc.code}: пауза 60 с и смена UA", flush=True)
                _ua_index += 1
                time.sleep(60)
            elif exc.code >= 500:
                print(f"  !! HTTP {exc.code}: повтор через 10 с", flush=True)
                time.sleep(10)
            else:
                break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _consecutive_errors += 1
            print(f"  !! сеть: {exc}; повтор через 5 с", flush=True)
            time.sleep(5)
    raise RuntimeError(f"не скачалось {url}: {last_exc}")


def image_ok(url: str) -> bool:
    """Проверяет скан: 404/410 выкидываем, остальные ответы считаем живыми."""
    if not CHECK_IMAGES:
        return True
    if url in IMAGE_CACHE:
        return IMAGE_CACHE[url]
    ok = False
    for method in ("HEAD", "GET"):
        try:
            headers = {"User-Agent": UA_POOL[0]}
            if method == "GET":
                headers["Range"] = "bytes=0-1023"
            req = urllib.request.Request(url, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                ok = resp.status < 400
            if ok:
                break
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410):
                ok = False
                break
        except Exception:  # noqa: BLE001
            pass
    IMAGE_CACHE[url] = ok
    if not ok:
        print(f"  !! битая картинка: {url}", flush=True)
    return ok


def clean_latex(text: str) -> str:
    """LaTeX/разметку euroki → читаемый текст без потери формул."""
    if not text:
        return ""
    s = text.replace("\\[", "\n").replace("\\]", "\n")
    s = s.replace("\\(", "\n").replace("\\)", "\n")
    # дроби и корни до снятия скобок
    s = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"\1/\2", s)
    s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√\1", s)
    s = re.sub(r"\\sqrt\s*(\d+)", r"√\1", s)
    for _ in range(4):
        s = re.sub(r"\\(?:boxed|mathbf|textbf|mathrm|text|mathit|mathsf|mathtt)\s*\{([^{}]*)\}", r"\1", s)
    s = s.replace("\\ ", " ").replace("\\,", " ").replace("\\;", " ").replace("\\:", " ")
    s = s.replace("\\!", "").replace("\\quad", " ").replace("\\qquad", " ")
    s = s.replace("\\cdot", "·").replace("\\times", "×").replace("\\div", ":")
    s = s.replace("\\leq", "≤").replace("\\geq", "≥").replace("\\neq", "≠")
    s = s.replace("\\le", "≤").replace("\\ge", "≥").replace("\\ne", "≠")
    s = s.replace("\\to", "→").replace("\\Rightarrow", "⇒").replace("\\rightarrow", "→")
    s = s.replace("\\pi", "π").replace("\\alpha", "α").replace("\\beta", "β")
    s = s.replace("\\pm", "±").replace("\\infty", "∞").replace("\\angle", "∠")
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = s.replace("{", "").replace("}", "")
    s = s.replace("Еуроки  -  ДЗ без мороки", "")
    s = s.replace("Еуроки - ДЗ без мороки", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def extract_answer(solution: str) -> str:
    if not solution:
        return ""
    m = list(re.finditer(r"(?im)^\s*ответ\s*:?\s*", solution))
    if m:
        return solution[m[-1].start():].strip()
    m = re.search(r"(?i)\bОтвет\s*:\s*(.+)$", solution, re.S)
    if m:
        return "Ответ: " + m.group(1).strip()
    lines = [line.strip() for line in solution.splitlines() if line.strip()]
    return lines[-1][:1000] if lines else solution


def parse_meta(text: str, source_subject: str, grade: int) -> dict:
    author = ""
    m = re.search(r"Авторы:\s*(.+?)(?:\s+Год:|\s+Тип:|\s+Серия:|$)", text)
    if m:
        author = m.group(1).strip()
    author = re.sub(r"\s*ФГОС\s*", " ", author)
    author = re.sub(r"\s+", " ", author).strip(" ,")
    year = ""
    m = re.search(r"Год:\s*([0-9–—-]+)", text)
    if m:
        year = m.group(1)
    if not year:
        year = "2024"
    surname = ""
    if author:
        surname = re.split(r"[,;]", author)[0].strip()
        surname = re.split(r"\s+", surname)[0]
    if not surname or surname.lower() in {"старое", "авторы"}:
        surname = {
            "matematika": "Математика", "russkiy": "Русский", "biologiya": "Окружающий мир",
            "literatura": "Литература", "algebra": "Алгебра", "geometriya": "Геометрия",
            "fizika": "Физика", "himiya": "Химия", "istoriya": "История",
            "obshestvoznanie": "Обществознание", "angliyskiy": "Английский",
        }.get(source_subject, "Учебник")
    return {"author": author or surname, "surname": surname, "year": year}


SUBJECT_MAP = {
    "matematika": "math",
    "russkiy": "russian",
    "biologiya": "biology",
    "literatura": "literature",
    "algebra": "algebra",
    "geometriya": "geometry",
    "fizika": "physics",
    "himiya": "chemistry",
    "istoriya": "history",
    "obshestvoznanie": "social",
    "angliyskiy": "english",
    "geografiya": "geo",
    "informatika": "informatics",
}


def map_subject(source_subject: str, grade: int) -> str:
    if source_subject == "biologiya" and grade in (3, 4):
        return "world"
    return SUBJECT_MAP[source_subject]


def task_links(index_html: str, book: dict) -> list[dict]:
    """Все ссылки на задания книги с номером, частью и типом."""
    soup = BeautifulSoup(index_html, "html.parser")
    base_path = urllib.parse.urlsplit(book["url"]).path.rstrip("/")
    found: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(book["url"], a["href"]).split("#", 1)[0]
        path = urllib.parse.urlsplit(href).path.rstrip("/")
        if not path.startswith(base_path + "/"):
            continue
        rel = path[len(base_path) + 1:]
        if not rel or rel in {"#"}:
            continue
        item = None
        m = re.fullmatch(r"(\d+)-str-(\d+)(?:-\d+)?", rel)
        if m:
            item = {"kind": "page", "part": int(m.group(1)), "num": int(m.group(2)), "url": href}
        if not item:
            m = re.fullmatch(r"str-(\d+)", rel)
            if m:
                item = {"kind": "page", "part": 0, "num": int(m.group(1)), "url": href}
        if not item:
            m = re.fullmatch(r"chast-(\d+)-zadanie-(\d+)", rel)
            if m:
                item = {"kind": "ex", "part": int(m.group(1)), "num": int(m.group(2)), "url": href}
        if not item:
            m = re.search(r"(?:^|-)zadanie-(\d+)(?:-|$)", rel)
            if m:
                item = {"kind": "ex", "part": 0, "num": int(m.group(1)), "url": href}
        if not item:
            m = re.search(r"-str-(\d+)$", rel)
            if m:
                part = re.search(r"chast-(\d+)", rel)
                item = {"kind": "page", "part": int(part.group(1)) if part else 0,
                        "num": int(m.group(1)), "url": href}
        if not item:
            m = re.fullmatch(r"(\d+)", rel)
            if m:
                item = {"kind": "num", "part": 0, "num": int(m.group(1)), "url": href}
        if item:
            item["section"] = a.get_text(" ", strip=True)[:120]
            found[href] = item
    return sorted(found.values(), key=lambda x: (x["part"], x["kind"], x["num"]))


def split_boxed(text: str) -> list[tuple[int, str]]:
    """Делит ответ на блоки «\\boxed{\\mathbf{N.}}»."""
    matches = list(re.finditer(r"\\boxed\{\\mathbf\{(\d+)", text))
    if not matches:
        return []
    out = []
    for i, m in enumerate(matches):
        start = m.end()
        # срезать остаток служебного маркера до первого перевода строки/закрытия
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end]
        chunk = re.sub(r"^.*?\\boxed\{[^{}]*\}", "", chunk, count=1, flags=re.S)
        chunk = clean_latex(chunk)
        chunk = re.sub(r"^\s*[.}]\s*", "", chunk)
        if chunk:
            out.append((int(m.group(1)), chunk))
    return out


def page_section(soup: BeautifulSoup, fallback: str) -> str:
    h1 = soup.find("h1")
    if h1:
        text = re.sub(r"\s+", " ", h1.get_text(" ", strip=True))
        text = re.sub(r"^Решебник\s+по\s+\S+\s+\d+\s+класс\s*", "", text)
        text = re.sub(r"\s*\|\s*Номер.*$", "", text)
        text = text.strip(" .|")
        if 3 < len(text) < 180:
            return text
    return fallback


def solution_images(soup: BeautifulSoup) -> list[str]:
    """Сканы-решения с CDN euroki (не логотипы и не иконки)."""
    out = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if "imgs.euroki.org/books/gdzs/" in src and src not in out:
            out.append(src)
    return out


def parse_task_page(html: str, url: str, base: int, kind: str, force_part: int | None = None,
                    section_hint: str = "") -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("article.gdz-solution-card")
    tasks: list[dict] = []
    seq = 0

    def add(number: str, section: str, condition: str, solution: str) -> None:
        nonlocal seq
        solution = clean_latex(solution)
        condition = clean_latex(condition)
        if not solution or len(solution) < 3:
            return
        if not condition:
            condition = f"Задание {number}."
        if not section:
            section = f"Страница {base}" if kind == "page" else f"Задание {base}"
        seq += 1
        tasks.append({
            "number": number,
            "section": section[:180],
            "condition": condition[:4000],
            "solution": solution,
            "answer": extract_answer(solution),
            "source": "euroki.org",
            "sourceUrl": url,
        })

    def add_image(images: list[str]) -> None:
        nonlocal seq
        images = [u for u in images if image_ok(u)]
        if not images:
            return
        seq += 1
        section = section_hint or (f"Страница {base}" if kind == "page" else f"Задание {base}")
        tasks.append({
            "number": str(base) if len(images) == 1 else f"{base}.{seq}",
            "section": section,
            "condition": f"{section}. Решение на изображении.",
            "solution": "",
            "answer": "",
            "images": images,
            "source": "euroki.org",
            "sourceUrl": url,
        })

    if cards:
        for ci, card in enumerate(cards, 1):
            q = card.select_one(".gdz-solution-card__question")
            a = card.select_one(".gdz-solution-card__answer")
            sec = card.select_one(".gdz-solution-card__section")
            qtext = clean_latex(q.get_text("\n", strip=True)) if q else ""
            atext = a.get_text("\n", strip=True) if a else ""
            section = clean_latex(sec.get_text(" ", strip=True)) if sec else ""
            if not section or section in {"•", "-", "—"}:
                section = f"Страница {base}" if kind == "page" else f"Задание {base}"
            boxed = split_boxed(atext)
            if boxed:
                for n, chunk in boxed:
                    num = f"{base}.{n}" if kind != "ex" else (str(base) if len(boxed) == 1 else f"{base}.{n}")
                    cond = qtext if qtext and len(boxed) == 1 else f"Задание {n}. Страница {base}." if kind == "page" else f"Задание {num}."
                    add(num, section, cond, chunk)
            elif atext.strip():
                num = f"{base}.{ci}" if len(cards) > 1 else str(base)
                cond = qtext or section
                add(num, section, cond, atext)
        if not tasks:
            add_image(solution_images(soup))
    else:
        # страницы без карточек обычно сканы; иногда текст лежит в content
        main = soup.select_one(".content.one_page") or soup.select_one("main")
        if main:
            imgs = main.select("img")
            text = main.get_text("\n", strip=True)
            text = re.sub(r"^(?:Новые|Конспекты уроков|Таблицы|Банк заданий).*?Все номера", "", text, flags=re.S)
            text = clean_latex(text)
            if len(text) > 80 and not imgs:
                add(str(base), page_section(soup, f"Задание {base}"), "", text)
            if not tasks:
                add_image(solution_images(soup))
    # уникальные номера
    seen: dict[str, int] = {}
    for t in tasks:
        n = t["number"]
        if n in seen:
            seen[n] += 1
            t["number"] = f"{n}-{seen[n]}"
        else:
            seen[n] = 1
    return tasks


SPECIAL_BASE = {
    # автор в источнике — «Старое издание», а не фамилия
    "vilenkin-staroe-izdanie-219": "vilenkin-5-219",
    # автор — «Очень старое издание»
    "vilenkin-universalnoe-izdanie-941": "vilenkin-5-941",
}
SPECIAL_TITLE = {
    "vilenkin-staroe-izdanie-219": "Виленкин",
    "vilenkin-universalnoe-izdanie-941": "Виленкин",
}


def book_base_id(book: dict, meta: dict, duplicate: bool) -> str:
    grade = book["grade"]
    special = SPECIAL_BASE.get(book["slug"])
    if special:
        return special
    base = f"{translit(meta['surname'])}-{grade}"
    if duplicate:
        tail = re.search(r"-(\d+)$", book["slug"])
        if tail:
            base += f"-{tail.group(1)}"
    return base


def process_book(book: dict, duplicate: bool, force: bool, dry: bool, limit: int | None) -> dict | None:
    subject = map_subject(book["source_subject"], book["grade"])
    meta = parse_meta(book["text"], book["source_subject"], book["grade"])
    index_html = fetch(book["url"], force=force)
    links = task_links(index_html, book)
    if not links:
        print(f"-- {book['slug']}: ссылок на задания нет, пропуск", flush=True)
        return None
    parts = sorted({x["part"] for x in links})
    multi = len(parts) > 1 or (len(parts) == 1 and parts[0] > 0)
    groups = {p: [x for x in links if x["part"] == p] for p in parts}
    if limit:
        for p in groups:
            groups[p] = groups[p][:limit]
    base_id = book_base_id(book, meta, duplicate)
    made = []
    for part, items in groups.items():
        if not items:
            continue
        suffix = f"-{part}" if multi and part > 0 else ""
        book_id = base_id + suffix
        out_path = DATA / subject / (book_id + ".json")
        title_part = f". Часть {part}" if multi and part > 0 else ""
        title = f"{SPECIAL_TITLE.get(book['slug'], meta['surname'])}{title_part}"
        if out_path.exists() and not force:
            # --resume: готовый файл не перекачиваем, но возвращаем его в манифест.
            # Иначе после обрыва процесса JSON есть, а книга пропадает из каталога.
            try:
                existing = json.loads(out_path.read_text(encoding="utf-8"))
                existing_tasks = len(existing.get("tasks") or [])
            except (OSError, json.JSONDecodeError):
                existing_tasks = 0
            made.append({
                "grade": book["grade"], "source_subject": book["source_subject"], "subject": subject,
                "id": book_id, "file": f"{subject}/{book_id}.json", "title": title,
                "author": meta["author"], "year": meta["year"], "part": part if multi and part > 0 else None,
                "tasks": existing_tasks, "sourceUrl": book["url"], "slug": book["slug"],
            })
            print(f"-- {book_id}: уже есть, пропуск", flush=True)
            continue
        tasks: list[dict] = []
        print(f"== {book_id}: {len(items)} страниц/заданий", flush=True)
        for item in items:
            try:
                html = fetch(item["url"], force=False)
            except Exception as exc:  # noqa: BLE001
                print(f"  !! {item['url']}: {exc}", flush=True)
                continue
            got = parse_task_page(html, item["url"], item["num"], item["kind"], section_hint=item.get("section", ""))
            if not got:
                continue
            tasks.extend(got)
        if not tasks:
            print(f"!! {book_id}: текстовых задач нет (сканы), пропуск", flush=True)
            continue
        # нормализуем и сортируем
        def sort_key(t: dict) -> tuple:
            return tuple(int(x) for x in re.findall(r"\d+", t["number"])) or (0,)
        tasks.sort(key=sort_key)
        doc = {
            "subject": subject,
            "textbook": book_id,
            "author": meta["author"],
            "year": meta["year"],
            "source": "parsed",
            "sourceUrl": book["url"],
            "parsedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tasks": tasks,
        }
        if multi and part > 0:
            doc["part"] = part
        if not dry:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = out_path.with_suffix(".json.part")
            tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(out_path)
        entry = {
            "grade": book["grade"], "source_subject": book["source_subject"], "subject": subject,
            "id": book_id, "file": f"{subject}/{book_id}.json", "title": title,
            "author": meta["author"], "year": meta["year"], "part": part if multi and part > 0 else None,
            "tasks": len(tasks), "sourceUrl": book["url"], "slug": book["slug"],
        }
        made.append(entry)
        print(f"   записано: {out_path} — {len(tasks)} задач", flush=True)
    if not made:
        return None
    return {"book": book, "entries": made}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grades", default="3,4,5,10,11")
    ap.add_argument("--subjects", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--slugs-file", default="", help="JSON-массив slug-ов, которые парсить")
    ap.add_argument("--manifest", default=str(MANIFEST), help="куда писать манифест (для шардов)")
    ap.add_argument("--limit", type=int, default=None, help="страниц на книгу, для проверки")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--resume", action="store_true", help="не перекачивать готовые книги (поведение по умолчанию)")
    ap.add_argument("--no-check-images", action="store_true", help="не проверять сканы на 404")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    global CHECK_IMAGES
    CHECK_IMAGES = not args.no_check_images
    grades = {int(x) for x in args.grades.split(",") if x.strip()}
    subjects = {x.strip() for x in args.subjects.split(",") if x.strip()}
    all_books = json.loads(INVENTORY.read_text(encoding="utf-8"))
    all_books = [b for b in all_books if b["grade"] in grades]
    if subjects:
        all_books = [b for b in all_books if b["source_subject"] in subjects or map_subject(b["source_subject"], b["grade"]) in subjects]
    # дубли считаем по всему инвентарю, а не по шарду: ID не должны зависеть от разбиения
    counts: dict[str, int] = {}
    for b in all_books:
        key = f"{b['grade']}/{b['source_subject']}"
        counts[key] = counts.get(key, 0) + 1
    duplicates = {k for k, n in counts.items() if n > 1}
    books = all_books
    if args.only:
        books = [b for b in books if args.only in b["slug"] or args.only in b["text"]]
    if args.slugs_file:
        allowed = set(json.loads(Path(args.slugs_file).read_text(encoding="utf-8")))
        books = [b for b in books if b["slug"] in allowed]
    manifest_path = Path(args.manifest)
    manifest_entries: list[dict] = []
    if manifest_path.exists():
        try:
            manifest_entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            manifest_entries = []
    known = {(e["id"]): e for e in manifest_entries}
    for i, b in enumerate(books, 1):
        print(f"\n[{i}/{len(books)}] {b['grade']} {b['source_subject']} {b['slug']}", flush=True)
        dup = f"{b['grade']}/{b['source_subject']}" in duplicates
        try:
            res = process_book(b, dup, args.force, args.dry, args.limit)
        except Exception as exc:  # noqa: BLE001
            print(f"!! книга {b['slug']} упала: {exc}", flush=True)
            continue
        if res:
            for e in res["entries"]:
                known[e["id"]] = e
    if not args.dry:
        manifest_entries = sorted(known.values(), key=lambda e: (e["grade"], e["subject"], e["id"]))
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest_entries, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\nманифест: {manifest_path} — {len(manifest_entries)} книг", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
