#!/usr/bin/env python3
"""быстрый смоук /app: сетка, шаги, столбик, фильтр, поиск, мобильная навигация."""
import os
import asyncio
import json
import sys

from playwright.async_api import async_playwright

BASE = os.environ.get("GDZ_BASE", "http://127.0.0.1:8000")
ERRORS = []


def on_console(msg):
    if msg.type == "error":
        ERRORS.append(("console", msg.text[:200]))


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 390, "height": 844})
        page.on("console", on_console)
        page.on("pageerror", lambda e: ERRORS.append(("pageerror", str(e)[:200], str(getattr(e, "stack", ""))[:400])))

        # 1. сетка: нет зачёркнутых ячеек, число ячеек совпадает с числом задач
        await page.goto(BASE + "/app/#/6/math/vilenkin-6-1", wait_until="networkidle")
        await page.wait_for_timeout(400)
        cells = await page.locator(".task-cell").count()
        missing = await page.locator(".task-cell.is-missing").count()
        count_text = await page.locator("#task-count").inner_text() if await page.locator("#task-count").count() else ""
        print("1) grid: cells =", cells, "missing =", missing, "| count:", count_text.strip()[:60])

        # 2. задача с шагами: элементы пронумерованы, префиксы «1)» не дублируются
        await page.goto(BASE + "/app/#/6/math/vilenkin-6-1/1.10", wait_until="networkidle")
        await page.wait_for_timeout(600)
        steps = await page.locator(".steps-list .step-line").count()
        first_step = await page.locator(".steps-list .step-line p").first.inner_text() if steps else ""
        print("2) steps =", steps, "| first:", first_step[:80])

        # 3. столбик: pre, переключатель работает
        col = await page.locator("pre.math-column").count()
        if col:
            text = await page.locator("pre.math-column").inner_text()
            print("3) column pre ok, первая строка:", text.splitlines()[0])
            await page.click("#column-toggle")
            hidden = await page.locator("#math-column-wrap").is_hidden()
            label = await page.locator("#column-toggle-label").inner_text()
            print("   после клика: скрыт =", hidden, "| лейбл:", label)
        else:
            print("3) НЕТ pre.math-column на 1.10 — плохо")

        # 4. фильтр из адресной строки
        await page.goto(BASE + "/app/#/6/math/vilenkin-6-1?q=1.2", wait_until="networkidle")
        await page.wait_for_timeout(700)
        visible = await page.locator(".task-cell:visible").count()
        print("4) фильтр ?q=1.2: видимых ячеек =", visible)

        # 5. поиск по слову
        await page.goto(BASE + "/app/#/search/урожайность", wait_until="networkidle")
        await page.wait_for_timeout(800)
        results = await page.locator(".list-item").count()
        print("5) поиск: результатов =", results)

        # 6. нижняя навигация и кнопка «наверх» на телефоне
        await page.goto(BASE + "/app/#/6/math/vilenkin-6-1", wait_until="networkidle")
        await page.wait_for_timeout(400)
        nav_visible = await page.locator("#bottom-nav").is_visible()
        await page.evaluate("window.scrollTo(0, 1500)")
        await page.wait_for_timeout(400)
        totop = await page.locator("#to-top").is_visible()
        progress = await page.evaluate("document.getElementById('read-progress').style.width")
        print("6) bottom-nav visible =", nav_visible, "| to-top =", totop, "| progress =", progress)

        # 7. офлайн-плашки нет при онлайне
        offline = await page.locator("#offline-bar").is_visible()
        print("7) offline-bar виден (должно быть False):", offline)

        await browser.close()

    print("console errors:", json.dumps(ERRORS[:15], ensure_ascii=False))
    return 0 if not ERRORS else 1


sys.exit(asyncio.run(main()))
