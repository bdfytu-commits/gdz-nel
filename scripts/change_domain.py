#!/usr/bin/env python3
"""Смена домена сайта по всему репозиторию в один запуск.

Заменяет старые адреса (по умолчанию gdz-nel.pages.dev и старый github-путь)
на новый домен во всех текстовых файлах: HTML, JS, CSS, JSON, sitemap.xml,
robots.txt, документация, парсеры, TG-бот. Бинарники (APK, картинки) не трогает.

Запуск (когда gdz-nel.is-a.dev одобрят):

    python3 scripts/change_domain.py                 # на gdz-nel.is-a.dev
    python3 scripts/change_domain.py example.ru      # на свой домен
    python3 scripts/change_domain.py --dry-run       # только показать, что изменится

После смены домена не забыть (скрипт напомнит):

    1. Cloudflare Pages → Custom domains → добавить новый домен;
    2. Supabase → Authentication → URL Configuration → Site URL и Redirect URLs;
    3. Lava.top — домен в настройках виджета/подписки (модерация домена);
    4. пересобрать APK: BUBBLEWRAP_DIR=/tmp/opencode/bw bash scripts/build_apk.sh build;
    5. sitemap.xml заново отправить в Яндекс.Вебмастер и Google Search Console.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NEW = "gdz-nel.is-a.dev"
OLD_HOSTS = ["gdz-nel.pages.dev", "bdfytu-commits.github.io/gdz-nel"]
TEXT_EXT = {
    ".html", ".htm", ".js", ".mjs", ".css", ".json", ".md", ".txt", ".xml",
    ".yml", ".yaml", ".py", ".sh", ".toml", ".sql", ".svg", ".webmanifest",
}
SKIP_DIRS = {".git", "node_modules", "venv-shots", "android-signing", "download"}
SKIP_FILES = {"scripts/change_domain.py"}  # себя не переписываем
TWA_MANIFEST = ROOT / "android-twa" / "twa-manifest.json"


def normalize(domain: str) -> str:
    d = domain.strip().lower()
    d = re.sub(r"^https?://", "", d)
    return d.strip("/")


def git_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout
    files = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8")
        if rel in SKIP_FILES:
            continue
        parts = rel.split("/")
        if any(p in SKIP_DIRS or p.startswith("venv") for p in parts):
            continue
        if rel.endswith(".apk") or rel.endswith(".png") or rel.endswith(".jpg"):
            continue
        path = ROOT / rel
        if path.is_file():
            files.append(path)
    return sorted(files)


def is_text(path: Path) -> bool:
    if path.suffix.lower() not in TEXT_EXT:
        return False
    try:
        chunk = path.read_bytes()[:8192]
    except OSError:
        return False
    return b"\0" not in chunk


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in argv
    new = normalize(args[0] if args else DEFAULT_NEW)
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.[a-z]{2,}", new):
        print("не похоже на домен:", new)
        return 2
    olds = [h for h in OLD_HOSTS if h != new]
    if not olds:
        print("новый домен совпадает со старым — нечего менять")
        return 0

    print(f"домен: {' → '.join(olds)} → {new}")
    print("режим:", "проверка (--dry-run)" if dry else "запись")

    files = 0
    total = 0
    for path in git_files():
        if not is_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits = sum(text.count(h) for h in olds)
        if not hits:
            continue
        for h in olds:
            text = text.replace(h, new)
        files += 1
        total += hits
        print(f"  {path.relative_to(ROOT)}: {hits}")
        if not dry:
            path.write_text(text, encoding="utf-8")

    print(f"\nфайлов: {files}, замен: {total}")

    # TWA-манифест живёт вне git (android-twa/ в .gitignore) — правим отдельно
    if TWA_MANIFEST.exists():
        data = json.loads(TWA_MANIFEST.read_text(encoding="utf-8"))
        changed = []
        for key in ("host",):
            if data.get(key) and data[key] in olds + [old.split("/")[0] for old in olds]:
                data[key] = new
                changed.append(key)
        for key in ("iconUrl", "maskableIconUrl", "webManifestUrl", "fullScopeUrl"):
            val = data.get(key, "")
            if any(h in val for h in olds):
                data[key] = val
                for h in olds:
                    data[key] = data[key].replace(h, new)
                changed.append(key)
        if data.get("host") != new:
            data["host"] = new
            changed.append("host")
        if changed:
            print(f"  android-twa/twa-manifest.json: {', '.join(sorted(set(changed)))}")
            if not dry:
                TWA_MANIFEST.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            print("  android-twa/twa-manifest.json: без изменений")

    if dry:
        print("\nэто был --dry-run, файлы не тронуты")
    print(
        "\nне забыть:\n"
        "  1. Cloudflare Pages → Custom domains → добавить " + new + ";\n"
        "  2. Supabase → Authentication → URL Configuration → Site URL и Redirect URLs;\n"
        "  3. Lava.top — домен в настройках подписки (повторная модерация);\n"
        "  4. пересобрать APK: BUBBLEWRAP_DIR=/tmp/opencode/bw bash scripts/build_apk.sh build;\n"
        "  5. sitemap.xml заново отправить в Яндекс.Вебмастер и Google Search Console."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
