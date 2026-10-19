#!/usr/bin/env python3
"""Реальные скриншоты ГДЗ НЭЛ через playwright.

Перед запуском подними локальный сервер из корня проекта:
    uv run python -m http.server 8000

Запуск скрипта:
    scripts/venv-shots/bin/python scripts/take_screenshots.py

Один раз нужно поставить окружение:
    uv venv scripts/venv-shots
    uv pip install --python scripts/venv-shots/bin/python playwright
    scripts/venv-shots/bin/playwright install chromium-headless-shell

Скриншоты кладутся в assets/img/screens/ и попадают на лендинг
(блок «Как это выглядит»).
"""
import pathlib

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "img" / "screens"
BASE = "http://localhost:8000"

MOBILE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2}
DESKTOP = {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 1}


def shot(page, name, url, selector, pause=900):
    """Открывает url и снимает скриншот в assets/img/screens/<name>."""
    page.goto(url, wait_until="networkidle")
    page.wait_for_selector(selector)
    page.wait_for_timeout(pause)  # даём шрифтам и переходам успокоиться
    # рекламную плашку не снимаем: в кадр она попадает не всегда (грузится асинхронно)
    page.evaluate("() => { const el = document.getElementById('ad-slot'); if (el) el.remove(); }")
    page.screenshot(path=str(OUT / name))
    print("снят", name)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # мобильные экраны приложения (основа лендинга)
        mobile = browser.new_context(**MOBILE, color_scheme="light", reduced_motion="reduce")
        page = mobile.new_page()
        shot(page, "app-subjects.png", BASE + "/app/#/", ".subject-grid")
        shot(page, "app-tasks.png", BASE + "/app/#/math/vilenkin-6-1", ".task-grid")
        shot(page, "app-task.png", BASE + "/app/#/math/vilenkin-6-1/1.12", ".task-block--answer")

        # тёмная тема
        page.goto(BASE + "/app/#/")
        page.evaluate("localStorage.setItem('gdz-nel-theme', 'dark')")
        shot(page, "app-task-dark.png", BASE + "/app/#/math/vilenkin-6-1/1.12", ".task-block--answer")
        mobile.close()

        # десктоп: лендинг и приложение
        desktop = browser.new_context(**DESKTOP, color_scheme="light", reduced_motion="reduce")
        page = desktop.new_page()
        shot(page, "landing-1440.png", BASE + "/", ".hero")
        shot(page, "app-home-1440.png", BASE + "/app/#/", ".subject-grid")
        shot(page, "app-task-1440.png", BASE + "/app/#/math/vilenkin-6-1/1.12", ".task-block--answer")
        desktop.close()

        # og-картинка 1200×630 для соцсетей
        og = browser.new_context(viewport={"width": 1200, "height": 630}, device_scale_factor=1,
                                 color_scheme="light", reduced_motion="reduce")
        og_page = og.new_page()
        shot(og_page, "og-1200x630.png", BASE + "/", ".hero")
        og.close()

        browser.close()

    print("готово:", sorted(f.name for f in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
