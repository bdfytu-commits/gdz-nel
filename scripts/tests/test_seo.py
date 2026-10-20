#!/usr/bin/env python3
"""SEO-аудит: canonical/OG/twitter/JSON-LD/sitemap/robots.

Без playwright и без сети наружу — работает по локальному серверу.

    uv run python -m http.server 8000
    python3 scripts/tests/test_seo.py

Домен берётся из canonical главной страницы, поэтому тест одинаково годится
для gdz-nel.pages.dev и для будущего gdz-nel.is-a.dev.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent.parent
BASE = os.environ.get("GDZ_BASE", "http://127.0.0.1:8000").rstrip("/")

# страницы, которые должны индексироваться: полный набор тегов
PUBLIC = [
    "index.html", "about.html", "contact.html", "privacy.html", "terms.html",
    "disclaimer.html", "premium.html", "cheatsheets.html", "photo.html",
    "search.html", "app/index.html",
]
# служебные: canonical и description есть, OG не обязателен
SOFT = ["auth.html", "profile.html"]
JSONLD_REQUIRED = {"index.html", "app/index.html"}

ERRORS: list[str] = []


def fail(where: str, msg: str) -> None:
    ERRORS.append(f"{where}: {msg}")


def fetch(path: str) -> str:
    with urllib.request.urlopen(BASE + "/" + path.lstrip("/"), timeout=20) as resp:
        return resp.read().decode("utf-8", "replace")


def attrs_of(tag: str) -> dict[str, str]:
    return {k.lower(): v for k, v in re.findall(r'([a-zA-Z:_-]+)="([^"]*)"', tag)}


def metas(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag in re.findall(r"<meta\b[^>]*>", html, re.I):
        a = attrs_of(tag)
        key = a.get("property") or a.get("name")
        if key:
            out.setdefault(key.lower(), a.get("content", ""))
    return out


def links(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag in re.findall(r"<link\b[^>]*>", html, re.I):
        a = attrs_of(tag)
        rel = a.get("rel", "").lower()
        href = a.get("href", "")
        if rel == "canonical" and href:
            out["canonical"] = href
    return out


def ld_json(html: str, where: str = "JSON-LD") -> list[dict]:
    blocks = re.findall(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.I | re.S)
    out = []
    for block in blocks:
        try:
            out.append(json.loads(block))
        except json.JSONDecodeError as exc:
            fail(where, f"битый JSON-LD: {exc}")
    return out


def main() -> int:
    index_html = fetch("/")
    canonical = links(index_html).get("canonical", "")
    if not canonical:
        print("нет canonical на главной — не могу определить домен")
        return 2
    host = urlparse(canonical).netloc
    if not host:
        print("canonical без хоста:", canonical)
        return 2
    print("домен:", host)

    # --- главная: канонические теги ---
    m = metas(index_html)
    if m.get("description") and len(m["description"]) < 40:
        fail("index.html", "description короче 40 символов")
    if not re.search(r"<html[^>]+lang=\"ru\"", index_html, re.I):
        fail("index.html", "нет lang=ru")
    if 'name="viewport"' not in index_html:
        fail("index.html", "нет viewport")

    # --- все публичные страницы ---
    for name in PUBLIC + SOFT:
        try:
            html = fetch(name)
        except Exception as exc:  # noqa: BLE001
            fail(name, f"не открывается: {exc}")
            continue
        m = metas(html)
        ln = links(html)
        title = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
        if not title or not title.group(1).strip():
            fail(name, "пустой title")
        if not m.get("description"):
            fail(name, "нет description")
        canon = ln.get("canonical", "")
        if not canon:
            fail(name, "нет canonical")
        elif urlparse(canon).netloc != host:
            fail(name, f"canonical на чужом домене: {canon}")
        if name in PUBLIC:
            for key in ("og:title", "og:description", "og:url", "og:image", "twitter:card"):
                if not m.get(key):
                    fail(name, f"нет {key}")
            og_url = m.get("og:url", "")
            if og_url and urlparse(og_url).netloc != host:
                fail(name, f"og:url на чужом домене: {og_url}")
            og_image = m.get("og:image", "")
            if og_image:
                if urlparse(og_image).netloc != host:
                    fail(name, f"og:image на чужом домене: {og_image}")
                else:
                    local = ROOT / urlparse(og_image).path.lstrip("/")
                    if not local.exists():
                        fail(name, f"og:image не существует: {og_image}")
        if name in JSONLD_REQUIRED:
            blocks = ld_json(html, name)
            if not blocks:
                fail(name, "нет JSON-LD")
            for block in blocks:
                if "@context" not in block or "@type" not in block:
                    fail(name, "JSON-LD без @context/@type")

    # --- sitemap ---
    try:
        sm = fetch("/sitemap.xml")
    except Exception as exc:  # noqa: BLE001
        fail("sitemap.xml", f"не открывается: {exc}")
        sm = ""
    locs = re.findall(r"<loc>([^<]+)</loc>", sm)
    if not locs:
        fail("sitemap.xml", "нет <loc>")
    sitemap_paths = set()
    for loc in locs:
        u = urlparse(loc)
        if u.netloc != host:
            fail("sitemap.xml", f"чужой домен: {loc}")
        path = u.path or "/"
        sitemap_paths.add(path)
        local = ROOT / (path.lstrip("/") or "index.html")
        if path.endswith("/"):
            local = ROOT / path.lstrip("/") / "index.html"
        if not local.exists():
            fail("sitemap.xml", f"нет файла для {path}")
    for must in ("/", "/app/", "/premium.html", "/privacy.html"):
        if must not in sitemap_paths:
            fail("sitemap.xml", f"нет обязательной страницы {must}")

    # --- robots ---
    try:
        rb = fetch("/robots.txt")
    except Exception as exc:  # noqa: BLE001
        fail("robots.txt", f"не открывается: {exc}")
        rb = ""
    if f"Sitemap: https://{host}/sitemap.xml" not in rb:
        fail("robots.txt", "Sitemap не совпадает с canonical-доменом")
    for rule in ("Disallow: /admin/", "Disallow: /profile.html"):
        if rule not in rb:
            fail("robots.txt", f"нет правила {rule}")

    print(f"проверено страниц: {len(PUBLIC) + len(SOFT)}, URL в sitemap: {len(locs)}")
    if ERRORS:
        print("\nошибки:")
        for e in ERRORS:
            print(" -", e)
        return 1
    print("SEO: всё чисто")
    return 0


if __name__ == "__main__":
    sys.exit(main())
