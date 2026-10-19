#!/usr/bin/env python3
"""Визуал математики: списки, минусы, дроби, SVG-графики."""
import os
import asyncio
import sys

from playwright.async_api import async_playwright

BASE = os.environ.get("GDZ_BASE", "http://127.0.0.1:8000")
logs = []


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 900, "height": 1400}, device_scale_factor=2)
        page.on("pageerror", lambda e: logs.append(("pageerror", str(e)[:200])))
        page.on("console", lambda m: logs.append(("console", m.text[:200])) if m.type == "error" else None)

        # 1. задание с шагами, минусами и дробями
        await page.goto(BASE + "/app/#/6/math/vilenkin-6-1/1.78", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        html = await page.locator("#solution-block").inner_html()
        step = await page.locator(".steps-intro").inner_text()
        has_badges = await page.locator(".step-num").count()
        fracs = await page.locator(".frac").count()
        marker = await page.evaluate("getComputedStyle(document.querySelector('.steps-list')).listStyleType")
        print("1) шаги: intro =", repr(step), "| старых кружков =", has_badges, "| list-style =", marker)
        print("   дробей на странице:", fracs)
        await page.locator("#solution-block").screenshot(path="/tmp/opencode/vis_steps.png")
        print("   первый <li>:", (await page.locator(".steps-list li").first.inner_html())[:150])

        # 2. координатная прямая
        await page.goto(BASE + "/app/#/6/math/vilenkin-6-2/4.12", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        vis = await page.locator(".task-visual").count()
        if vis:
            await page.locator(".task-visual").first.screenshot(path="/tmp/opencode/vis_line.png")
        print("2) координатная прямая найдена:", vis)

        # 3. генераторы на синтетике
        pie = await page.evaluate("""() => window.gdzVisuals.taskVisualHtml({
            condition: 'Постройте круговую диаграмму распределения: лес — 40%, пашня — 30%, луг — 20%, дороги — 10%.'
        })""")
        line = await page.evaluate("""() => window.gdzVisuals.taskVisualHtml({
            condition: 'Отметьте на координатной прямой точки A(-3), B(1,5), C(4).'
        })""")
        print("3) синтетика: пирог =", bool(pie), "| прямая =", bool(line))
        if pie:
            await page.set_content("<html><body style='background:#fff'>" + pie + "</body></html>")
            await page.wait_for_timeout(300)
            await page.screenshot(path="/tmp/opencode/vis_pie.png", clip={"x": 0, "y": 0, "width": 700, "height": 420})
        if line:
            await page.set_content("<html><body style='background:#fff'>" + line + "</body></html>")
            await page.wait_for_timeout(300)
            await page.screenshot(path="/tmp/opencode/vis_nline.png", clip={"x": 0, "y": 0, "width": 700, "height": 260})

        # 4. минус — обычный дефис
        minus = await page.evaluate("() => window.gdzVisuals.mathHtml('5 − 3 = 2,  •  точка')")
        print("4) нормализация:", repr(minus))

        await browser.close()
    print("ошибки:", logs[:8])
    return 0


sys.exit(asyncio.run(main()))
