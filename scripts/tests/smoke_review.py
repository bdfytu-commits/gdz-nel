#!/usr/bin/env python3
"""Чистый смоук: отзыв публикуется сразу, с логом ответов reviews."""
import os
import asyncio
import sys

from playwright.async_api import async_playwright

from env import account_ready, load

load()

BASE = os.environ.get("GDZ_BASE", "http://127.0.0.1:8000")
TASK = "#/6/math/vilenkin-6-1/1.16"
USER = os.environ.get("GDZ_USER2_EMAIL", "user2@gdz-nel.test")
PASS = os.environ.get("GDZ_TEST_PASSWORD", "")

logs = []


async def main():
    if not account_ready(USER, PASS):
        print("нет аккаунта/профиля", USER, "— смоук отзывов пропущен")
        return 0
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda e: logs.append(("pageerror", str(e)[:200])))

        async def on_response(r):
            if "/rest/v1/reviews" in r.request.url:
                try:
                    body = await r.text()
                except Exception:
                    body = "?"
                print("RESP", r.status, r.request.method, "|", body[:180].replace("\n", " "))

        page.on("response", lambda r: asyncio.ensure_future(on_response(r)))

        await page.goto(BASE + "/auth.html", wait_until="networkidle")
        await page.fill("#li-email", USER)
        await page.fill("#li-password", PASS)
        await page.click("#login-submit")
        await page.wait_for_timeout(3000)
        if "/auth.html" in page.url:
            print("нет тестового аккаунта", USER, "— смоук отзывов пропущен")
            await browser.close()
            return 0

        await page.goto(BASE + "/app/" + TASK, wait_until="networkidle")
        await page.wait_for_timeout(2500)
        await page.locator("#reviews").scroll_into_view_if_needed()
        await page.wait_for_timeout(1200)

        await page.fill("#review-text", "Прод-проверка 1.16: отзыв виден сразу: публикация сразу.")
        await page.click("#review-submit")
        await page.wait_for_timeout(600)
        toast = await page.locator(".toast").inner_text() if await page.locator(".toast").count() else "(нет)"
        print("тост:", repr(toast))

        await page.wait_for_timeout(3000)
        after = await page.locator("#reviews-list").inner_text()
        print("список после 3.6c:", after[:200].replace("\n", " / "))
        count = await page.locator("#reviews-count").inner_text() if await page.locator("#reviews-count").count() else ""
        print("счётчик:", repr(count))
        badge = await page.locator(".review-mine-badge").inner_text() if await page.locator(".review-mine-badge").count() else "(нет)"
        print("бейдж:", repr(badge))

        await browser.close()
    print("pageerror:", logs[:5])
    return 0


sys.exit(asyncio.run(main()))
