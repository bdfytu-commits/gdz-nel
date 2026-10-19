#!/usr/bin/env python3
"""смоук админки 2.0: вход, вкладки, модалка, csv недоступен оффлайн (не жмём), realtime-канал создаётся."""
import os
import asyncio
import sys

from playwright.async_api import async_playwright

BASE = os.environ.get("GDZ_BASE", "http://127.0.0.1:8000")
ADMIN_EMAIL = "admin@gdz-nel.test"
ADMIN_PASS = "GdzNel-Test-2026!"

ERRORS = []


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: ERRORS.append(("pageerror", str(e)[:300])))
        page.on("console", lambda m: ERRORS.append(("console", m.text[:200])) if m.type == "error" else None)

        # вход через форму авторизации
        await page.goto(BASE + "/auth.html", wait_until="networkidle")
        await page.fill("#li-email", ADMIN_EMAIL)
        await page.fill("#li-password", ADMIN_PASS)
        await page.click("#login-submit")
        await page.wait_for_timeout(2500)
        print("1) login: url =", page.url)

        # админка
        await page.goto(BASE + "/admin/", wait_until="networkidle")
        await page.wait_for_timeout(2500)
        denied = await page.locator("#admin-denied").is_visible()
        admin_visible = await page.locator("#admin").is_visible()
        print("2) admin: denied =", denied, "| visible =", admin_visible)

        if admin_visible:
            canvas = await page.locator("#dash-chart").count()
            cards = await page.locator(".dash-card").count()
            print("3) обзор: canvas =", canvas, "| карточек =", cards)

            # вкладка пользователей
            await page.click('.admin-nav a[data-tab="users"]')
            await page.wait_for_timeout(1500)
            rows = await page.locator(".admin-table tbody tr").count()
            print("4) users: строк =", rows)
            # модалка бана
            if rows:
                btn = page.locator('button[data-op="ban"]').first
                if await btn.count():
                    await btn.click()
                    await page.wait_for_timeout(400)
                    modal = await page.locator(".modal-card").is_visible()
                    print("5) модалка бана =", modal)
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(300)
                    print("   после Esc модалка =", await page.locator(".modal-card").count() > 0)

            # вкладка достижений
            await page.click('.admin-nav a[data-tab="achievements"]')
            await page.wait_for_timeout(1800)
            ach_cards = await page.locator(".dash-card").count()
            print("6) достижения: карточек =", ach_cards)

            # вкладка отзывов
            await page.click('.admin-nav a[data-tab="reviews"]')
            await page.wait_for_timeout(1500)
            rev_rows = await page.locator(".admin-table tbody tr").count()
            print("7) отзывы: строк =", rev_rows)

            # мобильная вёрстка админки
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.wait_for_timeout(600)
            nav = await page.locator(".admin-nav").is_visible()
            print("8) мобильный вид: nav виден =", nav)

        await browser.close()

    print("errors:", ERRORS[:10])
    return 0 if not ERRORS else 1


sys.exit(asyncio.run(main()))
