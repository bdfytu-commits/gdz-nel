#!/usr/bin/env python3
"""Добирает пропущенные номера задач с альтернативных источников.

Пропуски считаются той же логикой, что рисует серые зачёркнутые кнопки
в приложении (app/assets/script.js, функция missingBetween): только между
соседними задачами одного раздела.

Источники по приоритету:
  1. euroki.org   — текст решений (страницы «…-zadanie-N» и «str-N»)
  2. otvet.plus   — проверяется пригодность (учебники только картинками)
  3. reshalka.com — проверяется пригодность (другие издания, сквозная нумерация)

Условие задачи берётся со страницы gdz-raketa.ru (там эти номера есть,
но без ответа). В задачу добавляются поля:
    "source": "euroki.org",
    "sourceUrl": "<страница с решением>"

Вежливость: 1 запрос в секунду на хост, честный User-Agent, robots.txt.
При 403/429/503/Cloudflare источник помечается заблокированным; если
заблокированы все три — прогон останавливается, собранное не теряется.

Использование:
    uv run --with beautifulsoup4 scripts/fill_gaps.py --dry-run
    uv run --with beautifulsoup4 scripts/fill_gaps.py --book vilenkin-6-1 --limit 3
    uv run --with beautifulsoup4 scripts/fill_gaps.py

Полный прогон (без --dry-run/--book/--limit) обновляет отчёт в docs/PARSING.md.
"""

from __future__ import annotations

import argparse
import difflib
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
DOCS = ROOT / "docs"
UA = "GdzNelBot/1.0 (+https://bdfytu-commits.github.io/gdz-nel/; educational)"
DELAY = 1.5  # секунд между запросами к одному хосту

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse_gdz as pg  # noqa: E402  (переиспользуем извлечение текста gdz-raketa)

# --------------------------------------------------------------------------
# конфигурация: где лежит каждая книга на каждом источнике
# --------------------------------------------------------------------------

BOOKS: dict[str, dict] = {
    "vilenkin-6-1": {
        "title": "Математика-1", "file": "math/vilenkin-6-1.json", "subject": "math",
        "euroki": ("section", "https://www.euroki.org/gdz/ru/matematika/6_klass/vilenkin-fgos-192"),
        "gdz": ("single", "https://gdz-raketa.ru/matematika/6-klass/uchebnik-vilenkin", 1),
        "otvet": "http://otvet.plus/6-klass/matematika/vilenkin/",
        "reshalka": "https://reshalka.com/uchebniki/6-klass/matematika/vilenkin",
    },
    "vilenkin-6-2": {
        "title": "Математика-2", "file": "math/vilenkin-6-2.json", "subject": "math",
        "euroki": ("section", "https://www.euroki.org/gdz/ru/matematika/6_klass/vilenkin-fgos-192"),
        "gdz": ("single", "https://gdz-raketa.ru/matematika/6-klass/uchebnik-vilenkin", 2),
        "otvet": "http://otvet.plus/6-klass/matematika/vilenkin/",
        "reshalka": "https://reshalka.com/uchebniki/6-klass/matematika/vilenkin",
    },
    "ladyzhenskaya-6-1": {
        "title": "Русский-1", "file": "russian/ladyzhenskaya-6-1.json", "subject": "russian",
        "euroki": ("plain", "https://www.euroki.org/gdz/ru/russkiy/6_klass/reshebnik-po-russkomu-yazyku-6-klass-fgos-baranov-ladyzhenskaya-124"),
        "gdz": ("single", "https://gdz-raketa.ru/russkiy-yazyk/6-klass/uchebnik-ladyzhenskaya", 1),
        "otvet": "http://otvet.plus/6-klass/russkij-jazik/ladyzhenskaya/",
        "reshalka": None,
    },
    "ladyzhenskaya-6-2": {
        "title": "Русский-2", "file": "russian/ladyzhenskaya-6-2.json", "subject": "russian",
        "euroki": ("plain", "https://www.euroki.org/gdz/ru/russkiy/6_klass/reshebnik-po-russkomu-yazyku-6-klass-fgos-baranov-ladyzhenskaya-124"),
        "gdz": ("single", "https://gdz-raketa.ru/russkiy-yazyk/6-klass/uchebnik-ladyzhenskaya", 2),
        "otvet": "http://otvet.plus/6-klass/russkij-jazik/ladyzhenskaya/",
        "reshalka": None,
    },
    "vaulina-6": {
        "title": "Английский", "file": "english/vaulina-6.json", "subject": "english",
        "euroki": ("page", "https://www.euroki.org/gdz/ru/angliyskiy/6_klass/e_vaulina_d_duli_v_jevans_o_podoljanko_2_fgos"),
        "gdz": ("page", "https://gdz-raketa.ru/english/6-klass/uchebnik-vaulina", "stranitsa"),
        "otvet": "http://otvet.plus/6-klass/anglijskij-jazyk/spotlight/",
        "reshalka": "https://reshalka.com/uchebniki/6-klass/english/vaulina1",
    },
    "pasechnik-6": {
        "title": "Биология", "file": "biology/pasechnik-6.json", "subject": "biology",
        "euroki": ("page", "https://www.euroki.org/gdz/ru/biologiya/6_klass/pasechnik-fgos-438"),
        "gdz": ("page", "https://gdz-raketa.ru/biologiya/6-klass/pasechnik-uchebnik", "stranitsa"),
        "otvet": None,
        "reshalka": "https://reshalka.com/uchebniki/6-klass/biologia/pasechnik",
        # страницы 18–20 на euroki.org не существуют, но все три лабораторные
        # работы есть на странице параграфа §2; сопоставление проверено по
        # соседним заданиям (18.7 ↔ шаг 7, 18.9 ↔ шаг 9, 19.2 ↔ шаг 2 и т.д.)
        "euroki_fallback": {
            "url": "https://www.euroki.org/gdz/ru/biologiya/6_klass/pasechnik-fgos-438/2",
            "steps": {
                "18.8": (1, 8), "18.10": (1, 10), "18.11": (1, 11), "18.12": (1, 12),
                "19.3": (2, 3),
                "20.3": (3, 3), "20.4": (3, 4),
            },
        },
    },
    "medinsky-6": {
        "title": "История", "file": "history/medinsky-6.json", "subject": "history",
        "euroki": ("page", "https://www.euroki.org/gdz/ru/istoriya/6_klass/srednih-vekov-medinskii-323"),
        "gdz": ("page", "https://gdz-raketa.ru/istoriya/6-klass/uchebnik-medinskij", "stranica"),
        "otvet": None,
        "reshalka": None,
    },
    "bogolyubov-6": {
        "title": "Обществознание", "file": "social/bogolyubov-6.json", "subject": "social",
        "euroki": ("page", "https://www.euroki.org/gdz/ru/obshestvoznanie/6_klass/bogolubov-553"),
        "gdz": ("page", "https://gdz-raketa.ru/obshhestvoznanie/6-klass/uchebnik-bogolubov", "stranica"),
        "otvet": None,
        "reshalka": None,
    },
}

REASONS = {
    "images": "только изображения",
    "no_page": "нет страницы",
    "no_item": "нет нужного номера",
    "no_book": "нет книги",
    "other_edition": "другое издание/нумерация",
    "blocked": "заблокировал запросы",
    "no_condition": "условие не найдено на gdz-raketa",
    "mismatch": "не совпало с условием",
}

# --------------------------------------------------------------------------
# сеть: роботы, пауза на хост, защита от бана
# --------------------------------------------------------------------------


class HostBlocked(RuntimeError):
    """Источник ответил 403/429/503 или Cloudflare-заглушкой."""


_last_request: dict[str, float] = {}
_robots_cache: dict[str, list[str]] = {}
_html_cache: dict[str, str] = {}
_blocked: set[str] = set()


def _robots_allowed(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = f"{parts.scheme}://{parts.netloc}"
    if host not in _robots_cache:
        rules: list[str] = []
        for attempt in range(3):
            if attempt:
                time.sleep(DELAY)
            try:
                req = urllib.request.Request(host + "/robots.txt", headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = resp.read()
                if raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                body = raw.decode("utf-8", "replace")
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
                break
            except urllib.error.HTTPError as err:
                if err.code == 404:  # robots.txt нет — ограничений нет
                    break
                if err.code in (403, 429, 503):
                    _blocked.add(parts.netloc)
                    raise HostBlocked(f"robots.txt: HTTP {err.code} на {host}") from err
                raise
            except Exception as err:
                if attempt == 2:  # сеть не отдала robots.txt — не трогаем хост
                    print(f"  ! не удалось прочитать robots.txt {host} ({err})", file=sys.stderr)
                    _blocked.add(parts.netloc)
                    raise HostBlocked(f"robots.txt недоступен: {host}") from err
        _robots_cache[host] = rules
    path = parts.path or "/"
    for rule in _robots_cache[host]:
        pattern = re.escape(rule).replace(r"\*", ".*")
        if re.match(pattern, path):
            return False
    return True


def _pace(host: str) -> None:
    pause = DELAY - (time.time() - _last_request.get(host, 0.0))
    if pause > 0:
        time.sleep(pause)
    _last_request[host] = time.time()


def get(url: str) -> str:
    """Скачивает страницу (с кэшем). Пустая строка — страницы нет (404)."""
    if url in _html_cache:
        return _html_cache[url]
    host = urllib.parse.urlsplit(url).netloc
    if host in _blocked:
        raise HostBlocked(f"{host} уже заблокирован")
    if not _robots_allowed(url):
        raise RuntimeError(f"robots.txt запрещает {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru"})
    html = ""
    for attempt in range(3):
        _pace(host)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                html = resp.read().decode(charset, "replace")
            break
        except urllib.error.HTTPError as err:
            if err.code == 404:
                _html_cache[url] = ""
                return ""
            if err.code in (403, 429, 503):
                _blocked.add(host)
                raise HostBlocked(f"HTTP {err.code} на {url}") from err
            raise
        except Exception as err:  # обрыв соединения и прочие сетевые сбои
            if attempt == 2:
                print(f"  ! не удалось скачать {url} ({err})", file=sys.stderr)
                _html_cache[url] = ""
                return ""
    head = html[:4000].lower()
    if "just a moment" in head or "attention required" in head or "cf-error" in head:
        _blocked.add(host)
        raise HostBlocked(f"Cloudflare-заглушка на {url}")
    _html_cache[url] = html
    return html


# --------------------------------------------------------------------------
# пропуски — как в приложении
# --------------------------------------------------------------------------


def number_parts(num: str) -> list[int]:
    return [int(p) if p.isdigit() else 0 for p in re.split(r"[.\-]", str(num))]


def task_key(task: dict) -> tuple[list[int], str]:
    return (number_parts(task["number"]), str(task["number"]))


def missing_between(a: str, b: str) -> list[str]:
    ma = re.fullmatch(r"(\d+)\.(\d+)", str(a))
    mb = re.fullmatch(r"(\d+)\.(\d+)", str(b))
    if ma and mb and ma.group(1) == mb.group(1):
        return [f"{ma.group(1)}.{k}" for k in range(int(ma.group(2)) + 1, int(mb.group(2)))]
    if str(a).isdigit() and str(b).isdigit():
        return [str(k) for k in range(int(a) + 1, int(b))]
    return []


def find_gaps(book: dict) -> list[tuple[str, str]]:
    """[(раздел, номер пропуска)] — ровно те серые ячейки, что рисует сайт."""
    tasks = sorted(book["tasks"], key=task_key)
    gaps: list[tuple[str, str]] = []
    current = None
    prev = None
    for task in tasks:
        name = task.get("section") or "Все задания"
        if name != current:
            current = name
            prev = None
        if prev is not None:
            for missed in missing_between(prev, task["number"]):
                gaps.append((name, missed))
        prev = task["number"]
    return gaps


# --------------------------------------------------------------------------
# условия со страницы gdz-raketa
# --------------------------------------------------------------------------

FLEX_NUMBER_RE = re.compile(r"^Номер\.?\s+([0-9]+(?:\.[0-9]+)*(?:-\d+)?)\.?\s*(.*)$")


def gdz_condition(html: str, expected: str) -> str | None:
    """Условие задачи по номеру (страница может содержать несколько «Номер K.»)."""
    soup = BeautifulSoup(html, "html.parser")
    lines = pg._main_lines(soup)
    for i, line in enumerate(lines):
        match = FLEX_NUMBER_RE.match(line)
        if not match or match.group(1) != expected:
            continue
        cond: list[str] = []
        if match.group(2).strip():
            cond.append(match.group(2).strip())
        for nxt in lines[i + 1:]:
            if pg._is_stop(nxt) or pg._ANSWER_RE.match(nxt) or pg._TRANS_RE.match(nxt):
                break
            if FLEX_NUMBER_RE.match(nxt) or pg.NUMBER_RE.match(nxt):
                break
            cond.append(nxt)
        text = "\n".join(cond).strip()
        return text or None
    return None


def condition_for(cfg: dict, number: str) -> str | None:
    scheme = cfg["gdz"]
    if scheme[0] == "single":
        _, base, part = scheme
        if "." in number:
            section, task = number.split(".", 1)
            url = f"{base}/{part}-chast-nomer-{section}-{task}/"
        else:
            url = f"{base}/{part}-chast-nomer-{number}/"
        expected = number
    else:
        _, base, word = scheme
        page = number.split(".", 1)[0]
        url = f"{base}/{word}-{page}/"
        expected = number.split(".", 1)[1]
    html = get(url)
    if not html:
        return None
    return gdz_condition(html, expected)


# --------------------------------------------------------------------------
# euroki.org: извлечение решений
# --------------------------------------------------------------------------

JUNK_EXACT = {
    "Скачать ответ", "📸", "Решить моё задание", "Поделись с друзьями", "Add",
    "✂️", "Короче", "✨", "Другими словами", "➕", "Подробнее", "↩️", "Вернуть",
    "📍", "Оглавление", "Нужно другое издание?", "Все номера",
}


def _is_junk(line: str) -> bool:
    if line in JUNK_EXACT:
        return True
    if "Тапни предложение" in line:
        return True
    if "ОК ГДЗ - домашка" in line or "\\boxed{\\mathbf" in line:
        return True
    return bool(re.fullmatch(r"§\s*Задание\s*\d+", line))


def _clean_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    block = soup.select_one(".txt_version") or soup.select_one(".gdz-text-solution")
    if not block:
        return []
    raw = block.get_text("\n", strip=True)
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    return [line for line in lines if not _is_junk(line)]


def _read_group(s: str, i: int) -> tuple[str, int]:
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
    return s[i + 1:], len(s)


def _wrap(expr: str) -> str:
    expr = expr.strip()
    if re.search(r"[+\-·×:= ]", expr) and not (expr.startswith("(") and expr.endswith(")")):
        return f"({expr})"
    return expr


def _convert_fracs(s: str) -> str:
    out: list[str] = []
    i = 0
    while True:
        k = s.find("\\frac", i)
        if k < 0:
            out.append(s[i:])
            break
        out.append(s[i:k])
        j = k + len("\\frac")
        while j < len(s) and s[j] == " ":
            j += 1
        if j < len(s) and s[j] == "{":
            a, j2 = _read_group(s, j)
            while j2 < len(s) and s[j2] == " ":
                j2 += 1
            if j2 < len(s) and s[j2] == "{":
                b, j3 = _read_group(s, j2)
                a = _convert_fracs(a).strip()
                b = _convert_fracs(b).strip()
                prefix = "".join(out)
                if prefix and prefix[-1].isdigit():
                    out.append(" ")
                out.append(_wrap(a) + "/" + _wrap(b))
                i = j3
                continue
        i = k + len("\\frac")
    return "".join(out)


LATEX_REPL = {
    "\\cdot": "·", "\\times": "×", "\\div": ":", "\\dots": "…", "\\ldots": "…",
    "\\approx": "≈", "\\ne": "≠", "\\neq": "≠", "\\le": "≤", "\\leq": "≤",
    "\\ge": "≥", "\\geq": "≥", "\\pm": "±", "\\mp": "∓", "\\pi": "π",
    "\\alpha": "α", "\\beta": "β", "\\gamma": "γ", "\\degree": "°",
    "\\%": "%", "\\&": "&", "\\,": " ", "\\;": " ", "\\:": " ",
    "\\!": "", "\\ ": " ", "\\quad": "  ", "\\qquad": "   ",
    "\\left": "", "\\right": "", "\\displaystyle": "", "\\limits": "",
    "\\mid": "|", "\\vert": "|", "\\lvert": "|", "\\rvert": "|",
}


def latex_to_text(line: str) -> str:
    s = line.strip()
    if s.startswith("\\[") and s.endswith("\\]"):
        s = s[2:-2]
    elif s.startswith("\\(") and s.endswith("\\)"):
        s = s[2:-2]
    s = re.sub(r"\\sqrt\{([^{}]*)\}", r"√(\1)", s)
    s = _convert_fracs(s)
    for key in sorted(LATEX_REPL, key=len, reverse=True):  # \left раньше \le и т.п.
        s = s.replace(key, LATEX_REPL[key])
    for _ in range(6):
        new = re.sub(
            r"\\(?:mathbf|textbf|mathrm|text|boxed|textit|underline|overline|operatorname)\s*\{([^{}]*)\}",
            r"\1", s)
        if new == s:
            break
        s = new
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = s.replace("{", "").replace("}", "")
    s = s.replace("^2", "²").replace("^3", "³")
    return re.sub(r"[ \t]+", " ", s).strip()


def math_solution(html: str) -> list[str]:
    out: list[str] = []
    for line in _clean_lines(html):
        if line.startswith("§ "):
            continue
        converted = latex_to_text(line)
        if converted:
            out.append(converted)
    return out


def page_items(html: str) -> dict[int, str]:
    """Пронумерованные пункты страницы («3. …») — для english/bio/history/social."""
    lines = _clean_lines(html)
    chunks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if re.match(r"^§\s*Стр\.?\s*\d+", line):
            if current:
                chunks.append(current)
            current = []
        else:
            current.append(line)
    if current:
        chunks.append(current)

    items: dict[int, str] = {}
    for chunk in chunks:
        i = 0
        while i < len(chunk):
            match = re.match(r"^(\d{1,3})\.\s*(.*)$", chunk[i])
            if not match:
                i += 1
                continue
            num = int(match.group(1))
            body = [match.group(2)] if match.group(2) else []
            j = i + 1
            while j < len(chunk) and not re.match(r"^\d{1,3}\.\s", chunk[j]):
                body.append(chunk[j])
                j += 1
            text = "\n".join(part for part in body if part.strip()).strip()
            if text and (num not in items or len(text) > len(items[num])):
                items[num] = text
            i = j
    return items


def pick_answer(lines: list[str]) -> str:
    """Ответ: последняя строка с «=», иначе последняя строка (с склейкой переносов)."""
    for line in reversed(lines):
        if line.startswith("="):
            return line
    answer = lines[-1]
    i = len(lines) - 1
    while i > 0 and answer[:1].islower() and not re.search(r"[.!?:;)\]°]$", lines[i - 1]):
        answer = lines[i - 1] + " " + answer
        i -= 1
    return answer


_LAB_RE = re.compile(r"^Лабораторная работа\s*№?\s*(\d+)\s*[.:]", re.IGNORECASE)
_LAB_STEP_RE = re.compile(r"^(\d{1,2})\.\s*(.*)$")
_LAB_STOP_RE = re.compile(
    r"^(§\s*\d|Стр\.\s*\d|Лабораторная работа|Задания для|№\s*\d|Цель работы|Материалы и)")

def _section_steps(body: list[str]) -> dict[int, str]:
    """Нумерованные шаги одной лабораторной работы."""
    steps: dict[int, str] = {}
    i = 0
    while i < len(body):
        match = _LAB_STEP_RE.match(body[i])
        if not match:
            i += 1
            continue
        num = int(match.group(1))
        parts = [match.group(2)] if match.group(2).strip() else []
        j = i + 1
        while (j < len(body) and not _LAB_STEP_RE.match(body[j])
               and not _LAB_STOP_RE.match(body[j])):
            parts.append(body[j])
            j += 1
        text = "\n".join(part for part in parts if part.strip()).strip()
        if text and (num not in steps or len(text) > len(steps[num])):
            steps[num] = text
        i = j if j > i else i + 1
    return steps

def _lab_steps(lines: list[str]) -> dict[int, dict[int, str]]:
    """Лабораторные работы страницы параграфа: {№ работы: {№ шага: текст}}.

    На странице параграфа работы идут подряд, номера шагов внутри каждой
    начинаются заново, поэтому их нельзя брать из page_items (там на один
    номер остаётся самый длинный текст). Оглавление вверху страницы даёт
    пустые «варианты» работ — выбирается вариант с наибольшим числом шагов.
    """
    sections: dict[int, list[list[str]]] = {}
    current_num: int | None = None
    current: list[str] = []
    for line in lines:
        match = _LAB_RE.match(line)
        if match:
            if current_num is not None:
                sections.setdefault(current_num, []).append(current)
            current_num = int(match.group(1))
            current = []
        elif current_num is not None:
            current.append(line)
    if current_num is not None:
        sections.setdefault(current_num, []).append(current)

    labs: dict[int, dict[int, str]] = {}
    for num, variants in sections.items():
        best: dict[int, str] = {}
        for body in variants:
            steps = _section_steps(body)
            if len(steps) > len(best):
                best = steps
        labs[num] = best
    return labs

def euroki_fallback_step(cfg: dict, number: str) -> tuple[dict | None, str]:
    """Задание со страницы параграфа для страниц, которых нет на euroki.org."""
    fb = cfg["euroki_fallback"]
    lab, step = fb["steps"][number]
    html = get(fb["url"])
    if not html:
        return None, REASONS["no_page"]
    text = _lab_steps(_clean_lines(html)).get(lab, {}).get(step)
    if not text:
        return None, REASONS["no_item"]
    return {"solution": text, "answer": text.split("\n")[-1], "url": fb["url"]}, ""

def euroki_find(cfg: dict, number: str) -> tuple[dict | None, str]:
    fb = cfg.get("euroki_fallback")
    if fb and number in fb.get("steps", {}):
        return euroki_fallback_step(cfg, number)

    scheme, base = cfg["euroki"]
    if scheme == "section":
        match = re.fullmatch(r"(\d+)\.(\d+)", number)
        if not match:
            return None, REASONS["no_item"]
        url = f"{base}/{match.group(1)}-zadanie-{match.group(2)}"
        html = get(url)
        if not html:
            return None, REASONS["no_page"]
        solution = math_solution(html)
        if not solution:
            return None, REASONS["no_item"]
        return {"solution": "\n".join(solution), "answer": pick_answer(solution), "url": url}, ""

    if scheme == "plain":
        url = f"{base}/zadanie-{number}"
        html = get(url)
        if not html:
            return None, REASONS["no_page"]
        solution = math_solution(html)
        if not solution:
            return None, REASONS["images"]
        return {"solution": "\n".join(solution), "answer": pick_answer(solution), "url": url}, ""

    page = number.split(".", 1)[0]
    label = int(number.split(".", 1)[1])
    url = f"{base}/str-{page}"
    html = get(url)
    if not html:
        return None, REASONS["no_page"]
    text = page_items(html).get(label)
    if not text:
        return None, REASONS["no_item"]
    return {"solution": text, "answer": text.split("\n")[-1], "url": url}, ""


# --------------------------------------------------------------------------
# otvet.plus и reshalka.com: честная проверка пригодности
# --------------------------------------------------------------------------

_probe_cache: dict[str, str] = {}


def otvet_probe(cfg: dict) -> str:
    key = "otvet:" + cfg["title"]
    if key in _probe_cache:
        return _probe_cache[key]
    url = cfg.get("otvet")
    if not url:
        reason = REASONS["no_book"]
    else:
        html = get(url)
        if not html:
            reason = REASONS["no_book"]
        else:
            soup = BeautifulSoup(html, "html.parser")
            hrefs = [a["href"] for a in soup.find_all("a", href=True)]
            images = [h for h in hrefs if re.search(r"\.(?:png|jpe?g)$", h, re.I)]
            numeric = [h for h in hrefs if re.search(r"/\d+/?$", h)]
            if images and not numeric:
                reason = REASONS["images"]
            elif numeric:
                reason = REASONS["other_edition"]
            else:
                reason = REASONS["no_book"]
    _probe_cache[key] = reason
    return reason


def reshalka_probe(cfg: dict) -> str:
    key = "reshalka:" + cfg["title"]
    if key in _probe_cache:
        return _probe_cache[key]
    url = cfg.get("reshalka")
    if not url:
        reason = REASONS["no_book"]
    else:
        html = get(url)
        if not html:
            reason = REASONS["no_book"]
        else:
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.get_text(strip=True) if soup.title else ""
            numeric = [a["href"] for a in soup.find_all("a", href=True)
                       if re.search(r"/\d+$", a["href"])]
            # у reshalka сквозная нумерация и старые издания (2008–2019) —
            # нашим книгам (2023–2026) она не соответствует
            reason = REASONS["other_edition"] if numeric else REASONS["no_book"]
            if title:
                reason += f" ({title[:60]})"
    _probe_cache[key] = reason
    return reason


# --------------------------------------------------------------------------
# сравнение условия с найденным текстом (защита от сдвига страниц)
# --------------------------------------------------------------------------


def _norm(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^а-яa-z0-9 ]+", " ", text)
    return " ".join(text.split())


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _norm(a), _norm(b), autojunk=False).ratio()


def strip_leading_condition(solution: str, condition: str) -> str:
    """Убирает из решения повтор условия: euroki сначала повторяет вопрос.

    Строки снимаются, только когда их начало дословно совпадает с условием
    (после нормализации); иначе решение возвращается без изменений.
    """
    if "\n" not in solution:
        return solution
    c = _norm(condition)
    if not c:
        return solution
    lines = solution.split("\n")
    acc = ""
    for i, line in enumerate(lines):
        acc = (acc + " " + _norm(line)).strip()
        if not acc:
            continue
        if acc == c:
            rest = "\n".join(lines[i + 1:]).strip()
            return rest or solution
        if not c.startswith(acc):
            return solution
    return solution


def head_similarity(a: str, b: str) -> float:
    """Сходство условия с началом найденного текста.

    Решения с таблицами и списками намного длиннее условия, и общий ratio
    занижается, хотя такие решения обычно начинаются с условия дословно.
    """
    c = _norm(a)
    s = _norm(b)[:len(c) + 40]
    if not c or not s:
        return 0.0
    return difflib.SequenceMatcher(None, c, s, autojunk=False).ratio()


# --------------------------------------------------------------------------
# прогон
# --------------------------------------------------------------------------


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return few
    return many


def process_book(book_id: str, cfg: dict, args: argparse.Namespace) -> dict:
    path = DATA / cfg["file"]
    data = json.loads(path.read_text(encoding="utf-8"))
    gaps = find_gaps(data)
    if args.limit:
        gaps = gaps[:args.limit]

    stat = {
        "title": cfg["title"], "gaps": len(gaps), "filled": 0,
        "filled_by": Counter(), "reasons": Counter(), "saved": [],
    }
    if not gaps:
        print(f"=== {cfg['title']}: пропусков нет")
        return stat

    print(f"\n=== {cfg['title']}: {len(gaps)} "
          f"{plural(len(gaps), 'пропуск', 'пропуска', 'пропусков')}")

    otvet_reason: str | None = None
    reshalka_reason: str | None = None

    for section, number in gaps:
        try:
            condition = condition_for(cfg, number)
        except HostBlocked as err:
            print(f"  !! {err} — останавливаюсь на gdz-raketa")
            stat["reasons"][REASONS["blocked"]] += 1
            break
        if not condition:
            print(f"  {number}: условие не найдено на gdz-raketa — пропуск")
            stat["reasons"][REASONS["no_condition"]] += 1
            continue

        found = None
        reason = ""
        try:
            found, reason = euroki_find(cfg, number)
        except HostBlocked as err:
            print(f"  ! euroki.org: {err}")
            reason = REASONS["blocked"]
        if found and cfg["euroki"][0] == "page" and cfg["subject"] != "english":
            score = similarity(condition, found["solution"])
            head = head_similarity(condition, found["solution"])
            if score < 0.15 and head < 0.55:
                print(f"  {number}: euroki нашёл текст, но он не похож на условие "
                      f"({score:.2f}/{head:.2f}) — пропуск")
                found = None
                reason = REASONS["mismatch"]
            else:
                print(f"  {number}: сходство с условием {max(score, head):.2f}")

        if not found:
            if otvet_reason is None:
                try:
                    otvet_reason = otvet_probe(cfg)
                except HostBlocked as err:
                    print(f"  ! otvet.plus: {err}")
                    otvet_reason = REASONS["blocked"]
            if reshalka_reason is None:
                try:
                    reshalka_reason = reshalka_probe(cfg)
                except HostBlocked as err:
                    print(f"  ! reshalka.com: {err}")
                    reshalka_reason = REASONS["blocked"]
            details = "; ".join(
                f"{name} — {why}" for name, why in
                (("euroki.org", reason), ("otvet.plus", otvet_reason), ("reshalka.com", reshalka_reason))
                if why
            )
            print(f"  {number}: не добито ({details})")
            stat["reasons"][reason or REASONS["no_item"]] += 1
            if len(_blocked) >= 3:
                print("  !! все три источника заблокировали запросы — стоп")
                break
            continue

        solution = strip_leading_condition(found["solution"], condition)
        task = {
            "number": number,
            "section": section,
            "condition": condition,
            "solution": solution,
            "answer": found["answer"],
            "source": "euroki.org",
            "sourceUrl": found["url"],
        }
        if args.dry_run:
            preview_c = condition.replace("\n", " ")[:90]
            preview_s = solution.replace("\n", " ")[:110]
            print(f"  {number}: + euroki.org  условие: {preview_c}")
            print(f"      решение: {preview_s}")
        else:
            data["tasks"].append(task)
            data["tasks"].sort(key=task_key)
            print(f"  {number}: добавлено с euroki.org")
        stat["filled"] += 1
        stat["filled_by"]["euroki.org"] += 1
        stat["saved"].append(number)

    if stat["filled"] and not args.dry_run:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  записано: {path.relative_to(ROOT)} (+{stat['filled']})")
    return stat


def report_lines(stats: list[dict]) -> list[str]:
    lines: list[str] = []
    total = filled = 0
    for stat in stats:
        total += stat["gaps"]
        filled += stat["filled"]
        left = stat["gaps"] - stat["filled"]
        if stat["filled"]:
            source = stat["filled_by"].most_common(1)[0][0]
            done = f"добито {stat['filled']} с {source}, "
        else:
            done = "добито 0, "
        if left == 0:
            rest = "пустых не осталось"
        elif left == 1:
            rest = "1 остался пустым"
        else:
            rest = f"{left} остались пустыми"
        reason = ""
        if stat["reasons"]:
            reason = " (" + "; ".join(f"{why} — {count}" for why, count in stat["reasons"].most_common()) + ")"
        lines.append(f"- {stat['title']}: {stat['gaps']} "
                     f"{plural(stat['gaps'], 'пропуск', 'пропуска', 'пропусков')}, {done}{rest}.{reason}")
    if stats:
        lines.append(f"- Итого: {total} {plural(total, 'пропуск', 'пропуска', 'пропусков')}, "
                     f"добито {filled}, {total - filled} остались пустыми.")
    return lines


def update_parsing_doc(lines: list[str]) -> None:
    path = DOCS / "PARSING.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    block = (
        "<!-- fill-gaps:start -->\n"
        f"### Добор пропусков (fill_gaps.py), {stamp}\n\n"
        "Пропуски считаются той же логикой, что серые зачёркнутые кнопки в приложении\n"
        "(`missingBetween` в `app/assets/script.js`). Условие берётся со страницы gdz-raketa.ru,\n"
        "решение и ответ — с альтернативного источника; в задаче стоят `source` и `sourceUrl`.\n\n"
        + "\n".join(lines) + "\n\n"
        "Источники по приоритету: euroki.org → otvet.plus → reshalka.com. Запросы — не чаще\n"
        "одного в 1,5 секунды на хост, честный User-Agent, robots.txt соблюдается.\n"
        "<!-- fill-gaps:end -->"
    )
    if "<!-- fill-gaps:start -->" in text and "<!-- fill-gaps:end -->" in text:
        text = re.sub(r"<!-- fill-gaps:start -->.*?<!-- fill-gaps:end -->", block, text, flags=re.S)
    elif "## Журнал" in text:
        text = text.replace("## Журнал", block + "\n\n## Журнал", 1)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8")
    print(f"\nотчёт: {path.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Добор пропущенных задач с альтернативных источников")
    parser.add_argument("--book", help="только один учебник (id файла)")
    parser.add_argument("--limit", type=int, help="не больше N пропусков на книгу (для проверки)")
    parser.add_argument("--dry-run", action="store_true", help="ничего не записывать")
    args = parser.parse_args()

    if args.book and args.book not in BOOKS:
        print(f"нет такого учебника: {args.book}. Доступно: {', '.join(BOOKS)}", file=sys.stderr)
        return 1
    ids = [args.book] if args.book else list(BOOKS)

    stats = [process_book(book_id, BOOKS[book_id], args) for book_id in ids]
    lines = report_lines(stats)
    print("\n" + "\n".join(lines))

    full_run = not args.dry_run and not args.book and not args.limit
    if full_run and stats:
        update_parsing_doc(lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
