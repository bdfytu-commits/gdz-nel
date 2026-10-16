#!/usr/bin/env python3
"""Аудит контраста палитры ГДЗ НЭЛ по WCAG 2.1.

Считает коэффициент контраста для пар цветов светлой и тёмной темы
и проверяет требование AA: >= 4.5:1 для текста, >= 3:1 для графики.

Запуск: uv run python scripts/audit_contrast.py
Выход: код 1, если есть провалы.
"""

TEXT = 4.5   # обычный текст
GRAPHIC = 3.0  # иконки, границы, крупный текст


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = lin(r), lin(g), lin(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def mix(fg: str, bg: str, alpha: float) -> str:
    """Накладывает fg на bg с прозрачностью alpha (0..1)."""
    f = [int(fg.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(bg.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    out = [round(f[i] * alpha + b[i] * (1 - alpha)) for i in range(3)]
    return "#%02X%02X%02X" % tuple(out)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# палитра (держать в синхроне с css)
LIGHT = {
    "bg": "#FFFFFF", "surface": "#FFFFFF", "surface2": "#F5F5F5",
    "text": "#3C3C3C", "muted": "#6E6E6E", "link": "#0E7C7C",
    "primary": "#1AA3A3", "footer": "#3C3C3C", "footer_text": "#FFFFFF",
    "footer_muted": "#B9B9B9",
}
DARK = {
    "bg": "#1A1A1A", "surface": "#242424", "surface2": "#2C2C2C",
    "text": "#E8E8E8", "muted": "#9A9A9A", "link": "#1AA3A3",
    "primary": "#1AA3A3", "answer_bg": mix("#1AA3A3", "#242424", 0.07),
    "footer": "#161616", "footer_text": "#E8E8E8", "footer_muted": "#9A9A9A",
}
HERO_START = mix("#000000", "#1AA3A3", 0.20)
HERO_END = mix("#000000", "#0070C0", 0.20)
LIGHT["answer_bg"] = mix("#1AA3A3", "#FFFFFF", 0.07)


def audit(theme_name: str, t: dict, pairs: list) -> int:
    print(f"\n== {theme_name} ==")
    failed = 0
    for name, fg, bg, need in pairs:
        ratio = contrast(t[fg], t[bg])
        ok = ratio >= need
        if not ok:
            failed += 1
        print(f"{'ok  ' if ok else 'FAIL'} {ratio:5.2f}:1  (нужно {need})  {name}: {t[fg]} на {t[bg]}")
    return failed


failures = 0
failures += audit("светлая тема", LIGHT, [
    ("основной текст", "text", "bg", TEXT),
    ("основной текст на сером блоке", "text", "surface2", TEXT),
    ("приглушённый текст", "muted", "bg", TEXT),
    ("приглушённый текст на сером блоке", "muted", "surface2", TEXT),
    ("ссылки и акценты", "link", "bg", TEXT),
    ("ссылки на сером блоке", "link", "surface2", TEXT),
    ("ответ на бирюзовой подложке", "link", "answer_bg", TEXT),
    ("бирюза как графика (рамки, иконки)", "primary", "bg", GRAPHIC),
    ("текст футера", "footer_text", "footer", TEXT),
    ("приглушённый текст футера", "footer_muted", "footer", TEXT),
])

failures += audit("тёмная тема", DARK, [
    ("основной текст", "text", "bg", TEXT),
    ("основной текст на поверхности", "text", "surface", TEXT),
    ("приглушённый текст", "muted", "bg", TEXT),
    ("приглушённый текст на поверхности", "muted", "surface", TEXT),
    ("приглушённый текст на сером блоке", "muted", "surface2", TEXT),
    ("ссылки и акценты", "link", "surface", TEXT),
    ("ссылки на сером блоке", "link", "surface2", TEXT),
    ("ответ на бирюзовой подложке", "link", "answer_bg", TEXT),
    ("текст футера", "footer_text", "footer", TEXT),
    ("приглушённый текст футера", "footer_muted", "footer", TEXT),
])

hero = [
    ("белый текст на hero (начало градиента)", contrast("#FFFFFF", HERO_START), TEXT),
    ("белый текст на hero (конец градиента)", contrast("#FFFFFF", HERO_END), TEXT),
]
print("\n== hero (градиент с затемнением 20%) ==")
for name, ratio, need in hero:
    ok = ratio >= need
    if not ok:
        failures += 1
    print(f"{'ok  ' if ok else 'FAIL'} {ratio:5.2f}:1  (нужно {need})  {name}")

# кнопки: белый текст на затемнённом градиенте
BTN_START = "#128080"
BTN_END = "#005CA8"
print("\n== кнопки (grad-btn) ==")
for name, ratio, need in [
    ("белый текст кнопки (начало)", contrast("#FFFFFF", BTN_START), TEXT),
    ("белый текст кнопки (конец)", contrast("#FFFFFF", BTN_END), TEXT),
]:
    ok = ratio >= need
    if not ok:
        failures += 1
    print(f"{'ok  ' if ok else 'FAIL'} {ratio:5.2f}:1  (нужно {need})  {name}")

print(f"\nитог: {'всё проходит AA' if failures == 0 else str(failures) + ' провалов'}")
raise SystemExit(1 if failures else 0)
