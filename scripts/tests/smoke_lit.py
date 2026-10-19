"""Смоук: литература Коровиной на локальном сервере (порт 8000).

Открывает все 8 книг (если собран json), проверяет сетку, экран задачи
(условие/решение/ответ), ошибки консоли и делает скриншоты.
"""
import os
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE = os.environ.get("GDZ_BASE", "http://127.0.0.1:8000")
DATA = Path(__file__).resolve().parent.parent.parent / "app" / "data" / "literature"
BOOKS = [
    (6, "korovina-6-1"), (6, "korovina-6-2"),
    (7, "korovina-7-1"), (7, "korovina-7-2"),
    (8, "korovina-8-1"), (8, "korovina-8-2"),
    (9, "korovina-9-1"), (9, "korovina-9-2"),
]


async def main() -> None:
    only = sys.argv[1:]
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # карточка предмета на лендинге
        await page.goto(BASE + "/index.html", wait_until="networkidle")
        try:
            txt = await page.eval_on_selector(
                '[data-subject="literature"] .card-count', "el => el.textContent"
            )
            print("лендинг, литература:", txt)
        except Exception as exc:  # noqa: BLE001
            print("лендинг, литература: карточка не найдена:", exc)

        # страница предмета в приложении
        await page.goto(BASE + "/app/index.html#/6/literature", wait_until="networkidle")
        await page.wait_for_selector(".bookcard", timeout=8000)
        books = await page.eval_on_selector_all(
            ".bookcard", "els => els.map(e => e.textContent.replace(/\\s+/g, ' ').trim())"
        )
        print("предмет 6 класс, книги:", books or "(селектор .book-card пуст)")
        await page.screenshot(path="/tmp/opencode/lit_subject.png")

        for grade, book in BOOKS:
            if only and book not in only:
                continue
            if not (DATA / f"{book}.json").exists():
                print(f"-- {book}: json нет, пропуск")
                continue
            await page.goto(BASE + f"/app/index.html#/{grade}/literature/{book}", wait_until="networkidle")
            await page.wait_for_selector(".task-cell", timeout=8000)
            cells = await page.eval_on_selector_all(".task-cell", "els => els.map(e => e.textContent.trim())")
            chips = await page.eval_on_selector_all(
                ".section-chip, .chip", "els => els.map(e => e.textContent.trim()).filter(Boolean)"
            )
            print(f"{book}: ячеек {len(cells)} (первая {cells[0]}), разделов {len(chips)}: {chips[:6]}")
            # открываем задачу с картинкой? смоук первой задачи
            first = cells[0].replace("×", "").strip()
            await page.goto(BASE + f"/app/index.html#/{grade}/literature/{book}/{first}", wait_until="networkidle")
            await page.wait_for_selector("#solution-block", timeout=8000)
            cond = await page.eval_on_selector(
                ".task-block--cond", "el => el.textContent.replace(/\\s+/g, ' ').trim().slice(0, 90)"
            )
            try:
                ans = await page.eval_on_selector(
                    ".task-block--answer", "el => el.textContent.replace(/\\s+/g, ' ').trim().slice(0, 90)"
                )
            except Exception:  # noqa: BLE001
                ans = "(блок ответа отсутствует)"
            print(f"  задача {first}: условие «{cond}» | ответ «{ans}»")
            if book in ("korovina-6-1", "korovina-9-2"):
                await page.screenshot(path=f"/tmp/opencode/lit_task_{book}.png", full_page=True)

        print("ошибки консоли:", errors[:6] or "нет")
        await browser.close()


asyncio.run(main())
