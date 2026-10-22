#!/usr/bin/env python3
"""Офлайн-тест: скачать учебник, отключить сеть, открыть задание.

Запуск (сервер должен быть уже поднят):
    GDZ_BASE=http://127.0.0.1:8000 scripts/venv-shots/bin/python scripts/tests/test_offline.py
"""
from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("GDZ_BASE", "http://127.0.0.1:8000")
BOOK = "math/vilenkin-6-1.json"
BOOK_ID = "vilenkin-6-1"
TASK = "1.1"
ERRORS: list[str] = []


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844})
        page = context.new_page()
        page.on("pageerror", lambda e: ERRORS.append("pageerror: " + str(e)[:300]))
        page.on("console", lambda m: ERRORS.append("console: " + m.text[:200]) if m.type == "error" else None)

        print("1) открываю приложение")
        page.goto(BASE + "/app/index.html", wait_until="networkidle")
        page.wait_for_function(
            "navigator.serviceWorker && navigator.serviceWorker.controller !== null",
            timeout=30_000,
        )
        print("   sw:", page.evaluate("navigator.serviceWorker.controller.scriptURL"))

        print("2) открываю учебник и качаю")
        page.goto(BASE + "/app/index.html#/6/math", wait_until="networkidle")
        page.wait_for_selector('.bookcard-shell[data-file="' + BOOK + '"] .offline-btn', timeout=15_000)
        page.locator('.bookcard-shell[data-file="' + BOOK + '"] .offline-btn').click()
        page.wait_for_function(
            "() => { const b = document.querySelector('.bookcard-shell[data-file=\\\"" + BOOK + "\\\"] .offline-btn-label');"
            " return b && b.textContent.trim() === 'Скачано'; }",
            timeout=180_000,
        )
        meta = page.evaluate(
            "() => new Promise((resolve, reject) => {"
            " const r = indexedDB.open('gdz-nel-offline', 1);"
            " r.onerror = () => reject(r.error);"
            " r.onsuccess = () => { const db = r.result;"
            "  const tx = db.transaction('books', 'readonly');"
            "  const get = tx.objectStore('books').get('" + BOOK + "');"
            "  get.onsuccess = () => resolve(get.result); get.onerror = () => reject(get.error); }; })"
        )
        assert meta and meta.get("taskCount", 0) > 0, "в IndexedDB нет заданий"
        assert meta.get("bytes", 0) > 0, "не посчитан размер офлайн-копии"
        print("   задач:", meta["taskCount"], "| размер:", meta.get("bytes"), "байт")

        print("3) отключаю сеть")
        context.set_offline(True)
        page.reload(wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_selector("#screen", timeout=15_000)

        print("4) открываю задание из IndexedDB")
        page.evaluate("location.hash = '#/6/math/" + BOOK_ID + "/" + TASK + "'")
        page.wait_for_selector(".task-block", timeout=20_000)
        text = page.locator("#screen").inner_text()
        assert "1.1" in text or "1,1" in text, "номер задания не отображается"
        assert len(text) > 120, "экран задания пустой"

        print("5) прямой JSON-запрос офлайн")
        count = page.evaluate(
            "() => fetch('data/" + BOOK + "').then(r => r.json()).then(d => (d.tasks || []).length)"
        )
        assert count > 0, "SW не отдал JSON из IndexedDB"
        print("   SW отдал задач:", count)

        print("6) offline.html доступен")
        page.goto(BASE + "/app/offline.html", wait_until="domcontentloaded", timeout=20_000)
        assert page.locator("h1").inner_text().strip(), "offline.html пустой"
        assert page.locator(".book").count() >= 1, "offline.html не показал скачанный учебник"

        print("7) без скачанных книг SW отдаёт offline.html")
        ctx2 = browser.new_context()
        page2 = ctx2.new_page()
        page2.goto(BASE + "/app/index.html", wait_until="networkidle")
        page2.wait_for_function(
            "navigator.serviceWorker && navigator.serviceWorker.controller !== null",
            timeout=30_000,
        )
        ctx2.set_offline(True)
        page2.goto(BASE + "/app/index.html?offline=1#/6/math", wait_until="domcontentloaded", timeout=20_000)
        assert "Интернет недоступен" in page2.locator("h1").inner_text(), "нет offline-фолбэка"
        ctx2.set_offline(False)
        ctx2.close()

        print("OK: офлайн-режим работает")
        if ERRORS:
            print("ошибки консоли:", json.dumps(ERRORS[:5], ensure_ascii=False))
        context.set_offline(False)
        browser.close()
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print("FAIL:", exc)
        raise
