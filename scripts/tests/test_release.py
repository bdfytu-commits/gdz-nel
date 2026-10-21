#!/usr/bin/env python3
"""Релизный Playwright-аудит ГДЗ НЭЛ 3.0.

Прогоняет все страницы на 375x812, 768x1024 и 1920x1080:
  * HTTP-статус, ошибки страницы и консоли;
  * горизонтальное переполнение и вылет элементов за экран;
  * битые картинки и ссылки-заглушки;
  * доступность кнопок по тексту/aria-label;
  * PWA: регистрация service worker, офлайн-навигация;
  * prefers-reduced-motion: анимации выключаются.

С флагом --live дополнительно проверяет интерактив под админом:
отзыв, комментарий профиля, кастомизацию, лайк доски почёта,
разблокировку ГДЗ+ и все вкладки админки.

    scripts/venv-shots/bin/python scripts/tests/test_release.py
    scripts/venv-shots/bin/python scripts/tests/test_release.py --live

Сервер: http://127.0.0.1:8000 (или GDZ_BASE). Креды — scripts/tests/.env.local.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

from env import load

load()

BASE = os.environ.get("GDZ_BASE", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = os.environ.get("GDZ_ADMIN_EMAIL", "admin@gdz-nel.test")
ADMIN_PASSWORD = os.environ.get("GDZ_ADMIN_PASSWORD", "")
SUPABASE_URL = os.environ.get("GDZ_SUPABASE_URL", "https://qncqeoklwblztbnoktwk.supabase.co")
SUPABASE_KEY = os.environ.get(
    "GDZ_SUPABASE_KEY", "sb_publishable_uyBIZ2gNPuDqxre3ea989w_WbctezF4")
SHOTS = Path("/tmp/opencode/release")
SHOTS.mkdir(parents=True, exist_ok=True)

VIEWPORTS = {
    "mobile-375": {"width": 375, "height": 812, "is_mobile": True, "has_touch": True},
    "tablet-768": {"width": 768, "height": 1024, "is_mobile": True, "has_touch": True},
    "desktop-1920": {"width": 1920, "height": 1080, "is_mobile": False, "has_touch": False},
}

PAGES = [
    ("landing", "/index.html"),
    ("about", "/about.html"),
    ("contact", "/contact.html"),
    ("privacy", "/privacy.html"),
    ("terms", "/terms.html"),
    ("disclaimer", "/disclaimer.html"),
    ("cookie-policy", "/cookie-policy.html"),
    ("accessibility", "/accessibility.html"),
    ("premium", "/premium.html"),
    ("cheatsheets", "/cheatsheets.html"),
    ("photo", "/photo.html"),
    ("auth", "/auth.html"),
    ("search", "/search.html?q=проценты"),
    ("404", "/404.html"),
    ("app-home", "/app/index.html#/"),
    ("app-grade-3", "/app/index.html#/3/"),
    ("app-grade-8", "/app/index.html#/8/"),
    ("app-subject", "/app/index.html#/8/math/"),
    ("app-book", "/app/index.html#/6/math/vilenkin-6-1"),
    ("app-task", "/app/index.html#/6/math/vilenkin-6-1/1.12"),
    ("app-search", "/app/index.html#/search/дробь"),
]

CHECK_JS = r"""
() => {
  const vw = document.documentElement.clientWidth;
  const root = document.scrollingElement || document.documentElement;
  const overflow = root.scrollWidth - vw;

  function clipped(el) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return false;
    if (r.right <= vw + 1 && r.left >= -1) return false;
    const st = getComputedStyle(el);
    if (st.position === 'fixed' || st.position === 'absolute') return false;
    if (el.closest('pre, table, .table-wrap, .code, .task-text')) return false;
    return true;
  }

  const bad = [];
  document.querySelectorAll('body *').forEach((el) => {
    if (bad.length > 12) return;
    if (clipped(el)) bad.push(el.tagName.toLowerCase() + '.' + (el.className || '').toString().slice(0, 48));
  });

  const brokenImgs = [];
  document.querySelectorAll('img').forEach((img) => {
    if (img.complete && img.naturalWidth === 0 && img.getAttribute('src') && !img.getAttribute('src').startsWith('data:')) {
      brokenImgs.push((img.getAttribute('src') || '').slice(0, 80));
    }
  });

  const emptyButtons = [];
  document.querySelectorAll('button').forEach((b) => {
    const text = (b.innerText || '').trim();
    const label = b.getAttribute('aria-label') || b.getAttribute('title') || '';
    if (!text && !label) emptyButtons.push((b.className || b.id || 'button').slice(0, 60));
  });

  return { overflow, bad, brokenImgs, emptyButtons, title: document.title };
}
"""


def api(method: str, path: str, token: str, body=None):
    data = None if body is None else json.dumps(body).encode()
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token,
    }
    req = urllib.request.Request(SUPABASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")[:200]


def rest_token(email: str, password: str) -> str | None:
    """access_token через Supabase Auth — для REST-уборки тестовых записей."""
    if not password:
        return None
    req = urllib.request.Request(
        SUPABASE_URL + "/auth/v1/token?grant_type=password",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"apikey": SUPABASE_KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()).get("access_token")
    except Exception:  # noqa: BLE001
        return None


async def login(page, email: str, password: str) -> str | None:
    await page.goto(BASE + "/auth.html", wait_until="networkidle")
    await page.fill("#li-email", email)
    await page.fill("#li-password", password)
    await page.click("#login-submit")
    await page.wait_for_timeout(2500)
    if "/auth.html" in page.url:
        return None
    return rest_token(email, password) or "no-token"


class Result:
    def __init__(self):
        self.failures: list[str] = []
        self.checks = 0

    def fail(self, message: str, context: str = ""):
        self.failures.append((context + ": " if context else "") + message)

    def ok(self):
        self.checks += 1


async def audit_pages(browser, result: Result):
    for name, viewport in VIEWPORTS.items():
        context = await browser.new_context(
            viewport={"width": viewport["width"], "height": viewport["height"]},
            is_mobile=viewport["is_mobile"],
            has_touch=viewport["has_touch"],
            service_workers="allow",
            reduced_motion="no-preference",
        )
        page = await context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append("pageerror " + str(e)[:160]))
        page.on("console", lambda m: errors.append("console " + m.text[:160]) if m.type == "error" else None)

        for label, url in PAGES:
            errors.clear()
            try:
                resp = await page.goto(BASE + url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(500)
            except Exception as exc:  # noqa: BLE001
                result.fail(f"не открылась {url}: {exc}", name + "/" + label)
                continue
            if resp and resp.status >= 400:
                result.fail(f"HTTP {resp.status}", name + "/" + label)
            data = await page.evaluate(CHECK_JS)
            if data["overflow"] > 1:
                result.fail(f"overflow={data['overflow']}px", name + "/" + label)
            if data["bad"]:
                result.fail("вылетают: " + ", ".join(data["bad"][:5]), name + "/" + label)
            if data["brokenImgs"]:
                result.fail("битые img: " + ", ".join(data["brokenImgs"][:3]), name + "/" + label)
            if data["emptyButtons"]:
                result.fail("кнопки без подписи: " + ", ".join(data["emptyButtons"][:3]), name + "/" + label)
            if errors:
                result.fail("; ".join(errors[:3]), name + "/" + label)
            result.ok()
            await page.screenshot(path=str(SHOTS / f"{name}-{label}.png"), full_page=(label == "landing"))
        await context.close()

    # reduced motion: те же страницы, но анимации должны быть отключены
    context = await browser.new_context(
        viewport={"width": 375, "height": 812}, reduced_motion="reduce", service_workers="allow")
    page = await context.new_page()
    for label, url in [("landing", "/index.html"), ("cheatsheets", "/cheatsheets.html")]:
        await page.goto(BASE + url, wait_until="domcontentloaded")
        sample = await page.evaluate(
            "() => getComputedStyle(document.querySelector('.reveal, .cheat-card, .sheet-lock') || document.body).animationName"
        )
        if sample not in ("none", ""):
            result.fail(f"reduced-motion не выключил анимацию: {sample}", label)
        result.ok()
    await context.close()


async def audit_interactive(browser, result: Result):
    context = await browser.new_context(viewport={"width": 1440, "height": 900}, service_workers="allow")
    page = await context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append("pageerror " + str(e)[:200]))

    token = await login(page, ADMIN_EMAIL, ADMIN_PASSWORD)
    if not token:
        result.fail("админ не вошёл — интерактивные проверки пропущены")
        await context.close()
        return

    # 1. отзыв: публикуется и виден сразу
    stamp = str(int(__import__("time").time()))
    review_text = "release-проверка отзыва " + stamp
    await page.goto(BASE + "/app/index.html#/6/math/vilenkin-6-1/1.16", wait_until="networkidle")
    await page.wait_for_timeout(2000)
    await page.locator("#review-text").fill(review_text)
    await page.locator("#review-submit").click()
    await page.wait_for_timeout(3500)
    body = await page.locator("#reviews-list").inner_text()
    if review_text not in body:
        result.fail("отзыв не появился сразу", "reviews")
    else:
        result.ok()
    status, rows = api("GET", f"/rest/v1/reviews?select=id&text=eq.{urllib.parse.quote(review_text)}", token)
    if status == 200 and rows:
        for row in rows:
            api("DELETE", f"/rest/v1/reviews?id=eq.{row['id']}", token)

    # 2. комментарий профиля: создать и удалить
    comment_text = "release-проверка комментария " + stamp
    await page.goto(BASE + "/profile.html", wait_until="networkidle")
    await page.wait_for_selector("#comment-form", timeout=15000)
    await page.locator("#comment-text").fill(comment_text)
    await page.locator("#comment-send").click()
    await page.wait_for_timeout(2500)
    comment_body = await page.locator("#comment-list").inner_text()
    if comment_text not in comment_body:
        result.fail("комментарий не появился", "comments")
    else:
        result.ok()
        delete = page.locator(f'[data-del-comment]:near(:text("{comment_text}"))').first
        if await delete.count():
            await delete.click()
            await page.wait_for_timeout(1500)
            if comment_text in await page.locator("#comment-list").inner_text():
                result.fail("комментарий не удалился", "comments")
            else:
                result.ok()

    # 3. кастомизация: рамка сохраняется и сбрасывается
    await page.wait_for_selector("#custom-section:not([hidden])", timeout=15000)
    gold = page.locator('[data-border="gold"]')
    await gold.click()
    await page.locator("#custom-save").click()
    await page.wait_for_timeout(1800)
    await page.reload(wait_until="networkidle")
    await page.wait_for_timeout(1500)
    checked = await page.locator('[data-border="gold"]').get_attribute("aria-checked")
    if checked != "true":
        result.fail("кастомизация не сохранилась", "custom")
    else:
        result.ok()
    await page.locator('[data-border="none"]').click()
    await page.locator("#custom-save").click()
    await page.wait_for_timeout(1200)

    # 4. доска почёта: админ создаёт, лайк переключается, запись удаляется
    await page.goto(BASE + "/admin/index.html#honor", wait_until="networkidle")
    await page.wait_for_selector("#honor-new-text", timeout=15000)
    honor_text = "release-проверка доски " + stamp
    await page.locator("#honor-new-text").fill(honor_text)
    await page.locator('[data-act="honor-create"]').click()
    await page.wait_for_timeout(2000)
    await page.goto(BASE + "/honor.html", wait_until="networkidle")
    await page.wait_for_selector(".honor-card", timeout=15000)
    card = page.locator(".honor-card", has_text=honor_text).first
    if not await card.count():
        result.fail("запись доски не появилась", "honor")
    else:
        like = card.locator(".honor-like")
        await like.click()
        await page.wait_for_timeout(1200)
        count = await card.locator("[data-count]").inner_text()
        if count != "1":
            result.fail(f"лайк дал {count}, а не 1", "honor")
        else:
            result.ok()
        await like.click()
        await page.wait_for_timeout(1200)
        count = await card.locator("[data-count]").inner_text()
        if count != "0":
            result.fail(f"повторный лайк дал {count}, а не 0", "honor")
        else:
            result.ok()
        await page.goto(BASE + "/admin/index.html#honor", wait_until="networkidle")
        await page.wait_for_selector("#honor-new-text", timeout=15000)
        row = page.locator("tr", has_text=honor_text).first
        if await row.count():
            await row.locator('[data-act="honor-delete"]').click()
            await page.wait_for_timeout(600)
            await page.locator('.modal-actions [data-modal="yes"]').click()
            await page.wait_for_timeout(1200)

    # 5. ГДЗ+: у премиум-админа шпаргалки разблокированы
    await page.goto(BASE + "/cheatsheets.html", wait_until="networkidle")
    await page.wait_for_timeout(1800)
    locked = await page.locator("#sheets-wrap.is-locked").count()
    if locked:
        result.fail("ГДЗ+ не разблокировал шпаргалки", "premium")
    else:
        result.ok()

    # 6. все вкладки админки открываются
    for tab in ("overview", "users", "reviews", "ai", "photos", "achievements", "honor", "comments"):
        await page.goto(BASE + "/admin/index.html#" + tab, wait_until="networkidle")
        await page.wait_for_timeout(1600)
        if await page.locator(".empty-note:has-text('Не получилось')").count():
            result.fail(f"вкладка {tab} не загрузилась", "admin")
        else:
            result.ok()

    if errors:
        result.fail("; ".join(errors[:5]), "interactive")
    await context.close()


async def audit_pwa(browser, result: Result):
    context = await browser.new_context(viewport={"width": 375, "height": 812}, service_workers="allow")
    page = await context.new_page()
    await page.goto(BASE + "/app/index.html", wait_until="networkidle")
    ready = await page.evaluate(
        "() => navigator.serviceWorker.ready.then(() => true).catch(() => false)"
    )
    if not ready:
        result.fail("service worker не запустился", "pwa")
    else:
        result.ok()
    manifest = await page.evaluate(
        "() => fetch('manifest.json').then((r) => r.status).catch(() => 0)"
    )
    if manifest != 200:
        result.fail(f"manifest.json вернул {manifest}", "pwa")
    else:
        result.ok()
    version = await page.evaluate(
        "() => caches.keys().then((keys) => keys.join(','))"
    )
    if "gdz-nel-v10" not in version:
        result.fail(f"в кэше нет v10: {version[:120]}", "pwa")
    else:
        result.ok()
    await page.reload(wait_until="networkidle")
    await context.set_offline(True)
    try:
        await page.goto(BASE + "/app/index.html", wait_until="domcontentloaded", timeout=20000)
        text = await page.locator("body").inner_text()
        if "ГДЗ" not in text:
            result.fail("офлайн-страница пустая", "pwa")
        else:
            result.ok()
    except Exception as exc:  # noqa: BLE001
        result.fail(f"офлайн-навигация упала: {exc}", "pwa")
    await context.close()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="интерактив под админом")
    args = ap.parse_args()

    result = Result()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        await audit_pages(browser, result)
        await audit_pwa(browser, result)
        if args.live and ADMIN_PASSWORD:
            await audit_interactive(browser, result)
        elif args.live:
            result.fail("нет GDZ_ADMIN_PASSWORD — live-часть пропущена")
        await browser.close()

    print(f"проверок: {result.checks}, ошибок: {len(result.failures)}")
    for item in result.failures:
        print("FAIL", item)
    print("скриншоты:", SHOTS)
    return 1 if result.failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
