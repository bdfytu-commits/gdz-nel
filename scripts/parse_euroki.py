#!/usr/bin/env python3
"""Литература Коровиной (6–9 классы, части 1–2) с euroki.org: текст → JSON.

euroki отдаёт решебник постранично: страница книги («Часть 1, Стр. 107» или
«Часть 2, Стр. 10») = несколько карточек «рубрика → вопрос → ответ» обычным
текстом (в отличие от gdz.ru, где только сканы). Каждая часть книги пишется
отдельным файлом:

    app/data/literature/korovina-6-1.json

Номера задач — «страница.порядковый» (107.1, 107.2, …), чтобы на одной
странице мирно уживались вопросы из разных рубрик.

Запуск (из корня gdz-nel):

    uv run --no-project --with beautifulsoup4 scripts/parse_euroki.py
    uv run --no-project --with beautifulsoup4 scripts/parse_euroki.py korovina-9-2
    uv run --no-project --with beautifulsoup4 scripts/parse_euroki.py --force

Скрипт идемпотентный: HTML кэшируется в /tmp/opencode/euroki-cache, готовые
книги по умолчанию пропускаются (--force перекачивает). Пауза 1.1 с, честный
UA, robots.txt на euroki.org отсутствует (404 — запретов нет).
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
CACHE = Path("/tmp/opencode/euroki-cache")
UA = "Mozilla/5.0 (X11; Linux x86_64; gdz-nel data parser; +https://bdfytu-commits.github.io/gdz-nel/)"
PAUSE = 1.1  # секунда между запросами к источнику

# Литература под ред. Коровиной, ФГОС (Просвещение):
# 6 класс — Полухина, Коровина; 7–9 — Коровина, Журавлев, Коровин.
BOOKS = [
    dict(subject="literature", id="korovina-6-1", grade=6, part=1,
         title="Коровина. Часть 1",
         author="Полухина В.П., Коровина В.Я., Журавлев В.П., Коровин В.И.",
         year="2023",
         url="https://www.euroki.org/gdz/ru/literatura/6_klass/korovina-156"),
    dict(subject="literature", id="korovina-6-2", grade=6, part=2,
         title="Коровина. Часть 2",
         author="Полухина В.П., Коровина В.Я., Журавлев В.П., Коровин В.И.",
         year="2023",
         url="https://www.euroki.org/gdz/ru/literatura/6_klass/korovina-156"),
    dict(subject="literature", id="korovina-7-1", grade=7, part=1,
         title="Коровина. Часть 1",
         author="Коровина В.Я., Журавлев В.П., Коровин В.И.",
         year="2023",
         url="https://www.euroki.org/gdz/ru/literatura/7_klass/korovina-fgos-653"),
    dict(subject="literature", id="korovina-7-2", grade=7, part=2,
         title="Коровина. Часть 2",
         author="Коровина В.Я., Журавлев В.П., Коровин В.И.",
         year="2023",
         url="https://www.euroki.org/gdz/ru/literatura/7_klass/korovina-fgos-653"),
    dict(subject="literature", id="korovina-8-1", grade=8, part=1,
         title="Коровина. Часть 1",
         author="Коровина В.Я., Журавлев В.П., Коровин В.И.",
         year="2023",
         url="https://www.euroki.org/gdz/ru/literatura/8_klass/korovina-fgos-314"),
    dict(subject="literature", id="korovina-8-2", grade=8, part=2,
         title="Коровина. Часть 2",
         author="Коровина В.Я., Журавлев В.П., Коровин В.И.",
         year="2023",
         url="https://www.euroki.org/gdz/ru/literatura/8_klass/korovina-fgos-314"),
    dict(subject="literature", id="korovina-9-1", grade=9, part=1,
         title="Коровина. Часть 1",
         author="Коровина В.Я., Журавлев В.П., Коровин В.И.",
         year="2023",
         url="https://www.euroki.org/gdz/ru/literatura/9_klass/korovina-fgos-18"),
    dict(subject="literature", id="korovina-9-2", grade=9, part=2,
         title="Коровина. Часть 2",
         author="Коровина В.Я., Журавлев В.П., Коровин В.И.",
         year="2023",
         url="https://www.euroki.org/gdz/ru/literatura/9_klass/korovina-fgos-18"),
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


def clean(text: str) -> str:
    """Убираем пустые строки и хвостовые пробелы."""
    lines = [ln.strip() for ln in text.split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def normalize_section(section: str) -> str:
    """Длинные рубрики-инструкции («Объясните слова и словосочетания, …») —
    режем до первой запятой/двоеточия, чтобы не раздувать чипы разделов."""
    s = section.strip()
    if 0 < len(s) <= 48:
        return s
    for sep in (":", ",", ";"):
        head = s.split(sep, 1)[0].strip()
        if 4 <= len(head) <= 48:
            return head
    return s[:45].rstrip() + "…"


# карточки без .gdz-solution-card__question: первый абзац ответа иногда
# содержит сам вопрос (euroki не разметил), а дальше — ответ
QUESTION_STARTS = re.compile(
    r"^(Назовите|Прочитайте|Объясните|Подготовьте|Найдите|Сравните|Опишите|"
    r"Расскажите|Составьте|Выпишите|Ответьте|Вспомните|Перескажите|"
    r"Рассмотрите|Подумайте|Докажите|Определите|Запишите|Выучите|Используя|"
    r"Как|Что|Какие|Кто|Где|Когда|Почему|Зачем|Чем|Сколько|Есть ли|Можно ли|"
    r"Согласны ли|Вы согласны)",
    re.IGNORECASE,
)


def part_links(html: str, part: int) -> list[str]:
    """Относительные ссылки страниц указанной части, по возрастанию номера.

    Слаги бывают двух видов: «1-str-107» и «1-str-102-148» (суффикс-хэш).
    """
    found: dict[int, str] = {}
    for m in re.finditer(r'href="(/gdz/ru/literatura/\d+_klass/[^"/]+/' + str(part) + r'-str-(\d+)(?:-\d+)?)/?"', html):
        found[int(m.group(2))] = m.group(1)
    return [found[n] for n in sorted(found)]


def parse_page(html: str, page: int, url: str, stats: dict) -> list[dict]:
    """Карточки страницы → задачи."""
    soup = BeautifulSoup(html, "html.parser")
    tasks = []
    for i, card in enumerate(soup.select("article.gdz-solution-card"), 1):
        a = card.select_one(".gdz-solution-card__answer")
        sec = card.select_one(".gdz-solution-card__section")
        section = normalize_section(clean(sec.get_text(" ", strip=True))) if sec else "Задания"
        q = card.select_one(".gdz-solution-card__question")
        qtext = clean(q.get_text("\n", strip=True)) if q else ""
        atext = clean(a.get_text("\n", strip=True)) if a else ""
        if not qtext:
            # euroki не разметил вопрос: пробуем вытащить из первого абзаца ответа
            stats["noq"] += 1
            paras = [clean(p.get_text(" ", strip=True)) for p in (a.find_all("p") if a else [])]
            paras = [p for p in paras if p]
            if len(paras) >= 2 and (paras[0].endswith("?") or QUESTION_STARTS.match(paras[0])):
                qtext = paras[0]
                atext = "\n".join(paras[1:])
                stats["noq_split"] += 1
            else:
                qtext = f"Страница {page}. {section.rstrip('.')}."
        if not atext:
            # нет блока ответа (euroki отдаёт такую карточку без решения) —
            # в данные не берём, как и основной парсер
            stats["empty"] += 1
            continue
        tasks.append({
            "number": f"{page}.{i}",
            "section": section,
            "condition": qtext,
            "solution": atext,
            "answer": atext,
            "source": "euroki.org",
            "sourceUrl": url,
        })
    return tasks


def process_book(book: dict, force: bool) -> None:
    out_path = DATA / book["subject"] / (book["id"] + ".json")
    if out_path.exists() and not force:
        print(f"-- {book['id']}: уже собран, пропуск (--force для пересборки)")
        return
    index_html = fetch(book["url"])
    links = part_links(index_html, book["part"])
    print(f"== {book['id']}: страниц в части {book['part']} — {len(links)}")
    tasks: list[dict] = []
    empty = 0
    stats = {"noq": 0, "noq_split": 0, "empty": 0}
    for rel in links:
        url = "https://www.euroki.org" + rel
        page = int(re.search(r"-str-(\d+)", rel).group(1))
        try:
            html = fetch(url)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! стр. {page}: не скачалась:", exc)
            continue
        got = parse_page(html, page, url, stats)
        if not got:
            empty += 1
            print(f"  -- стр. {page}: карточек нет, пропуск")
        tasks.extend(got)
    if not tasks:
        print("!! ни одной задачи — JSON не записан")
        return
    tasks.sort(key=lambda t: [int(p) for p in t["number"].split(".")])
    doc = {
        "subject": book["subject"],
        "textbook": book["id"],
        "part": book["part"],
        "author": book["author"],
        "year": book["year"],
        "source": "parsed",
        "sourceUrl": book["url"],
        "parsedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tasks": tasks,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"записано: {out_path} — задач {len(tasks)}, пустых страниц {empty}"
          f", без вопроса {stats['noq']} (из них склеено из абзаца: {stats['noq_split']})"
          f", пропущено без ответа {stats['empty']}")


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
