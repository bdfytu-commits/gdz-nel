#!/usr/bin/env python3
"""Пинг IndexNow (Яндекс/Bing) и отправка sitemap в Google Search Console.

IndexNow:
  * ключ лежит в корне сайта: /<KEY>.txt;
  * перед пингом скрипт проверяет, что файл реально отдаётся с продакшена;
  * отправляет все URL из sitemap.xml.

Google Search Console:
  * нужен GSC_ACCESS_TOKEN (OAuth access token с правами webmasters);
  * если токена нет — шаг честно пропускается, не имитируем успех.

Запуск:
    python3 scripts/ping_indexnow.py --dry-run
    python3 scripts/ping_indexnow.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://gdz-nel.pages.dev"
KEY = "20a796611b5e0341efdbc8906acad257"
KEY_FILE = ROOT / f"{KEY}.txt"
SITEMAP = ROOT / "sitemap.xml"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"


def sitemap_urls() -> list[str]:
    tree = ElementTree.parse(SITEMAP)
    urls: list[str] = []
    for node in tree.iter():
        if node.tag.endswith("loc") and node.text:
            url = node.text.strip()
            if url.startswith(SITE + "/"):
                urls.append(url)
    return sorted(set(urls))


def preflight() -> bool:
    key_location = f"{SITE}/{KEY}.txt"
    request = urllib.request.Request(
        key_location + "?ping=" + KEY[:8],
        headers={"User-Agent": "GdzNelIndexNow/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("ascii", "replace").strip()
    except Exception as error:  # noqa: BLE001
        print(f"key file недоступен: {key_location} ({error})")
        return False
    if body != KEY:
        print(f"key file содержит не тот ключ: {key_location}")
        return False
    print("key file доступен:", key_location)
    return True


def ping_indexnow(urls: list[str]) -> bool:
    payload = {
        "host": urllib.parse.urlparse(SITE).netloc,
        "key": KEY,
        "keyLocation": f"{SITE}/{KEY}.txt",
        "urlList": urls,
    }
    request = urllib.request.Request(
        INDEXNOW_ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "GdzNelIndexNow/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read().decode("utf-8", "replace")
            print(f"IndexNow: HTTP {response.status}, URL: {len(urls)}")
            if body:
                print(body[:500])
            return response.status in (200, 202)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        print(f"IndexNow: HTTP {error.code} {body[:500]}")
        return False
    except Exception as error:  # noqa: BLE001
        print(f"IndexNow: ошибка {error}")
        return False


def submit_gsc() -> None:
    token = os.environ.get("GSC_ACCESS_TOKEN", "").strip()
    if not token:
        print("Google Search Console: пропущено, нет GSC_ACCESS_TOKEN")
        return
    site = os.environ.get("GSC_SITE_URL", f"{SITE}/").strip()
    sitemap = f"{SITE}/sitemap.xml"
    url = (
        "https://www.googleapis.com/webmasters/v3/sites/"
        + urllib.parse.quote(site, safe="")
        + "/sitemaps/"
        + urllib.parse.quote(sitemap, safe="")
    )
    request = urllib.request.Request(
        url,
        data=b"",
        headers={"Authorization": f"Bearer {token}"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            print(f"Google Search Console: HTTP {response.status}")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        print(f"Google Search Console: HTTP {error.code} {body[:300]}")
    except Exception as error:  # noqa: BLE001
        print(f"Google Search Console: ошибка {error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    if not KEY_FILE.exists() or KEY_FILE.read_text(encoding="ascii").strip() != KEY:
        print(f"нет локального key file: {KEY_FILE}")
        return 2
    urls = sitemap_urls()
    if not urls:
        print("в sitemap.xml нет URL продакшена")
        return 2
    print("URL в sitemap:", len(urls))
    if args.dry_run:
        print("dry-run: пинг не отправляю")
        return 0
    if not args.skip_preflight and not preflight():
        print("сначала задеплойте key file на прод")
        return 2
    ok = ping_indexnow(urls)
    submit_gsc()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
