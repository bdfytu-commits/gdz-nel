#!/usr/bin/env python3
"""Мобильный аудит 375×812: все страницы, переполнение по горизонтали.

Проверяет лендинг, /app (сетка, длинная задача, поиск), все статические
страницы, профиль и все вкладки админки. Ловит горизонтальный скролл и
элементы, вылезающие за экран. Скриншоты — /tmp/opencode/mobile375/.

    scripts/venv-shots/bin/python scripts/tests/test_mobile_375.py

Сервер :8000 (или GDZ_BASE). Для админки нужен тестовый аккаунт
admin@gdz-nel.test — пароль берётся из scripts/tests/.env.local
(переменная GDZ_ADMIN_PASSWORD). Без пароля админка пропускается.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

from playwright.async_api import async_playwright

from env import load

load()

BASE = os.environ.get("GDZ_BASE", "http://127.0.0.1:8000").rstrip("/")
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
OUT = pathlib.Path("/tmp/opencode/mobile375")
OUT.mkdir(parents=True, exist_ok=True)

ADMIN_EMAIL = os.environ.get("GDZ_ADMIN_EMAIL", "admin@gdz-nel.test")
ADMIN_PASSWORD = os.environ.get("GDZ_ADMIN_PASSWORD", "")
SKIP_AUTH = os.environ.get("GDZ_SKIP_AUTH") == "1" or not ADMIN_PASSWORD

PAGES = [
    ("landing", "/"),
    ("app-home", "/app/#/"),
    ("app-grade-8", "/app/#/8/"),
    ("app-subjects", "/app/#/8/math/"),
    ("app-grid", "/app/#/6/math/vilenkin-6-1"),
    ("app-task", "/app/#/6/math/vilenkin-6-1/1.12"),
    ("app-search", "/app/#/search/дробь"),
    ("search", "/search.html"),
    ("cheatsheets", "/cheatsheets.html"),
    ("premium", "/premium.html"),
    ("photo", "/photo.html"),
    ("auth", "/auth.html"),
    ("about", "/about.html"),
    ("contact", "/contact.html"),
    ("privacy", "/privacy.html"),
    ("terms", "/terms.html"),
    ("disclaimer", "/disclaimer.html"),
    ("cookie-policy", "/cookie-policy.html"),
    ("accessibility", "/accessibility.html"),
    ("404", "/404.html"),
]

# самое длинное решение в учебнике — стресс-тест формул на узком экране
LONG_TASK = "/app/#/8/math/makarichev-8/797"


def long_number() -> str:
    path = ROOT / "app/data/algebra/makarichev-8.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        tasks = data.get("tasks") or []
        best = max(tasks, key=lambda t: len(json.dumps(t, ensure_ascii=False)))
        return str(best.get("number", "797"))
    except (OSError, ValueError):
        return "797"


CHECK_JS = r"""
() => {
  const vw = document.documentElement.clientWidth;
  const root = document.scrollingElement || document.documentElement;
  const overflow = root.scrollWidth - vw;

  function clipped(el) {
    let p = el.parentElement;
    while (p && p !== document.body) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === 'auto' || ox === 'scroll' || ox === 'hidden') {
        const pr = p.getBoundingClientRect();
        if (pr.right <= vw + 1) return true;
      }
      p = p.parentElement;
    }
    return false;
  }

  const bad = [];
  for (const el of document.querySelectorAll('body *')) {
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || el.hidden) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    if (st.position === 'fixed' && Math.abs(r.width - vw) < 2) continue;
    if (r.right > vw + 1 || r.left < -1) {
      if (clipped(el)) continue;
      bad.push({
        tag: el.tagName.toLowerCase(),
        cls: String(el.className || '').slice(0, 70),
        left: Math.round(r.left),
        right: Math.round(r.right),
        w: Math.round(r.width)
      });
    }
  }
  return {vw, overflow, bad: bad.slice(0, 8), badCount: bad.length};
}
"""


async def audit(page, label: str, url: str, expect: str | None = None) -> dict:
    await page.goto(BASE + url, wait_until="domcontentloaded")
    await page.wait_for_timeout(1000)
    try:
        await page.wait_for_function(
            "document.fonts ? document.fonts.status === 'loaded' : true", timeout=5000)
    except Exception:  # noqa: BLE001
        pass
    result = {"label": label, "url": url, "ok": True, "notes": []}
    if expect:
        count = await page.locator(expect).count()
        if not count:
            result["ok"] = False
            result["notes"].append(f"нет обязательного элемента {expect}")
    data = await page.evaluate(CHECK_JS)
    if data["overflow"] > 1 or data["badCount"]:
        # дать верстке устояться и перемерить — так тест не ловит момент загрузки
        await page.wait_for_timeout(700)
        data = await page.evaluate(CHECK_JS)
    result["overflow"] = data["overflow"]
    result["bad"] = data["bad"]
    result["badCount"] = data["badCount"]
    if data["overflow"] > 1 or data["badCount"]:
        result["ok"] = False
    await page.screenshot(path=str(OUT / f"{label}.png"))
    return result


async def main() -> int:
    errors: list[tuple[str, str]] = []
    results: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 375, "height": 812},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
        )
        page = await context.new_page()
        page.on("pageerror", lambda e: errors.append(("pageerror", f"{page.url}: {str(e)[:160]}")))
        page.on("console", lambda m: errors.append(("console", f"{page.url}: {m.text[:160]}"))
                if m.type == "error" else None)

        for label, url in PAGES:
            results.append(await audit(page, label, url))

        task_url = LONG_TASK.replace("/797", "/" + long_number())
        results.append(await audit(page, "app-task-long", task_url, expect="#solution-block"))
        # доскроллить до ответа: там формулы и дроби
        await page.locator(".answer").scroll_into_view_if_needed()
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(OUT / "app-task-long-answer.png"))

        # --- вход админом (в CI тестовых аккаунтов нет) ---
        if SKIP_AUTH:
            print("GDZ_SKIP_AUTH=1: профиль и админка пропущены")
        else:
            await page.goto(BASE + "/auth.html", wait_until="domcontentloaded")
            await page.fill("#li-email", ADMIN_EMAIL)
            await page.fill("#li-password", ADMIN_PASSWORD)
            await page.click("#login-submit")
            try:
                await page.wait_for_url("**/profile.html*", timeout=20000)
            except Exception:  # noqa: BLE001
                await page.wait_for_timeout(3000)
            results.append(await audit(page, "profile-admin", "/profile.html"))

            await page.goto(BASE + "/admin/", wait_until="domcontentloaded")
            try:
                await page.wait_for_selector("#admin:not([hidden])", timeout=20000)
            except Exception:  # noqa: BLE001
                pass
            await page.wait_for_timeout(1500)
            admin_visible = await page.locator("#admin:not([hidden])").count()
            results.append(await audit(page, "admin-overview", "/admin/#overview"))
            if not admin_visible:
                results[-1]["ok"] = False
                results[-1]["notes"].append("админка не открылась — проверь тестового админа")

            for tab, label in (
                ("users", "admin-users"),
                ("reviews", "admin-reviews"),
                ("ai", "admin-ai"),
                ("photos", "admin-photos"),
                ("achievements", "admin-achievements"),
            ):
                await page.goto(BASE + f"/admin/#{tab}", wait_until="domcontentloaded")
                await page.wait_for_timeout(1200)
                try:
                    await page.wait_for_function(
                        "document.fonts ? document.fonts.status === 'loaded' : true", timeout=5000)
                except Exception:  # noqa: BLE001
                    pass
                data = await page.evaluate(CHECK_JS)
                if data["overflow"] > 1 or data["badCount"]:
                    await page.wait_for_timeout(700)
                    data = await page.evaluate(CHECK_JS)
                item = {
                    "label": label, "url": f"/admin/#{tab}", "ok": True, "notes": [],
                    "overflow": data["overflow"], "bad": data["bad"], "badCount": data["badCount"],
                }
                if data["overflow"] > 1 or data["badCount"]:
                    item["ok"] = False
                await page.screenshot(path=str(OUT / f"{label}.png"))
                results.append(item)

        await browser.close()

    failed = [r for r in results if not r["ok"]]
    for r in results:
        mark = "ok  " if r["ok"] else "FAIL"
        line = f"{mark} {r['label']:<20} overflow={r.get('overflow')} bad={r.get('badCount')}"
        if r["notes"]:
            line += " | " + "; ".join(r["notes"])
        print(line)
        if not r["ok"] and r.get("bad"):
            for b in r["bad"][:4]:
                print(f"       {b['tag']}.{b['cls']} left={b['left']} right={b['right']} w={b['w']}")

    if errors:
        print("\nконсольные ошибки (не влияют на верстку):")
        for kind, text in errors[:12]:
            print(f" {kind}: {text}")

    print(f"\nстраниц: {len(results)}, падений: {len(failed)}, скриншоты: {OUT}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
