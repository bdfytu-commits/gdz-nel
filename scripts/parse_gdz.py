#!/usr/bin/env python3
"""Парсер ГДЗ для проекта ГДЗ НЭЛ.

Источник: gdz-raketa.ru (первый в списке ТЗ). Уважает robots.txt,
держит 1 запрос в секунду, честный User-Agent.

Использование:
    uv run --with beautifulsoup4 scripts/parse_gdz.py vilenkin-6-1
    uv run --with beautifulsoup4 scripts/parse_gdz.py all             # все доступные задания
    uv run --with beautifulsoup4 scripts/parse_gdz.py all --limit 30  # первые 30 на книгу
    uv run --with beautifulsoup4 scripts/parse_gdz.py all --resume    # дополнить после сбоя
    uv run --with beautifulsoup4 scripts/parse_gdz.py all --dry       # превью в /tmp, без записи

При 403/429/Cloudflare или серии недоступных страниц парсер останавливается сам
и сохраняет собранное — не долбит источник.

Логика:
  * math/russian  — одна задача на страницу: «Номер 1.1.» + условие + «Ответ:»
  * english/bio/history/social — на странице несколько «Номер K.»;
    номер задачи = «страница.K», раздел — заголовок страницы (модуль/параграф)
"""

from __future__ import annotations

import argparse
import json
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
UA = "GdzNelBot/1.0 (+https://bdfytu-commits.github.io/gdz-nel/; educational, contact: ivan@localhost)"
DELAY = 1.1  # секунд между запросами

_last_request = 0.0
_robots_cache: dict[str, list[str]] = {}


# --------------------------------------------------------------------------
# сеть
# --------------------------------------------------------------------------

def _wait() -> None:
    global _last_request
    pause = DELAY - (time.time() - _last_request)
    if pause > 0:
        time.sleep(pause)
    _last_request = time.time()


def _robots_allowed(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = f"{parts.scheme}://{parts.netloc}"
    if host not in _robots_cache:
        rules: list[str] = []
        try:
            req = urllib.request.Request(host + "/robots.txt", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", "replace")
            in_star = False
            for line in body.splitlines():
                line = line.split("#")[0].strip()
                if not line or ":" not in line:
                    continue
                key, _, value = line.partition(":")
                key, value = key.strip().lower(), value.strip()
                if key == "user-agent":
                    in_star = value == "*"
                elif key == "disallow" and in_star and value:
                    rules.append(value)
        except Exception as err:  # нет robots — консервативно запрещаем только при ошибке сети
            print(f"  ! не удалось прочитать robots.txt ({err}), считаем запрещённым", file=sys.stderr)
            rules = ["/"]
        _robots_cache[host] = rules
    path = parts.path or "/"
    for rule in _robots_cache[host]:
        pattern = re.escape(rule).replace(r"\*", ".*")
        if re.match(pattern, path):
            return False
    return True


class SourcesBlocked(RuntimeError):
    """Источник перестал отдавать страницы (403/429/Cloudflare) — стоп без долбёжки."""


def fetch(url: str) -> BeautifulSoup:
    if not _robots_allowed(url):
        raise RuntimeError(f"robots.txt запрещает {url}")
    _wait()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        if err.code in (403, 429, 503):
            raise SourcesBlocked(f"HTTP {err.code} на {url} — похоже на бан или Cloudflare") from err
        raise
    head = html[:4000].lower()
    if "just a moment" in head or "attention required" in head or "cf-error" in head:
        raise SourcesBlocked(f"Cloudflare-заглушка на {url}")
    return BeautifulSoup(html, "html.parser")


def _expected_number(url: str) -> str | None:
    """Номер, который должна дать страница (для --resume), или None."""
    m = re.search(r"-nomer-(\d+)-(\d+)/$", url)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    m = re.search(r"-nomer-(\d+)/$", url)
    if m:
        return m.group(1)
    return None


def _number_key(number: str) -> list[int]:
    return [int(p) for p in re.split(r"[.\-]", number) if p.isdigit()]


# --------------------------------------------------------------------------
# извлечение текста
# --------------------------------------------------------------------------

META_PREFIXES = (
    "тип:", "авторы:", "автор", "часть:", "год:", "серия:", "издательство:",
    "материал подготовила:", "гдз", "6 класс", "учебник", "а класс", "рабочая тетрадь",
    "книга для", "тренажёр", "тренажер", "контрольные", "проверочные",
)
STOP_MARKERS = (
    "конец страницы", "переход на другие страницы", "содержание",
    "информация на этой странице", "нашли ошибку на сайте",
    "сообщить об ошибке", "с подпиской рекламы", "подключите премиум",
    "поделитесь ответами", "понравились решения", "вам может быть интересно",
    "твой лучший помощник", "рекомендуем посмотреть", "© ", "заполните форму",
    "выберите тип ошибки", "отличается задание", "оставить отзыв",
    "неполное решение", "нет решения", "опечатка", "ошибка в ответе",
    "не совпадает номер", "спасибо! ваше сообщение", "сообщение должно",
    "не понял задачу", "гдз по фото", "войдите", "войди через",
    "о нас", "блог", "отзывы", "карта сайта", "личный кабинет", "контакты",
    "для рекламодателей", "премиум подписка", "правообладателям",
    "публичная оферта", "пользовательское соглашение", "согласие на обработку",
    "напишите свой комментарий", "подключить", "решебник 2017",
)


INLINE_TAGS = ("span", "strong", "em", "b", "i", "sup", "sub", "u", "small", "a", "mark")


def _main_lines(soup: BeautifulSoup) -> list[str]:
    main = soup.select_one("main") or soup.body
    if main is None:
        return []
    # инлайн-теги (дроби вида <span class="fraction">2/3</span>, выделения)
    # разворачиваем в текст, чтобы они не рвали строку на части
    for tag in main.find_all(INLINE_TAGS):
        tag.replace_with(tag.get_text())
    main.smooth()  # склеиваем соседние текстовые узлы в один
    text = main.get_text("\n", strip=True)
    return [line for line in (l.strip() for l in text.split("\n")) if line]


def _is_meta(line: str) -> bool:
    low = line.lower()
    if any(low.startswith(p) for p in META_PREFIXES):
        return True
    if re.match(r"^\d+ класс$", low):
        return True
    if "гдз по " in low and "класс" in low:
        return True
    return False


def _is_stop(line: str) -> bool:
    low = line.lower()
    return any(low.startswith(m) for m in STOP_MARKERS)


_META_LABEL_RE = re.compile(r"^(материал подготовил[аи]|автор|авторы)\s*:?\s*$", re.I)


def _looks_like_heading(line: str, allow_numbered: bool = True) -> bool:
    if line.startswith("§"):
        return True
    letters = [ch for ch in line if ch.isalpha()]
    is_caps = bool(letters) and all(ch.isupper() for ch in letters)
    if is_caps and "ГЛАВА" not in line:
        return True
    if allow_numbered and re.match(r"^\d+\.\s+\S", line):
        return True
    if " — " in line and len(line) < 80:
        return True
    return False


def _heading_before(lines: list[str], first_idx: int, default: str = "",
                    allow_numbered: bool = True) -> str:
    """Заголовок (раздел/модуль/параграф) перед первой задачей страницы."""
    meta_end = 0
    for i in range(first_idx):
        if _META_LABEL_RE.match(lines[i]):
            meta_end = i + 2  # ярлык и значение (имя) под ним
    candidates: list[str] = []
    for i in range(meta_end, first_idx):
        line = lines[i]
        low = line.lower()
        if _is_stop(line) or _ANSWER_RE.match(line):
            break
        if _is_meta(line) or len(line) > 100 or line.endswith(":"):
            continue
        if _looks_like_heading(line, allow_numbered):
            candidates.append(line.rstrip("."))
    return candidates[-1] if candidates else default


NUMBER_RE = re.compile(r"^Номер\.?\s+([0-9]+(?:\.[0-9]+)*)\.?$")
_ANSWER_RE = re.compile(r"^ответ\s*:?\s*$", re.I)
_TRANS_RE = re.compile(r"^перевод\s*:?\s*$", re.I)


def parse_single_task(soup: BeautifulSoup) -> dict | None:
    """Страница с одной задачей: math, russian."""
    lines = _main_lines(soup)
    idx = next((i for i, l in enumerate(lines) if NUMBER_RE.match(l)), None)
    if idx is None:
        return None
    number = NUMBER_RE.match(lines[idx]).group(1)

    cond: list[str] = []
    sol: list[str] = []
    trans: list[str] = []
    mode = "cond"
    for line in lines[idx + 1:]:
        if _is_stop(line):
            break
        if _ANSWER_RE.match(line):
            mode = "sol"
            continue
        if _TRANS_RE.match(line):
            mode = "trans"
            continue
        if NUMBER_RE.match(line):
            break
        if mode == "cond":
            cond.append(line)
        elif mode == "sol":
            # служебные хвосты отзывов могут идти после решения
            if _is_stop(line):
                break
            sol.append(line)
        else:
            trans.append(line)

    if not cond or not sol:
        return None
    solution = "\n".join(sol)
    if trans:
        solution += "\nПеревод:\n" + "\n".join(trans)
    return {
        "number": number,
        "section": _heading_before(lines, idx),
        "condition": "\n".join(cond),
        "solution": solution,
        "answer": sol[-1],
    }


def parse_page_tasks(soup: BeautifulSoup, page: str) -> list[dict]:
    """Страница с несколькими «Номер K.»: english, bio, history, social."""
    lines = _main_lines(soup)
    marks = [i for i, l in enumerate(lines) if NUMBER_RE.match(l)]
    if not marks:
        return []

    section = _heading_before(lines, marks[0], allow_numbered=False)
    out: list[dict] = []
    used: dict[str, int] = {}
    for pos, idx in enumerate(marks):
        number = NUMBER_RE.match(lines[idx]).group(1)
        used[number] = used.get(number, 0) + 1
        if used[number] > 1:
            number = f"{number}-{used[number]}"
        end = marks[pos + 1] if pos + 1 < len(marks) else len(lines)
        cond: list[str] = []
        sol: list[str] = []
        trans: list[str] = []
        mode = "cond"
        for line in lines[idx + 1:end]:
            if _is_stop(line):
                break
            if _ANSWER_RE.match(line):
                mode = "sol"
                continue
            if _TRANS_RE.match(line):
                mode = "trans"
                continue
            if mode == "cond":
                cond.append(line)
            elif mode == "sol":
                sol.append(line)
            else:
                trans.append(line)
        if not cond or not sol:
            continue
        solution = "\n".join(sol)
        if trans:
            solution += "\nПеревод:\n" + "\n".join(trans)
        out.append({
            "number": f"{page}.{number}",
            "section": section,
            "condition": "\n".join(cond),
            "solution": solution,
            "answer": sol[-1],
        })
    return out


def _tidy_section(line: str) -> str:
    """«§ 1. БИОЛОГИЧЕСКОЕ И СОЦИАЛЬНОЕ…» → «§ 1. Биологическое и социальное…»"""
    m = re.match(r"^(§\s*\d+[.,]?)\s+(.+)$", line)
    if m:
        title = m.group(2).lower().rstrip(".")
        title = title[:1].upper() + title[1:]
        return f"{m.group(1)} {title}"
    return line


def _is_rubric(line: str) -> bool:
    """Рубрики Боголюбова: ЗАДУМАЕМСЯ, ВСПОМНИМ, ПРОВЕРИМ СЕБЯ."""
    if not line or len(line) > 40 or line.startswith("§"):
        return False
    letters = [ch for ch in line if ch.isalpha()]
    return bool(letters) and all(ch.isupper() for ch in letters) and "ГЛАВА" not in line


def parse_rubric_tasks(soup: BeautifulSoup, page: str, default_section: str = "") -> list[dict]:
    """Страница с рубриками (обществознание): «ЗАДУМАЕМСЯ» + вопрос + «Ответ:»."""
    lines = _main_lines(soup)
    rubrics = [i for i, l in enumerate(lines) if _is_rubric(l)]
    if not rubrics:
        return []

    section = default_section
    for i in range(rubrics[0]):
        if lines[i].startswith("§"):
            section = _tidy_section(lines[i])

    out: list[dict] = []
    idx = 0
    for pos, start in enumerate(rubrics):
        end = rubrics[pos + 1] if pos + 1 < len(rubrics) else len(lines)
        cond: list[str] = []
        sol: list[str] = []
        mode = "cond"
        for line in lines[start + 1:end]:
            if _is_stop(line):
                break
            if _ANSWER_RE.match(line):
                mode = "sol"
                continue
            if _TRANS_RE.match(line) or NUMBER_RE.match(line):
                continue
            if mode == "cond":
                cond.append(line)
            else:
                sol.append(line)
        if not cond or not sol:
            continue
        idx += 1
        out.append({
            "number": f"{page}.{idx}",
            "section": section,
            "condition": "\n".join(cond),
            "solution": "\n".join(sol),
            "answer": sol[-1],
        })
    return out


# --------------------------------------------------------------------------
# конфигурация учебников
# --------------------------------------------------------------------------

HEADERS = {
    "math": ("Виленкин Н.Я., Жохов В.И., Чесноков А.С., Шварцбурд С.И.", "2023–2026"),
    "russian": ("Ладыженская Т.А., Баранов М.Т., Тростенцова Л.А. и др.", "2023"),
    "english": ("Ваулина Ю.Е., Дули Д., Подоляко О.Е. и др.", "2026"),
    "biology": ("Пасечник В.В., Суматохин С.В., Гапонюк З.Г.", "2023–2024"),
    "history": ("Мединский В.Р., Чубарьян А.О.", "2025"),
    "social": ("Боголюбов Л.Н., Рутковская Е.Л., Иванова Л.Ф. и др.", "2023"),
}

BOOKS: dict[str, dict] = {
    "vilenkin-6-1": {
        "subject": "math", "textbook": "vilenkin-6-1", "part": 1,
        "index": "https://gdz-raketa.ru/matematika/6-klass/uchebnik-vilenkin/",
        "kind": "single",
        "section": "§1. Вычисления и построения",
        # названия § по учебнику (часть 1: стр. 44 — §2, дальше §3); страницы глав заголовков не несут
        "section_map": {
            "1": "§1. Вычисления и построения",
            "2": "§2. Действия со смешанными числами",
            "3": "§3. Отношения и пропорции",
        },
        # §1: 1..198, §2: 1..540, §3: 1..193 (по индексной странице источника)
        "urls": [f"https://gdz-raketa.ru/matematika/6-klass/uchebnik-vilenkin/1-chast-nomer-1-{i}/"
                 for i in range(1, 199)]
        + [f"https://gdz-raketa.ru/matematika/6-klass/uchebnik-vilenkin/1-chast-nomer-2-{i}/"
           for i in range(1, 541)]
        + [f"https://gdz-raketa.ru/matematika/6-klass/uchebnik-vilenkin/1-chast-nomer-3-{i}/"
           for i in range(1, 194)],
    },
    "vilenkin-6-2": {
        "subject": "math", "textbook": "vilenkin-6-2", "part": 2,
        "index": "https://gdz-raketa.ru/matematika/6-klass/uchebnik-vilenkin/",
        "kind": "single",
        "section": "§4",
        # названия § по учебнику (часть 2)
        "section_map": {
            "4": "§4. Действия с рациональными числами",
            "5": "§5. Решение уравнений",
            "6": "§6. Координаты на плоскости",
        },
        # §4: 1..399, §5: 1..133, §6: 1..126
        "urls": [f"https://gdz-raketa.ru/matematika/6-klass/uchebnik-vilenkin/2-chast-nomer-4-{i}/"
                 for i in range(1, 400)]
        + [f"https://gdz-raketa.ru/matematika/6-klass/uchebnik-vilenkin/2-chast-nomer-5-{i}/"
           for i in range(1, 134)]
        + [f"https://gdz-raketa.ru/matematika/6-klass/uchebnik-vilenkin/2-chast-nomer-6-{i}/"
           for i in range(1, 127)],
    },
    "ladyzhenskaya-6-1": {
        "subject": "russian", "textbook": "ladyzhenskaya-6-1", "part": 1,
        "index": "https://gdz-raketa.ru/russkiy-yazyk/6-klass/uchebnik-ladyzhenskaya/",
        "kind": "single", "section": "",
        "urls": [f"https://gdz-raketa.ru/russkiy-yazyk/6-klass/uchebnik-ladyzhenskaya/1-chast-nomer-{i}/"
                 for i in range(1, 407)],
    },
    "ladyzhenskaya-6-2": {
        "subject": "russian", "textbook": "ladyzhenskaya-6-2", "part": 2,
        "index": "https://gdz-raketa.ru/russkiy-yazyk/6-klass/uchebnik-ladyzhenskaya/",
        "kind": "single", "section": "",
        "urls": [f"https://gdz-raketa.ru/russkiy-yazyk/6-klass/uchebnik-ladyzhenskaya/2-chast-nomer-{i}/"
                 for i in range(407, 755)],
    },
    "vaulina-6": {
        "subject": "english", "textbook": "vaulina-6", "index":
        "https://gdz-raketa.ru/english/6-klass/uchebnik-vaulina/",
        "kind": "page", "page_pattern": "https://gdz-raketa.ru/english/6-klass/uchebnik-vaulina/stranitsa-{n}/",
        "pages": range(5, 105),
    },
    "pasechnik-6": {
        "subject": "biology", "textbook": "pasechnik-6", "section": "Глава 1. Растение – живой организм",
        "index": "https://gdz-raketa.ru/biologiya/6-klass/pasechnik-uchebnik/",
        "kind": "page", "page_pattern": "https://gdz-raketa.ru/biologiya/6-klass/pasechnik-uchebnik/stranitsa-{n}/",
        "pages": range(4, 152),
    },
    "medinsky-6": {
        "subject": "history", "textbook": "medinsky-6", "section": "Глава 1",
        "index": "https://gdz-raketa.ru/istoriya/6-klass/uchebnik-medinskij/",
        "kind": "page", "page_pattern": "https://gdz-raketa.ru/istoriya/6-klass/uchebnik-medinskij/stranica-{n}/",
        "pages": range(3, 227),
    },
    "bogolyubov-6": {
        "subject": "social", "textbook": "bogolyubov-6",
        "index": "https://gdz-raketa.ru/obshhestvoznanie/6-klass/uchebnik-bogolubov/",
        "kind": "rubric", "section": "Обществознание",
        "page_pattern": "https://gdz-raketa.ru/obshhestvoznanie/6-klass/uchebnik-bogolubov/stranica-{n}/",
        "pages": range(6, 172),
    },
}


# --------------------------------------------------------------------------
# сборка книги
# --------------------------------------------------------------------------

def collect(book_id: str, limit: int | None = None, resume: bool = False) -> dict:
    cfg = BOOKS[book_id]
    subject = cfg["subject"]
    author, year = HEADERS[subject]
    tasks: list[dict] = []
    skipped: list[str] = []
    last_section = cfg.get("section") or ""
    consecutive_failures = 0
    aborted: str | None = None

    existing_tasks: list[dict] = []
    existing_numbers: set[str] = set()
    existing_pages: set[str] = set()
    if resume:
        old_path = DATA / subject / f"{cfg['textbook']}.json"
        if old_path.exists():
            try:
                old = json.loads(old_path.read_text(encoding="utf-8"))
                existing_tasks = old.get("tasks", [])
                existing_numbers = {t["number"] for t in existing_tasks}
                existing_pages = {n.split(".")[0] for n in existing_numbers if "." in n}
                if existing_tasks:
                    # страницы могут не нести собственный заголовок — наследуем раздел
                    last_section = existing_tasks[-1].get("section") or last_section
            except (json.JSONDecodeError, KeyError) as err:
                print(f"  ! не удалось прочитать {old_path} для --resume: {err}")
        print(f"  --resume: в файле уже {len(existing_tasks)} заданий")
    skipped_existing = 0

    def take(task: dict | None, url: str) -> bool:
        nonlocal last_section
        if not task:
            skipped.append(url)
            return False
        lines_out = task["solution"].splitlines() + [task["answer"]]
        if any(l.strip().lower().startswith(("продолжение на следующей", "начало на предыдущей"))
               for l in lines_out):
            skipped.append(url)
            return False
        if task.get("section"):
            last_section = task["section"]
        else:
            task["section"] = last_section or "Все задания"
        tasks.append(task)
        return True

    def fail(url: str, err: object) -> None:
        """Сбой одной страницы; много подряд — источник явно не в духе, останавливаемся."""
        nonlocal consecutive_failures
        consecutive_failures += 1
        print(f"  ! {url}: {err}")
        skipped.append(url)
        if consecutive_failures >= 12:
            raise SourcesBlocked(f"{consecutive_failures} страниц подряд не отдались (последняя: {url})")

    def ok_fetch(url: str) -> BeautifulSoup:
        nonlocal consecutive_failures
        soup = fetch(url)
        consecutive_failures = 0
        return soup

    try:
        if cfg["kind"] == "single":
            total = len(cfg["urls"])
            for i, url in enumerate(cfg["urls"], 1):
                if limit is not None and len(tasks) >= limit:
                    break
                expected = _expected_number(url)
                if expected and expected in existing_numbers:
                    skipped_existing += 1
                    continue
                try:
                    soup = ok_fetch(url)
                except SourcesBlocked:
                    raise
                except Exception as err:
                    fail(url, err)
                    continue
                task = parse_single_task(soup)
                take(task, url)
                num = f"№{task['number']}" if task else "пропуск"
                print(f"  {len(tasks):4d} задач  {i}/{total}  {num:>9}  {task['section'][:44] if task else ''}")
        else:
            pages = list(cfg["pages"])
            total = len(pages)
            for i, page in enumerate(pages, 1):
                if limit is not None and len(tasks) >= limit:
                    break
                if resume and str(page) in existing_pages:
                    skipped_existing += 1
                    continue
                url = cfg["page_pattern"].format(n=page)
                try:
                    soup = ok_fetch(url)
                except SourcesBlocked:
                    raise
                except Exception as err:
                    fail(url, err)
                    continue
                page_tasks = parse_page_tasks(soup, str(page))
                if not page_tasks and cfg["kind"] == "rubric":
                    page_tasks = parse_rubric_tasks(soup, str(page))
                if not page_tasks:
                    skipped.append(url)
                    continue
                for task in page_tasks:
                    if limit is not None and len(tasks) >= limit:
                        break
                    take(task, url)
                first = page_tasks[0] if page_tasks else None
                print(f"  {len(tasks):4d} задач  стр. {page:>3} ({i}/{total})  на странице: {len(page_tasks)}  {first['section'][:36] if first else ''}")
    except SourcesBlocked as err:
        aborted = str(err)
        print(f"  !! источник закрылся: {aborted}")

    if resume and existing_tasks:
        merged = {t["number"]: t for t in existing_tasks}
        for t in tasks:
            merged[t["number"]] = t
        tasks = sorted(merged.values(), key=lambda t: _number_key(t["number"]))
    if cfg.get("section_map"):
        # страницы источника не несут заголовки § — раскладываем по номеру задания
        for t in tasks:
            mapped = cfg["section_map"].get(t["number"].split(".")[0])
            if mapped:
                t["section"] = mapped
    if skipped_existing:
        print(f"  --resume: пропущено (уже было в файле): {skipped_existing}")

    data = {
        "subject": subject,
        "textbook": cfg["textbook"],
        "author": author,
        "year": year,
        "source": "parsed",
        "sourceUrl": cfg["index"],
        "parsedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tasks": tasks,
    }
    if "part" in cfg:
        data["part"] = cfg["part"]
    return {"data": data, "skipped": skipped, "aborted": aborted}


def main() -> None:
    ap = argparse.ArgumentParser(description="Парсер ГДЗ (gdz-raketa.ru)")
    ap.add_argument("book", help="id учебника или all")
    ap.add_argument("--limit", type=int, default=None,
                    help="сколько заданий собрать (по умолчанию — все доступные)")
    ap.add_argument("--dry", action="store_true", help="не писать в app/data, сохранить превью в /tmp")
    ap.add_argument("--resume", action="store_true",
                    help="дополнить существующий файл, не перекачивая уже собранное")
    args = ap.parse_args()

    ids = list(BOOKS) if args.book == "all" else [args.book]
    blocked = False
    for book_id in ids:
        if book_id not in BOOKS:
            print(f"нет такого учебника: {book_id}", file=sys.stderr)
            sys.exit(1)
        suffix = f" (до {args.limit} заданий)" if args.limit else " (полный сбор)"
        print(f"\n=== {book_id}{suffix}{' +resume' if args.resume else ''}")
        result = collect(book_id, args.limit, args.resume)
        data = result["data"]
        if result["aborted"]:
            blocked = True
        if data["tasks"]:
            if args.dry:
                path = Path("/tmp") / f"gdz_preview_{book_id}.json"
            else:
                subject_dir = DATA / data["subject"]
                subject_dir.mkdir(parents=True, exist_ok=True)
                path = subject_dir / f"{data['textbook']}.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"  задач: {len(data['tasks'])}, пропущено страниц: {len(result['skipped'])}")
            print(f"  записано: {path}")
        else:
            print("  !! ничего не собрано")
        if blocked:
            break
    if blocked:
        print("\n!! СБОР ПРЕРВАН: источник перестал отдавать страницы. "
              "Собранное записано; продолжать позже (правила — docs/PARSING.md).", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
