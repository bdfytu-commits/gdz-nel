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
    m = re.search(r"/(?:upr)-(\d+)/$", url)
    if m:
        return m.group(1)
    return None


def _number_key(number: str) -> list[int]:
    return [int(p) for p in re.split(r"[.\-]", number) if p.isdigit()]


# --------------------------------------------------------------------------
# latex → обычный текст
# источник иногда отдаёт формулы как $$ \frac{..}{..} $$, \text, \cdot —
# конвертируем при разборе, чтобы в данных был читаемый текст
# --------------------------------------------------------------------------

_SUP_DIGITS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_SUB_DIGITS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def _read_group(text: str, pos: int) -> tuple[str, int]:
    """Содержимое {...} с учётом вложенности; pos указывает на «{»."""
    if pos >= len(text) or text[pos] != "{":
        return "", pos
    depth = 0
    for i in range(pos, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[pos + 1:i], i + 1
    return text[pos + 1:], len(text)


def _latex_simple(side: str) -> bool:
    side = re.sub(r"\\[,;:!]", " ", side).strip()
    return bool(side) and re.fullmatch(r"[\d\s,]+", side) is not None


def _latex_tidy_side(side: str) -> str:
    """Пробелы внутри чисто числовой стороны дроби — артефакт \\mathbf{9 0}."""
    s = side.strip()
    if re.fullmatch(r"[\d\s,]+", s):
        return re.sub(r"\s+", "", s)
    return s


def _latex_fracs(text: str) -> str:
    """\\frac{a}{b} → a/b (числовые) или (a) : (b); идём с конца — внутренние первыми."""
    text = text.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    guard = 0
    while "\\frac" in text and guard < 300:
        guard += 1
        idx = text.rfind("\\frac")
        j = idx + 5
        while j < len(text) and text[j] == " ":
            j += 1
        if j >= len(text) or text[j] != "{":
            text = text[:idx] + text[idx + 5:]
            continue
        numerator, k = _read_group(text, j)
        while k < len(text) and text[k] == " ":
            k += 1
        if k >= len(text) or text[k] != "{":
            text = text[:idx] + text[idx + 5:]
            continue
        denominator, end = _read_group(text, k)
        numerator = _latex_tidy_side(numerator)
        denominator = _latex_tidy_side(denominator)
        if _latex_simple(numerator) and _latex_simple(denominator):
            repl = f"{numerator.strip()}/{denominator.strip()}"
        else:
            left = numerator.strip() if _latex_simple(numerator) else f"({numerator.strip()})"
            right = denominator.strip() if _latex_simple(denominator) else f"({denominator.strip()})"
            repl = f"{left} : {right}"
        text = text[:idx] + repl + text[end:]
    return text


_FONT_CMD_RE = re.compile(
    r"\\(?:mathbf|boldsymbol|bm|mathit|mathsf|mathtt|mathcal|mathbb|text|mathrm)"
    r"\s*\{\s*([^{}]*?)\s*\}")


def _latex_unwrap_fonts(text: str) -> str:
    """\\mathbf{1} → 1 (и прочие шрифтовые команды) — до разбора дробей."""
    prev = None
    while prev != text:
        prev = text
        text = _FONT_CMD_RE.sub(r"\1", text)
    return text


_LATEX_RX = (
    (re.compile(r"\\text\s*\{\s*([^{}]*?)\s*\}"), r"\1"),
    (re.compile(r"\\mathrm\s*\{\s*([^{}]*?)\s*\}"), r"\1"),
    (re.compile(r"\\cdot\b"), "·"),
    (re.compile(r"\\times\b"), "×"),
    (re.compile(r"\\div\b"), ":"),
    (re.compile(r"\\colon\b"), ":"),
    (re.compile(r"\\left\b"), ""),
    (re.compile(r"\\right\s*\.\s*"), "}"),
    (re.compile(r"\\right\b"), ""),
    (re.compile(r"\\pi\b"), "π"),
    (re.compile(r"\\alpha\b"), "α"),
    (re.compile(r"\\beta\b"), "β"),
    (re.compile(r"\\gamma\b"), "γ"),
    (re.compile(r"\\lambda\b"), "λ"),
    (re.compile(r"\\varphi\b"), "φ"),
    (re.compile(r"\\lg\b"), "lg"),
    (re.compile(r"\\log\b"), "log"),
    (re.compile(r"\\sin\b"), "sin"),
    (re.compile(r"\\cos\b"), "cos"),
    (re.compile(r"\\tg\b"), "tg"),
    (re.compile(r"\\ctg\b"), "ctg"),
    (re.compile(r"\\geq\b"), "≥"),
    (re.compile(r"\\leq\b"), "≤"),
    (re.compile(r"\\neq\b"), "≠"),
    (re.compile(r"\\inR\b"), "∈ R"),
    (re.compile(r"\\square\b"), "□"),
    (re.compile(r"\\Gamma\b"), "Γ"),
    (re.compile(r"\\Pi\b"), "Π"),
    (re.compile(r"\\llbracket\b"), "⟦"),
    (re.compile(r"\\rrbracket\b"), "⟧"),
    (re.compile(r"\\lceil\b"), "⌈"),
    (re.compile(r"\\rceil\b"), "⌉"),
    (re.compile(r"\\lfloor\b"), "⌊"),
    (re.compile(r"\\rfloor\b"), "⌋"),
    (re.compile(r"\\ulcorner\b"), "⌜"),
    (re.compile(r"\\urcorner\b"), "⌝"),
    (re.compile(r"\\(?:mathbf|boldsymbol|bm|mathit|mathsf|mathtt|mathcal|mathbb)\s*\{\s*([^{}]*?)\s*\}"), r"\1"),
    (re.compile(r"\\\\"), " "),
    (re.compile(r"\\[;,!: ]"), " "),
)


def _latex_cmds(text: str) -> str:
    for rx, repl in _LATEX_RX:
        text = rx.sub(repl, text)
    text = re.sub(r"\\sqrt\s*\[\s*([^\]]*?)\s*\]\s*\{\s*([^{}]*?)\s*\}",
                  lambda m: m.group(1).translate(_SUP_DIGITS) + "√" + m.group(2), text)
    text = re.sub(r"\\sqrt\s*\{\s*([^{}]*?)\s*\}", r"√\1", text)
    text = re.sub(r"\\sqrt\s*(\d)", r"√\1", text)
    # таблицы (\begin{array}{c|c} … \hline … \end{array}) и прочие остатки latex
    text = re.sub(r"\\begin\s*\{?array\}?\s*(?:\{\s*[lcr|]*\s*\})?", " ", text)
    text = re.sub(r"\\end\s*\{?array\}?\s*", " ", text)
    text = re.sub(r"\\hline\b|\\cr\b", " ", text)
    text = re.sub(r"\\(?!frac\b)[a-zA-Z]+\s*", "", text)
    text = text.replace("\\{", "{").replace("\\}", "}")
    text = re.sub(r"[&]+", " ", text)
    text = re.sub(r"\{\s*\}", "", text)
    text = re.sub(r"[ \t\u00a0]{2,}", " ", text)
    return text


def _latex_block(m: re.Match) -> str:
    s = _latex_cmds(m.group(1))
    s = _latex_fracs(s)
    # пробелы вокруг операций (только внутри формул)
    s = re.sub(r"\s*=\s*", " = ", s)
    s = re.sub(r"\s*\+\s*", " + ", s)
    s = re.sub(r"\s*:\s*", " : ", s)
    s = re.sub(r"\s*∶\s*", " ∶ ", s)
    s = re.sub(r"(?<=[\d)/])-(?=\d)", " - ", s)
    s = re.sub(r"(?<=[\d)/])−(?=\d)", " − ", s)
    # пустые группы MathJax: { }^{10} → ¹⁰, { }_1 → ₁
    s = re.sub(r"\{\s*\}\s*\^\s*\{?\s*\(?\s*([\d+\-]+)(?:\s*\))?(?:\s*\})?",
               lambda m: m.group(1).translate(_SUP_DIGITS), s)
    s = re.sub(r"\^\s*\{?\s*\(?\s*([\d+\-]+)(?:\s*\))?(?:\s*\})?",
               lambda m: m.group(1).translate(_SUP_DIGITS), s)
    s = re.sub(r"\{\s*\}\s*_\s*\{?\s*\(?\s*([\d+\-]+)(?:\s*\))?(?:\s*\})?",
               lambda m: m.group(1).translate(_SUB_DIGITS), s)
    s = re.sub(r"_\s*\{?\s*\(?\s*([\d+\-]+)(?:\s*\))?(?:\s*\})?",
               lambda m: m.group(1).translate(_SUB_DIGITS), s)
    s = s.replace("^", "").replace("{", "").replace("}", "")
    # компактные переменные: «4 c» → «4c», «7 x y» → «7xy»
    s = re.sub(r"(?<=\d)\s+([a-zA-Z])(?![a-zA-Z\w])", r"\1", s)
    s = re.sub(r"([a-zA-Z])\s+([a-zA-Z])(?![a-zA-Z\w])", r"\1\2", s)
    s = re.sub(r"\s*\n\s*", " ", s)
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    s = re.sub(r"\s+([;,.])", r"\1", s)
    return " " + s.strip() + " "


def _latex_to_text(text: str) -> str:
    """Разметка latex источника → читаемый текст.

    Срабатывает, только если в строке есть математика: `$$…$$` или команды
    `\\имя` латиницей. Литеральные «\\[у]» русского раздела и английские
    цены в `$` не трогаются.
    """
    if "$$" not in text and not re.search(r"\\[a-zA-Z]", text):
        return text
    text = _latex_unwrap_fonts(text)
    text = re.sub(r"\$\$(.+?)\$\$", _latex_block, text, flags=re.S)
    # многострочные формулы $$…$$ приходят построчно — пары не всегда ловятся,
    # остатки дробей и команд доводим вне блоков
    text = _latex_fracs(text)
    if "\\" in text:
        text = _latex_cmds(text)
    text = re.sub(r"\${1,2}", "", text)
    text = re.sub(r"(?<=[\d)])=\s*", " = ", text)
    text = re.sub(r"[ \t\u00a0]{2,}", " ", text)
    return text


def _dash_fix(line: str) -> str:
    """прямая речь обычным дефисом в начале строки → длинное тире."""
    return re.sub(r"^-(?=\s+[«\"'(А-ЯЁA-Z])", "—", line)


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


def _main_lines(soup: BeautifulSoup, root=None) -> list[str]:
    main = root or soup.select_one("main") or soup.body
    if main is None:
        return []
    # инлайн-теги (дроби вида <span class="fraction">2/3</span>, выделения)
    # разворачиваем в текст, чтобы они не рвали строку на части.
    # у gdz-raketa знаменатель дроби отдаётся как <sup>\х + 4</sup> — «\» в начале
    # значит «под дробью»: превращаем в /(…) до общей развёртки
    for tag in main.find_all(INLINE_TAGS):
        if tag.name == "sup":
            inner = tag.get_text(" ", strip=True)
            if inner.startswith("\\"):
                body = inner[1:].strip()
                repl = f"/({body})" if re.search(r"\s", body) else f"/{body}"
                tag.replace_with(repl)
                continue
        tag.replace_with(tag.get_text())
    main.smooth()  # склеиваем соседние текстовые узлы в один
    text = main.get_text("\n", strip=True)
    # $$…$$ бывают многострочными (таблицы \begin{array}): построчный конвертер
    # их не видит, и в данные лезут {x}/« : ». Схлопываем блоки заранее.
    if "$$" in text:
        text = re.sub(r"\$\$(.+?)\$\$", _latex_block, text, flags=re.S)
    return [_dash_fix(_latex_to_text(line))
            for line in (l.strip() for l in text.split("\n")) if line]


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


NUMBER_RE = re.compile(r"^(?:Номер|Задание)\.?\s+([0-9]+(?:\.[0-9]+)*)\.?$")
_ANSWER_RE = re.compile(r"^ответ\s*:?\s*$", re.I)
_TRANS_RE = re.compile(r"^перевод\s*:?\s*$", re.I)


def parse_single_task(soup: BeautifulSoup, expected: str | None = None) -> dict | None:
    """Страница с одной задачей: math, russian.

    expected — номер из адреса страницы: сайт иногда лепит в заголовок
    чужой номер (например, на странице 131 стоит «Номер 133.»), поэтому
    адресу доверяем больше, чем тексту.
    """
    lines = _main_lines(soup)
    idx = next((i for i, l in enumerate(lines) if NUMBER_RE.match(l)), None)
    if idx is None:
        return None
    marker = NUMBER_RE.match(lines[idx]).group(1)
    number = expected or marker

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
# парсеры форматов 7–9 классов (издания 2019–2025)
# --------------------------------------------------------------------------

EXERCISE_RE = re.compile(r"^Упражнение\s+(\d+)\s*$")

_EXCLUDE_SELECTORS = (
    ".Modal", "#auth-popup-overlay", ".pagination-down", ".end-content",
    ".rating", ".error-mod", ".wrapper-titles", ".lenta-block", ".lenta-tit",
    ".site-footer-links", ".site-footer-legal", ".site-footer-copy", ".breadcrumbs",
    ".article-author", ".user-link", ".user__title", ".wrap-b", ".title-share",
    ".title-error", ".sres", ".nextpage", ".push-btn", ".contact-form", ".gift",
    ".img-wrapper-450", ".article-rating", ".premium-block",
)

_QUESTION_CLASSES = ("text", "description-text", "vopros")


def _main_root(soup: BeautifulSoup):
    return soup.select_one("main") or soup.body


def _excluded_ids(soup: BeautifulSoup) -> set[int]:
    ids: set[int] = set()
    for sel in _EXCLUDE_SELECTORS:
        for el in soup.select(sel):
            ids.add(id(el))
    return ids


def _content_stream(soup: BeautifulSoup) -> list[tuple[str, str, tuple[str, ...]]]:
    """Значимые узлы страницы по порядку: («h»|«q»|«m»|«p», текст, классы).

    «q» — блок вопросов (ul.rus2), «m» — маркер «Ответ:», «p» — абзац,
    «h» — заголовок h2/h3/h4. Обрыв на «Конец страницы».
    """
    root = _main_root(soup)
    if root is None:
        return []
    excluded = _excluded_ids(soup)
    stream: list[tuple[str, str, tuple[str, ...]]] = []
    for el in root.find_all(True):
        if id(el) in excluded or any(id(p) in excluded for p in el.parents):
            continue
        if el.name == "div" and "end-content" in (el.get("class") or []):
            break
        if el.name == "ul" and "rus2" in (el.get("class") or []):
            items = [li.get_text(" ", strip=True) for li in el.find_all("li")]
            text = "\n".join(t for t in items if t)
            if text:
                stream.append(("q", text, ("rus2",)))
            continue
        if el.name == "b" and "otvet" in (el.get("class") or []):
            if el.find_parent("p") is None:
                stream.append(("m", el.get_text(" ", strip=True), ("otvet",)))
            continue
        if el.name in ("h2", "h3", "h4"):
            text = el.get_text(" ", strip=True)
            if text and not _is_stop(text):
                stream.append(("h", text, ()))
            continue
        if el.name == "p":
            if el.find_parent("ul") is not None:
                continue
            text = el.get_text(" ", strip=True)
            if not text:
                continue
            cls = tuple(el.get("class") or [])
            if text.strip().lower().rstrip(":") == "ответ":
                stream.append(("m", text, cls))
                continue
            if _is_stop(text) or _is_meta(text):
                continue
            if len(text) < 40 and text.rstrip().endswith(":") and text[:1].isupper():
                # служебные ярлыки вроде «Вспомните:» / «Проверьте знания:»
                continue
            stream.append(("p", text, cls))
    return stream


def _is_question_class(cls: tuple[str, ...]) -> bool:
    return any(c in _QUESTION_CLASSES for c in cls)


def parse_exercise_tasks(soup: BeautifulSoup, page: str, default_section: str = "") -> list[dict]:
    """Английский 7–8: «Упражнение N» + условия (p.text) + ответы (p без класса)."""
    section = default_section
    tasks: list[dict] = []
    cur: dict | None = None

    def flush() -> None:
        nonlocal cur
        if cur and cur["q"] and cur["a"]:
            tasks.append({
                "number": f"{page}.{cur['n']}",
                "section": section,
                "condition": "\n".join(cur["q"]),
                "solution": "\n".join(cur["a"]),
                "answer": cur["a"][-1],
            })
        cur = None

    for kind, text, cls in _content_stream(soup):
        if kind == "h":
            section = _tidy_section(text)
            continue
        if kind in ("m", "q"):
            if kind == "q" and cur is not None:
                cur["q"].append(text)
            continue
        m = EXERCISE_RE.match(text)
        if m:
            flush()
            cur = {"n": m.group(1), "q": [], "a": []}
            continue
        if cur is None:
            continue
        if not cur["a"] and _is_question_class(cls):
            cur["q"].append(text)
        else:
            cur["a"].append(text)
    flush()
    return tasks


def parse_qa_tasks(soup: BeautifulSoup, page: str, default_section: str = "") -> list[dict]:
    """История/обществознание/биология 7–9: вопросы (ul.rus2 или p.text) + «Ответ:»."""
    section = default_section
    tasks: list[dict] = []
    q: list[str] = []
    a: list[str] = []
    after_marker = False

    def flush() -> None:
        nonlocal q, a, after_marker
        if q and a:
            tasks.append({
                "number": f"{page}.{len(tasks) + 1}",
                "section": section,
                "condition": "\n".join(q),
                "solution": "\n".join(a),
                "answer": a[-1],
            })
        q, a, after_marker = [], [], False

    for kind, text, cls in _content_stream(soup):
        if kind == "h":
            section = _tidy_section(text)
            continue
        if kind == "q":
            flush()
            q = [text]
            continue
        if kind == "m":
            if q:
                after_marker = True
            continue
        if kind == "p":
            if not after_marker:
                q.append(text)
                continue
            if _is_question_class(cls) and a:
                # новый вопрос без ul-блока: «2. Чем отличается…?»
                flush()
                q = [text]
                continue
            a.append(text)
    flush()
    return tasks


def _panel_images(panel, base_url: str) -> list[str]:
    els = list(panel.descendants)
    marker = None
    for i, el in enumerate(els):
        if getattr(el, "name", None) == "b" and "otvet" in (el.get("class") or []):
            marker = i
            break
    if marker is None:
        return []
    out: list[str] = []
    for el in els[marker + 1:]:
        if getattr(el, "name", None) != "img":
            continue
        src = (el.get("src") or "").strip()
        if not src or src.startswith("data:") or src.lower().endswith(".svg"):
            continue
        if not (re.search(r"nomer", src, re.I)
                or el.find_parent("div", class_="img-wrapper-450")
                or el.find_parent("div", class_="sdvig")):
            continue
        out.append(urllib.parse.urljoin(base_url, src))
    return out


def parse_panel_tasks(soup: BeautifulSoup, number: str, base_url: str,
                      default_section: str = "", prefer_last: bool = True) -> list[dict]:
    """Алгебра Макарычева: вкладки-годы, решение — картинка после «Ответ:»."""
    root = _main_root(soup)
    if root is None:
        return []
    candidates: list[dict] = []
    # у части книг (например, Макарычев-9) вкладок div.panel нет — страница целиком
    for panel in (root.select("div.panel") or [root]):
        # картинки — до вызова _main_lines: она схлопывает ссылки вместе с <img> внутри
        images = _panel_images(panel, base_url)
        lines = _main_lines(soup, root=panel)
        idx = next((i for i, l in enumerate(lines) if NUMBER_RE.match(l)), None)
        if idx is None:
            continue
        cond: list[str] = []
        sol: list[str] = []
        mode = "cond"
        for line in lines[idx + 1:]:
            if _is_stop(line):
                break
            if _ANSWER_RE.match(line):
                mode = "sol"
                continue
            if NUMBER_RE.match(line):
                break
            if mode == "cond":
                cond.append(line)
            else:
                sol.append(line)
        if not cond or not (sol or images):
            continue
        task: dict = {
            "number": str(number),
            "section": "",
            "condition": "\n".join(cond),
            "solution": "\n".join(sol),
            "answer": sol[-1] if sol else "",
        }
        if images:
            task["images"] = images
        candidates.append(task)
    if not candidates:
        return []
    return [candidates[-1] if prefer_last else candidates[0]]


PARSERS = {
    "page": parse_page_tasks,
    "rubric": parse_rubric_tasks,
    "exercise": parse_exercise_tasks,
    "qa": parse_qa_tasks,
}


# --------------------------------------------------------------------------
# конфигурация учебников
# --------------------------------------------------------------------------

HEADERS = {
    "math": ("Виленкин Н.Я., Жохов В.И., Чесноков А.С., Шварцбурд С.И.", "2023–2026"),
    "algebra": ("Макарычев Ю.Н., Миндюк Н.Г., Нешков К.И.", "2019–2024"),
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

    # ---------------- 7–9 классы (добавлено в релизе 2.0) ----------------
    "baranov-7-1": {
        "subject": "russian", "textbook": "baranov-7-1", "part": 1,
        "author": "Баранов М.Т., Ладыженская Т.А., Тростенцова Л.А. и др.", "year": "2023",
        "index": "https://gdz-raketa.ru/russkiy-yazyk/7-klass/uchebnik-baranov/",
        "kind": "single", "section": "",
        "urls": [f"https://gdz-raketa.ru/russkiy-yazyk/7-klass/uchebnik-baranov/1-chast-nomer-{i}/"
                 for i in range(1, 391)],
    },
    "baranov-7-2": {
        "subject": "russian", "textbook": "baranov-7-2", "part": 2,
        "author": "Баранов М.Т., Ладыженская Т.А., Тростенцова Л.А. и др.", "year": "2023",
        "index": "https://gdz-raketa.ru/russkiy-yazyk/7-klass/uchebnik-baranov/",
        "kind": "single", "section": "",
        "urls": [f"https://gdz-raketa.ru/russkiy-yazyk/7-klass/uchebnik-baranov/2-chast-nomer-{i}/"
                 for i in range(391, 645)],
    },
    "barhudarov-8": {
        "subject": "russian", "textbook": "barhudarov-8",
        "author": "Бархударов С.Г., Крючков С.Е., Максимов Л.Ю. и др.", "year": "2023",
        "index": "https://gdz-raketa.ru/russkiy-yazyk/8-klass/uchebnik-barhudarov/",
        "kind": "single", "section": "",
        "link_pattern": r"/russkiy-yazyk/8-klass/uchebnik-barhudarov/upr-(\d+)/$",
    },
    "barhudarov-9": {
        "subject": "russian", "textbook": "barhudarov-9",
        "author": "Бархударов С.Г., Крючков С.Е., Максимов Л.Ю. и др.", "year": "2023",
        "index": "https://gdz-raketa.ru/russkiy-yazyk/9-klass/uchebnik-barhudarov/",
        "kind": "single", "section": "",
        "link_pattern": r"/russkiy-yazyk/9-klass/uchebnik-barhudarov/nomer-(\d+)/$",
    },
    "makarichev-7": {
        "subject": "algebra", "textbook": "makarichev-7",
        "index": "https://gdz-raketa.ru/algebra/7-klass/uchebnik-makarichev/",
        "kind": "panel", "section": "",
        "link_pattern": r"/algebra/7-klass/uchebnik-makarichev/nomer-(\d+)/$",
    },
    "makarichev-8": {
        "subject": "algebra", "textbook": "makarichev-8",
        "index": "https://gdz-raketa.ru/algebra/8-klass/uchebnik-makarichev/",
        "kind": "panel", "section": "",
        "link_pattern": r"/algebra/8-klass/uchebnik-makarichev/nomer-(\d+)/$",
    },
    "makarichev-9": {
        "subject": "algebra", "textbook": "makarichev-9",
        "index": "https://gdz-raketa.ru/algebra/9-klass/uchebnik-makarichev/",
        "kind": "panel", "section": "",
        "link_pattern": r"/algebra/9-klass/uchebnik-makarichev/nomer-(\d+)/$",
    },
    "vaulina-7": {
        "subject": "english", "textbook": "vaulina-7",
        "author": "Ваулина Ю.Е., Дули Д., Подоляко О.Е. и др.", "year": "2023",
        "index": "https://gdz-raketa.ru/english/7-klass/uchebnik-vaulina/",
        "kind": "page", "parsers": ["exercise"],
        "link_pattern": r"/english/7-klass/uchebnik-vaulina/stranitsa-(\d+)/$",
    },
    "vaulina-8": {
        "subject": "english", "textbook": "vaulina-8",
        "author": "Ваулина Ю.Е., Дули Д., Подоляко О.Е. и др.", "year": "2023",
        "index": "https://gdz-raketa.ru/english/8-klass/uchebnik-vaulina/",
        "kind": "page", "parsers": ["exercise"],
        "link_pattern": r"/english/8-klass/uchebnik-vaulina/stranitsa-(\d+)/$",
    },
    "pasechnik-7": {
        "subject": "biology", "textbook": "pasechnik-7",
        "index": "https://gdz-raketa.ru/biologiya/7-klass/pasechnik-uchebnik/",
        "kind": "page", "parsers": ["qa"],
        "link_pattern": r"/biologiya/7-klass/pasechnik-uchebnik/stranitsa-(\d+)/$",
    },
    "pasechnik-8": {
        "subject": "biology", "textbook": "pasechnik-8",
        "index": "https://gdz-raketa.ru/biologiya/8-klass/pasechnik-uchebnik/",
        "kind": "page", "parsers": ["qa"],
        "link_pattern": r"/biologiya/8-klass/pasechnik-uchebnik/stranitsa-(\d+)/$",
    },
    "pasechnik-9": {
        "subject": "biology", "textbook": "pasechnik-9",
        "index": "https://gdz-raketa.ru/biologiya/9-klass/pasechnik-uchebnik/",
        "kind": "page", "parsers": ["qa"],
        "link_pattern": r"/biologiya/9-klass/pasechnik-uchebnik/stranitsa-(\d+)/$",
    },
    "medinsky-7": {
        "subject": "history", "textbook": "medinsky-7",
        "index": "https://gdz-raketa.ru/istoriya/7-klass/uchebnik-medinskij/",
        "kind": "page", "parsers": ["qa"],
        "link_pattern": r"/istoriya/7-klass/uchebnik-medinskij/stranica-(\d+)/$",
    },
    "medinsky-8": {
        "subject": "history", "textbook": "medinsky-8",
        "index": "https://gdz-raketa.ru/istoriya/8-klass/uchebnik-medinskij/",
        "kind": "page", "parsers": ["qa"],
        "link_pattern": r"/istoriya/8-klass/uchebnik-medinskij/stranica-(\d+)/$",
    },
    "medinsky-9": {
        "subject": "history", "textbook": "medinsky-9",
        "index": "https://gdz-raketa.ru/istoriya/9-klass/uchebnik-medinskij/",
        "kind": "page", "parsers": ["qa"],
        "link_pattern": r"/istoriya/9-klass/uchebnik-medinskij/stranica-(\d+)/$",
    },
    "bogolyubov-7": {
        "subject": "social", "textbook": "bogolyubov-7",
        "index": "https://gdz-raketa.ru/obshhestvoznanie/7-klass/uchebnik-bogolubov/",
        "kind": "page", "parsers": ["qa"],
        "link_pattern": r"/obshhestvoznanie/7-klass/uchebnik-bogolubov/stranica-(\d+)/$",
    },
    "bogolyubov-8": {
        "subject": "social", "textbook": "bogolyubov-8",
        "index": "https://gdz-raketa.ru/obshhestvoznanie/8-klass/uchebnik-bogolubov/",
        "kind": "page", "parsers": ["qa"],
        "link_pattern": r"/obshhestvoznanie/8-klass/uchebnik-bogolubov/stranica-(\d+)/$",
    },
    "bogolyubov-9": {
        "subject": "social", "textbook": "bogolyubov-9",
        "index": "https://gdz-raketa.ru/obshhestvoznanie/9-klass/uchebnik-bogolubov/",
        "kind": "page", "parsers": ["qa"],
        "link_pattern": r"/obshhestvoznanie/9-klass/uchebnik-bogolubov/stranica-(\d+)/$",
    },
}


# --------------------------------------------------------------------------
# сборка книги
# --------------------------------------------------------------------------

def collect(book_id: str, limit: int | None = None, resume: bool = False) -> dict:
    cfg = BOOKS[book_id]
    subject = cfg["subject"]
    header_author, header_year = HEADERS[subject]
    author = cfg.get("author", header_author)
    year = cfg.get("year", header_year)
    single_like = cfg["kind"] in ("single", "panel")
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
        number = task.get("number")
        for i, prev in enumerate(tasks):
            if prev.get("number") == number:
                # страницы сайта иногда повторяют чужой номер — держим более полную версию
                size = lambda t: len(t.get("condition") or "") + len(t.get("solution") or "")
                if size(task) > size(prev):
                    tasks[i] = task
                skipped.append(url)
                print(f"  ! дубль номера {number} ({url}) — оставлена более полная версия")
                return False
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

    # цели сбора: (ключ для --resume, url)
    if cfg.get("link_pattern"):
        index_soup = fetch(cfg["index"])
        rx = re.compile(cfg["link_pattern"])
        found: dict[str, str] = {}
        for a in index_soup.find_all("a", href=True):
            href = urllib.parse.urljoin(cfg["index"], a["href"])
            m = rx.search(href)
            if m:
                found.setdefault(m.group(1), href)
        targets = [(n, found[n]) for n in sorted(found, key=_number_key)]
        print(f"  индексная страница: {len(targets)} ссылок")
    elif single_like:
        targets = [(_expected_number(url) or url, url) for url in cfg["urls"]]
    else:
        targets = [(str(p), cfg["page_pattern"].format(n=p)) for p in cfg["pages"]]
    total = len(targets)

    chain = cfg.get("parsers")
    if chain is None:
        chain = ["page", "rubric"] if cfg["kind"] == "rubric" else ["page"]

    try:
        for i, (key, url) in enumerate(targets, 1):
            if limit is not None and len(tasks) >= limit:
                break
            if resume and key:
                if single_like and key in existing_numbers:
                    skipped_existing += 1
                    continue
                if not single_like and key in existing_pages:
                    skipped_existing += 1
                    continue
            try:
                soup = ok_fetch(url)
            except SourcesBlocked:
                raise
            except Exception as err:
                fail(url, err)
                continue
            if cfg["kind"] == "panel":
                page_tasks = parse_panel_tasks(soup, key, cfg["index"],
                                               cfg.get("section", ""),
                                               cfg.get("prefer_panel", "last") == "last")
                for task in page_tasks:
                    if limit is not None and len(tasks) >= limit:
                        break
                    take(task, url)
                num = f"№{page_tasks[-1]['number']}" if page_tasks else "пропуск"
                print(f"  {len(tasks):4d} задач  {i}/{total}  {num:>9}")
                continue
            if cfg["kind"] == "single":
                task = parse_single_task(soup, key)
                take(task, url)
                num = f"№{task['number']}" if task else "пропуск"
                print(f"  {len(tasks):4d} задач  {i}/{total}  {num:>9}  "
                      f"{task['section'][:44] if task else ''}")
                continue
            page_tasks = []
            for pname in chain:
                page_tasks = PARSERS[pname](soup, key)
                if page_tasks:
                    break
            if not page_tasks:
                skipped.append(url)
                continue
            for task in page_tasks:
                if limit is not None and len(tasks) >= limit:
                    break
                take(task, url)
            first = page_tasks[0] if page_tasks else None
            label = f"стр. {key:>3}" if key.isdigit() else f"№{key}"
            print(f"  {len(tasks):4d} задач  {label} ({i}/{total})  на странице: "
                  f"{len(page_tasks)}  {first['section'][:36] if first else ''}")
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
