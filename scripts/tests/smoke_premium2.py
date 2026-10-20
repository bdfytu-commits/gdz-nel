#!/usr/bin/env python3
"""Смоук премиум-фич (Ф35): шпаргалки, выбор модели, PDF, PRO в отзывах."""
import os
import asyncio
import sys

from playwright.async_api import async_playwright

from env import load

load()

BASE = os.environ.get("GDZ_BASE", "http://127.0.0.1:8000")
PASS = os.environ.get("GDZ_TEST_PASSWORD", "")
PREMIUM = os.environ.get("GDZ_USER1_EMAIL", "user1@gdz-nel.test")
FREE = os.environ.get("GDZ_USER2_EMAIL", "user2@gdz-nel.test")

ERRORS = []


async def login(page, email):
    await page.goto(BASE + "/auth.html", wait_until="networkidle")
    await page.fill("#li-email", email)
    await page.fill("#li-password", PASS)
    await page.click("#login-submit")
    await page.wait_for_timeout(2500)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda e: ERRORS.append(("pageerror", str(e)[:200])))
        page.on("console", lambda m: ERRORS.append(("console", m.text[:160])) if m.type == "error" else None)

        # 1. без входа: шпаргалки размыты
        await page.goto(BASE + "/cheatsheets.html", wait_until="networkidle")
        locked = await page.locator("#sheets-wrap.is-locked").count()
        lock_vis = await page.locator(".sheet-lock").is_visible()
        blur = await page.eval_on_selector(".sheets", "el => getComputedStyle(el).filter")
        print("1) шпаргалки (аноним): is-locked =", locked, "| плашка =", lock_vis, "| filter =", blur)

        # 1b. без входа: рекламная плашка на лендинге видна
        await page.goto(BASE + "/index.html", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        ad_anon = await page.locator("#ad-slot").is_visible()
        print("1b) реклама (аноним): видна =", ad_anon)

        await login(page, PREMIUM)

        # 2. премиум: рекламная плашка скрыта
        await page.goto(BASE + "/index.html", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        ad_prem = await page.locator("#ad-slot").is_visible()
        print("2a) реклама (премиум): скрыта =", not ad_prem)

        # 2b. премиум: шпаргалки открыты
        await page.goto(BASE + "/cheatsheets.html", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        unlocked = await page.locator("#sheets-wrap:not(.is-locked)").count()
        print("2) шпаргалки (премиум): разблокировано =", unlocked)

        # 3. премиум: выбор модели на фото
        await page.goto(BASE + "/photo.html", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        chips = await page.locator(".model-chip").count()
        model_vis = await page.locator("#photo-model").is_visible()
        locked_hint = await page.locator("#photo-model-locked").is_visible()
        print("3) фото (премиум): модель =", model_vis, "| чипов =", chips, "| подсказка =", locked_hint)

        # 4. отзывы: PRO-бейдж (отзыв админа — премиум)
        await page.goto(BASE + "/app/index.html#/6/math/vilenkin-6-1/1.82", wait_until="networkidle")
        await page.wait_for_selector(".review", timeout=10000)
        pro_avatars = await page.locator(".review-avatar.is-pro").count()
        pro_badges = await page.locator(".review .pro-badge").count()
        print("4) отзывы: золотых аватарок =", pro_avatars, "| PRO-бейджей =", pro_badges)

        # 5. PDF: премиум — без водяного знака
        pdf_count = await page.locator("#pdf-btn").count()
        await page.evaluate("window.print = function () { window.__printClass = document.body.className; };")
        await page.locator("#pdf-btn").click()
        await page.wait_for_timeout(300)
        printed = await page.evaluate("window.__printClass")
        layer = await page.locator("#print-layer").count()
        print("5) PDF (премиум): кнопка =", pdf_count, "| класс на печать =", repr(printed), "| слой =", layer)

        # 6. бесплатный: фото-страница
        await login(page, FREE)
        await page.goto(BASE + "/photo.html", wait_until="networkidle")
        await page.wait_for_timeout(1800)
        model_vis2 = await page.locator("#photo-model").is_visible()
        locked_hint2 = await page.locator("#photo-model-locked").is_visible()
        banner2 = await page.locator("#premium-banner").is_visible()
        limit2 = await page.locator("#photo-limit").inner_text()
        print("6) фото (user2): модель =", model_vis2, "| подсказка =", locked_hint2,
              "| плашка =", banner2, "| лимит:", limit2[:50])

        # 7. PDF: бесплатный — с водяным знаком
        await page.goto(BASE + "/app/index.html#/6/math/vilenkin-6-1/1.82", wait_until="networkidle")
        await page.wait_for_selector("#pdf-btn", timeout=10000)
        await page.evaluate("window.print = function () { window.__printClass = document.body.className; };")
        await page.locator("#pdf-btn").click()
        await page.wait_for_timeout(300)
        printed2 = await page.evaluate("window.__printClass")
        await page.emulate_media(media="print")
        layer_disp = await page.eval_on_selector("#print-layer", "el => getComputedStyle(el).display")
        print("7) PDF (user2): класс на печать =", repr(printed2), "| слой в @media print =", layer_disp)

        # 8. бесплатный: рекламная плашка снова видна
        await page.goto(BASE + "/index.html", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        ad_free = await page.locator("#ad-slot").is_visible()
        print("8) реклама (user2): видна =", ad_free)

        await browser.close()

    print("errors:", ERRORS[:10])
    return 0 if not ERRORS else 1


sys.exit(asyncio.run(main()))
