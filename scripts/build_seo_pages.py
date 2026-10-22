#!/usr/bin/env python3
"""Генерирует статические SEO-страницы под длинные запросы.

10 популярных учебников × 5 заданий = 50 страниц. Каждая страница:
условие, решение, ответ, ссылка в приложение, canonical, OG-теги,
JSON-LD и своя OG-картинка 1200×630 (Pillow).

Запуск:
    python3 scripts/build_seo_pages.py
    python3 scripts/build_seo_pages.py --dry
"""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
SEO = ROOT / "seo"
OG_DIR = SEO / "og"
SITEMAP = ROOT / "sitemap.xml"
SITE = "https://gdz-nel.pages.dev"

SUBJECT_TITLES = {
    "math": "Математика",
    "russian": "Русский язык",
    "english": "Английский язык",
    "literature": "Литература",
    "algebra": "Алгебра",
    "geometry": "Геометрия",
    "physics": "Физика",
    "chemistry": "Химия",
    "biology": "Биология",
    "history": "История",
    "social": "Обществознание",
    "geo": "География",
    "informatics": "Информатика",
    "world": "Окружающий мир",
    "history-maps": "История (контурные карты)",
}

BOOKS = [
    {"id": "vilenkin-6-1", "file": "math/vilenkin-6-1.json", "grade": 6, "subject": "math",
     "query": "виленкин 6 класс", "author": "Виленкин"},
    {"id": "vilenkin-6-2", "file": "math/vilenkin-6-2.json", "grade": 6, "subject": "math",
     "query": "виленкин 6 класс часть 2", "author": "Виленкин"},
    {"id": "abramov-6-519", "file": "history/abramov-6-519.json", "grade": 6, "subject": "history",
     "query": "абрамов 6 класс история", "author": "Абрамов"},
    {"id": "vigasin-5-938", "file": "history/vigasin-5-938.json", "grade": 5, "subject": "history",
     "query": "вигасин 5 класс история", "author": "Вигасин"},
    {"id": "kanakina-4-1", "file": "russian/kanakina-4-1.json", "grade": 4, "subject": "russian",
     "query": "канакина 4 класс", "author": "Канакина"},
    {"id": "peryshkin-7-609", "file": "physics/peryshkin-7-609.json", "grade": 7, "subject": "physics",
     "query": "перышкин 7 класс физика", "author": "Перышкин"},
    {"id": "makarichev-8", "file": "algebra/makarichev-8.json", "grade": 8, "subject": "algebra",
     "query": "макарычев 8 класс алгебра", "author": "Макарычев"},
    {"id": "afanaseva-11", "file": "english/afanaseva-11.json", "grade": 11, "subject": "english",
     "query": "афанасьева 11 класс", "author": "Афанасьева"},
    {"id": "bogolyubov-11", "file": "social/bogolyubov-11.json", "grade": 11, "subject": "social",
     "query": "боголюбов 11 класс общество", "author": "Боголюбов"},
    {"id": "medinskiy-11", "file": "history/medinskiy-11.json", "grade": 11, "subject": "history",
     "query": "мединский 11 класс история", "author": "Мединский"},
]

PER_BOOK = 5
FONT_BOLD = "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/TTF/DejaVuSans.ttf"


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def slugify(value: str) -> str:
    value = value.lower().replace("ё", "e")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def pick_tasks(tasks: list[dict]) -> list[dict]:
    usable = [
        t for t in tasks
        if re.fullmatch(r"\d+(?:\.\d+)*(?:-\d+)?", str(t.get("number", "")))
        and len(str(t.get("condition", "")).strip()) >= 40
        and len(str(t.get("solution", "")).strip()) >= 20
    ]
    if len(usable) <= PER_BOOK:
        return usable
    step = len(usable) / PER_BOOK
    return [usable[int(i * step)] for i in range(PER_BOOK)]


def wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = (line + " " + word).strip()
        if draw.textlength(candidate, font=font) <= width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def make_og(path: Path, title: str, subtitle: str) -> None:
    img = Image.new("RGB", (1200, 630), "#063c3c")
    draw = ImageDraw.Draw(img)
    for y in range(630):
        k = y / 630
        draw.line((0, y, 1200, y), fill=(int(6 + 10 * k), int(60 + 70 * k), int(60 + 60 * k)))
    draw.rounded_rectangle((60, 60, 1140, 570), radius=36, outline=(255, 255, 255, 60), width=2)
    bold = ImageFont.truetype(FONT_BOLD, 34)
    big = ImageFont.truetype(FONT_BOLD, 64)
    small = ImageFont.truetype(FONT_REG, 28)
    draw.text((100, 100), "ГДЗ НЭЛ", font=bold, fill="#7ff0e0")
    y = 210
    for line in wrap(draw, title, big, 1000)[:3]:
        draw.text((100, y), line, font=big, fill="#ffffff")
        y += 82
    y = max(y + 20, 430)
    for line in wrap(draw, subtitle, small, 1000)[:2]:
        draw.text((100, y), line, font=small, fill="#cfeeea")
        y += 40
    draw.text((100, 520), "gdz-nel.pages.dev · готовые решения без воды", font=small, fill="#9fd8d2")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)


PAGE_CSS = """
:root{--brand:#0d7c74;--ink:#102a2a;--muted:#5d7373;--line:#dbe7e5;--bg:#f6fbfa}
*{box-sizing:border-box}body{margin:0;font-family:'Segoe UI',Roboto,Arial,sans-serif;background:var(--bg);color:var(--ink);line-height:1.6}
a{color:var(--brand)}header{background:#fff;border-bottom:1px solid var(--line)}
.wrap{max-width:860px;margin:0 auto;padding:0 20px}
.top{display:flex;align-items:center;gap:12px;min-height:64px}.logo{font-weight:800;font-size:20px;text-decoration:none;color:var(--brand)}
.top nav{margin-left:auto;display:flex;gap:16px;font-size:14px}
.crumbs{font-size:13px;color:var(--muted);margin:22px 0 8px}.crumbs a{color:var(--muted)}
h1{font-size:30px;line-height:1.25;margin:6px 0 18px}
.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:22px;margin:16px 0}
.card h2{font-size:16px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:0 0 10px}
.text{white-space:pre-line}
.answer{border-left:4px solid var(--brand);background:#effaf8;padding:14px 16px;border-radius:10px;white-space:pre-line}
.cta{display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between;background:#063c3c;color:#fff;border-radius:16px;padding:22px;margin:24px 0}
.cta p{margin:0;color:#cfeeea}.btn{display:inline-block;background:#25c2b3;color:#042a2a;font-weight:700;padding:12px 20px;border-radius:12px;text-decoration:none}
.related{display:flex;flex-wrap:wrap;gap:10px;padding:0;list-style:none}.related a{display:inline-block;border:1px solid var(--line);background:#fff;border-radius:10px;padding:8px 12px;text-decoration:none;font-size:14px}
footer{border-top:1px solid var(--line);margin-top:36px;padding:24px 0;color:var(--muted);font-size:13px}
@media(max-width:600px){h1{font-size:24px}.top nav{display:none}.cta{padding:18px}}
"""


def page_html(book: dict, task: dict, slug: str, siblings: list[tuple[str, str]]) -> str:
    subject = SUBJECT_TITLES.get(book["subject"], book["subject"])
    number = str(task["number"])
    query = book["query"]
    title = f"{query.capitalize()} номер {number} — решение и ответ | ГДЗ НЭЛ"
    description = (
        f"Готовое решение задания {number} по предмету «{subject}» для {book['grade']} класса: "
        "условие, шаги решения и ответ. Открывайте на ГДЗ НЭЛ."
    )
    canonical = f"{SITE}/seo/{slug}/"
    image = f"{SITE}/seo/og/{slug}.png"
    app_url = (
        f"{SITE}/app/index.html#/{book['grade']}/{book['subject']}/"
        f"{book['id']}/{task['number']}"
    )
    related = "".join(
        f'<li><a href="/seo/{s}/">{esc(label)}</a></li>' for s, label in siblings
    )
    ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "image": image,
        "mainEntityOfPage": canonical,
        "author": {"@type": "Organization", "name": "ГДЗ НЭЛ"},
        "publisher": {"@type": "Organization", "name": "ГДЗ НЭЛ"},
        "about": {"@type": "Thing", "name": f"{subject}, {book['grade']} класс, задание {number}"},
    }
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">
  <link rel="canonical" href="{canonical}">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="ГДЗ НЭЛ">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:image" content="{image}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:url" content="{canonical}">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="icon" href="/favicon.ico">
  <link rel="stylesheet" href="/assets/style.css">
  <style>{PAGE_CSS}</style>
  <script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head>
<body>
<header><div class="wrap top">
  <a class="logo" href="/">ГДЗ НЭЛ</a>
  <nav><a href="/app/">Приложение</a><a href="/search.html">Поиск</a><a href="/honor.html">Доска почёта</a></nav>
</div></header>
<main class="wrap">
  <nav class="crumbs" aria-label="Хлебные крошки">
    <a href="/">Главная</a> / <a href="/app/">ГДЗ</a> / <a href="/app/index.html#/{book['grade']}/{book['subject']}">{book['grade']} класс</a> /
    <a href="/app/index.html#/{book['grade']}/{book['subject']}/{book['id']}">{esc(book['author'])}</a> / <span>№{esc(number)}</span>
  </nav>
  <h1>{esc(book['author'])}. {esc(subject)}, {book['grade']} класс, номер {esc(number)}</h1>
  <section class="card"><h2>Условие</h2><div class="text">{esc(task.get('condition') or 'Условие смотрите в учебнике.')}</div></section>
  <section class="card"><h2>Решение</h2><div class="text">{esc(task.get('solution') or 'Пошаговое решение смотрите в приложении.')}</div></section>
  <section class="card"><h2>Ответ</h2><div class="answer">{esc(task.get('answer') or 'Смотрите решение.')}</div></section>
  <div class="cta">
    <p>Открой задание в приложении: все номера подряд, поиск по тексту, избранное и офлайн-режим.</p>
    <a class="btn" href="{app_url}">Открыть решение</a>
  </div>
  <section class="card"><h2>Ещё задания этого учебника</h2><ul class="related">{related}</ul></section>
</main>
<footer><div class="wrap">
  ГДЗ НЭЛ — готовые домашние задания для 1–11 классов. Материалы для самопроверки.
  <a href="/">На главную</a> · <a href="/seo/">Все разборы</a>
</div></footer>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    pages: list[dict] = []
    for book in BOOKS:
        path = DATA / book["file"]
        if not path.exists():
            print(f"!! нет файла {path}", flush=True)
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        tasks = pick_tasks(doc.get("tasks", []))
        for task in tasks:
            slug = slugify(f"{book['id']} {task['number']}")
            pages.append({"book": book, "task": task, "slug": slug})

    if not pages:
        print("нечего генерировать")
        return 1

    by_book: dict[str, list[dict]] = {}
    for page in pages:
        by_book.setdefault(page["book"]["id"], []).append(page)

    for page in pages:
        siblings = [
            (p["slug"], f"№{p['task']['number']}")
            for p in by_book[page["book"]["id"]] if p["slug"] != page["slug"]
        ]
        if not args.dry:
            out = SEO / page["slug"] / "index.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(page_html(page["book"], page["task"], page["slug"], siblings), encoding="utf-8")
            subject = SUBJECT_TITLES.get(page["book"]["subject"], page["book"]["subject"])
            make_og(
                OG_DIR / f"{page['slug']}.png",
                f"{page['book']['author']}, {page['book']['grade']} класс, №{page['task']['number']}",
                f"{subject} · условие, решение и ответ · ГДЗ НЭЛ",
            )

    index_html = ['<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">',
                  '<meta name="viewport" content="width=device-width, initial-scale=1">',
                  '<title>Разборы заданий — ГДЗ НЭЛ</title>',
                  '<meta name="description" content="50 разборов популярных заданий: условие, решение и ответ. Математика, русский, английский, история и общество.">',
                  '<link rel="canonical" href="' + SITE + '/seo/">',
                  '<link rel="icon" href="/favicon.ico"><link rel="stylesheet" href="/assets/style.css">',
                  f'<style>{PAGE_CSS}</style></head><body><header><div class="wrap top">'
                  '<a class="logo" href="/">ГДЗ НЭЛ</a><nav><a href="/app/">Приложение</a>'
                  '<a href="/search.html">Поиск</a></nav></div></header><main class="wrap">'
                  '<nav class="crumbs"><a href="/">Главная</a> / <span>Разборы</span></nav>'
                  '<h1>Разборы заданий</h1><p>Условие, решение и ответ для популярных номеров. '
                  'Полная книга — в приложении.</p>']
    for book in BOOKS:
        items = by_book.get(book["id"], [])
        if not items:
            continue
        index_html.append(
            f'<section class="card"><h2>{esc(book["author"])}, {book["grade"]} класс</h2><ul class="related">'
        )
        for page in items:
            index_html.append(f'<li><a href="/seo/{page["slug"]}/">№{esc(page["task"]["number"])}</a></li>')
        index_html.append("</ul></section>")
    index_html.append('</main><footer><div class="wrap">ГДЗ НЭЛ · <a href="/">На главную</a></div></footer></body></html>')

    if not args.dry:
        (SEO / "index.html").write_text("".join(index_html), encoding="utf-8")

        block = ["  <!-- seo-pages:start -->"]
        for page in pages:
            block.append(
                "  <url>\n"
                f"    <loc>{SITE}/seo/{page['slug']}/</loc>\n"
                f"    <lastmod>{date.today().isoformat()}</lastmod>\n"
                "    <changefreq>monthly</changefreq>\n"
                "    <priority>0.6</priority>\n"
                "  </url>"
            )
        block.append("  <!-- seo-pages:end -->")
        xml = SITEMAP.read_text(encoding="utf-8")
        xml = re.sub(r"  <!-- seo-pages:start -->.*?  <!-- seo-pages:end -->\n?", "", xml, flags=re.S)
        xml = xml.replace("</urlset>", "\n".join(block) + "\n</urlset>")
        SITEMAP.write_text(xml, encoding="utf-8")

    print(f"страниц: {len(pages)}, учебников: {len(by_book)}")
    print("пример:", pages[0]["slug"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
