"""Смоук: контурные карты на локальном сервере (порт 8000)."""
import os
import asyncio

from playwright.async_api import async_playwright

BASE = os.environ.get("GDZ_BASE", "http://127.0.0.1:8000")
os.makedirs("/tmp/opencode", exist_ok=True)


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # лендинг: карточки географии и контурных карт истории
        await page.goto(BASE + "/index.html", wait_until="networkidle")
        for subj in ("geo", "history-maps"):
            txt = await page.eval_on_selector(
                f'[data-subject="{subj}"] .card-count', "el => el.textContent"
            )
            print("лендинг", subj, ":", txt)

        # приложение: классы 6-9
        await page.goto(BASE + "/app/index.html#/", wait_until="networkidle")
        await page.wait_for_selector(".subject-card", timeout=8000)
        cards = await page.eval_on_selector_all(
            ".subject-card", "els => els.map(e => e.textContent.replace(/\\s+/g, ' ').trim())"
        )
        print("классы:", cards)
        await page.screenshot(path="/tmp/opencode/kontur_home.png")

        # 6 -> география -> книга
        await page.goto(BASE + "/app/index.html#/6/geo/matveev-6", wait_until="networkidle")
        await page.wait_for_selector(".task-cell", timeout=8000)
        cells = await page.eval_on_selector_all(".task-cell", "els => els.map(e => e.textContent.trim())")
        print("ячейки matveev-6:", cells)

        # задание 2–3: картинка должна загрузиться
        await page.goto(BASE + "/app/index.html#/6/geo/matveev-6/2%E2%80%933", wait_until="networkidle")
        await page.wait_for_selector(".task-image img", timeout=8000)
        await page.wait_for_timeout(700)
        w = await page.evaluate("document.querySelector('.task-image img').naturalWidth")
        has_answer = await page.evaluate("!!document.getElementById('solution-block') && !!document.querySelector('.task-block--answer')")
        print("картинка naturalWidth:", w, "| блок ответа показан:", has_answer)
        await page.screenshot(path="/tmp/opencode/kontur_task.png", full_page=True)

        # 9 класс история: ячейки + первая картинка
        await page.goto(BASE + "/app/index.html#/9/history-maps/torop-9", wait_until="networkidle")
        await page.wait_for_selector(".task-cell", timeout=8000)
        cells9 = await page.eval_on_selector_all(".task-cell", "els => els.map(e => e.textContent.trim())")
        print("ячейки torop-9:", cells9[:6])

        print("ошибки консоли:", errors[:6] or "нет")
        await browser.close()


asyncio.run(main())
