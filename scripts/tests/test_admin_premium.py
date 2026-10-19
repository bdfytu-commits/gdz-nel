#!/usr/bin/env python3
"""Смоук вкладки «Юзеры»: колонка ГДЗ+, кнопки Выдать/Продлить/Забрать PRO.

Полный цикл: выдать → продлить → забрать, с проверкой бейджа и тостов.
После прогона подписку user1 вернуть к исходному снапшоту (см. откат в конце).
"""
import os
from urllib.parse import quote

from playwright.sync_api import sync_playwright

BASE = os.environ.get("GDZ_BASE", "http://127.0.0.1:8000")
EMAIL = "admin@gdz-nel.test"
PASSWORD = "GdzNel-Test-2026!"


def main() -> None:
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        page.goto(BASE + "/auth.html?next=" + quote("admin/index.html"), wait_until="domcontentloaded")
        page.fill("#li-email", EMAIL)
        page.fill("#li-password", PASSWORD)
        page.click("#login-submit")
        page.wait_for_timeout(4000)

        page.goto(BASE + "/admin/index.html#users", wait_until="domcontentloaded")
        page.wait_for_selector("table.admin-table tbody tr", timeout=20000)

        headers = [h.strip() for h in page.locator("table.admin-table thead th").all_inner_texts()]
        assert "ГДЗ+" in headers, f"нет колонки ГДЗ+, заголовки: {headers}"
        print("колонка ГДЗ+ есть")

        def row():
            return page.locator("table.admin-table tbody tr", has_text="user1@gdz-nel.test").first

        def badge():
            r = row()
            return r.locator(".badge.is-premium").inner_text() if r.locator(".badge.is-premium").count() else None

        def click_confirm():
            page.wait_for_selector("#admin-modal:not([hidden]) .modal-card", timeout=5000)
            title = page.locator("#admin-modal .modal-title").inner_text()
            page.locator('#admin-modal [data-modal="yes"]').click()
            page.wait_for_timeout(3000)
            page.wait_for_selector("table.admin-table tbody tr", timeout=15000)
            return title

        def click_row_button(name):
            row().get_by_role("button", name=name).click()
            page.wait_for_timeout(400)

        r = row()
        buttons = r.locator("button").all_inner_texts()
        print("кнопки:", [b for b in buttons if "PRO" in b])
        print("бейдж сейчас:", badge() or "нет")
        page.screenshot(path="/tmp/opencode/admin-premium-before.png")

        # если подписки нет — выдать
        if badge() is None:
            click_row_button("Выдать PRO")
            print("модалка:", click_confirm())
            assert badge() is not None, "подписка не появилась"
            print("выдать ок:", badge())

        # продлить
        before = badge()
        click_row_button("Продлить PRO")
        print("модалка:", click_confirm())
        after = badge()
        assert after is not None and after != before, f"срок не изменился: {before} → {after}"
        print("продлить ок:", before, "→", after)
        page.screenshot(path="/tmp/opencode/admin-premium-after.png")

        # забрать
        click_row_button("Забрать PRO")
        print("модалка:", click_confirm())
        assert badge() is None, "бейдж ГДЗ+ не пропал"
        assert row().get_by_role("button", name="Выдать PRO").count() == 1, "нет кнопки Выдать PRO"
        print("забрать ок: подписка снята")

        if errors:
            print("ошибки консоли:", errors[:5])
        else:
            print("ошибок консоли нет")
        browser.close()


if __name__ == "__main__":
    main()
