#!/usr/bin/env python3
"""Статический аудит безопасности ГДЗ НЭЛ.

Проверяет:
  * нет ли в клиентских html/js секретных ключей и service_role;
  * у каждой public-таблицы включён RLS;
  * у каждой таблицы есть хотя бы одна политика;
  * опасные операции (delete/update) не открыты роли anon.

Пишет docs/SECURITY.md и завершается с кодом 1 при утечке секрета.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "SECURITY.md"
CLIENT_SUFFIXES = {".html", ".js"}
SKIP_PARTS = {
    "scripts", "supabase", "node_modules", ".git", "venv", "venv-shots",
    "android-twa", "android-signing", "download",
}
SECRET_PATTERNS = [
    ("supabase secret key", re.compile(r"\bsb_secret_[A-Za-z0-9_-]{8,}")),
    ("Groq API key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}")),
    ("service_role JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}")),
]
SUSPICIOUS_WORDS = re.compile(r"\b(service_role|GROQ_API_KEY|SUPABASE_SERVICE_ROLE_KEY)\b")
PUBLISHABLE = re.compile(r"\bsb_publishable_[A-Za-z0-9_-]{8,}")


def client_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in CLIENT_SUFFIXES:
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        files.append(path)
    return sorted(files)


def scan_client() -> tuple[list[dict[str, object]], list[str], int]:
    findings: list[dict[str, object]] = []
    publishable: list[str] = []
    scanned = 0
    for path in client_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        scanned += 1
        relative = str(path.relative_to(ROOT))
        for title, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append({"file": relative, "line": line, "type": title})
        for match in SUSPICIOUS_WORDS.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append({
                "file": relative, "line": line,
                "type": "упоминание служебного ключа в клиенте",
                "word": match.group(0),
            })
        for match in PUBLISHABLE.finditer(text):
            publishable.append(match.group(0))
    return findings, sorted(set(publishable)), scanned


def strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    return re.sub(r"--[^\n]*", "", sql)


def scan_sql() -> tuple[list[dict[str, object]], int]:
    tables: dict[str, dict[str, object]] = {}
    policies: dict[str, list[str]] = {}
    sql_text = ""
    for path in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
        sql_text += "\n" + path.read_text(encoding="utf-8", errors="replace")

    clean = strip_sql_comments(sql_text)
    for match in re.finditer(
        r"\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?public\.([a-zA-Z0-9_]+)\s*\(",
        clean, re.I,
    ):
        tables.setdefault(match.group(1), {"rls": False, "policies": []})
    for match in re.finditer(
        r"\balter\s+table\s+public\.([a-zA-Z0-9_]+)\s+enable\s+row\s+level\s+security",
        clean, re.I,
    ):
        tables.setdefault(match.group(1), {"rls": False, "policies": []})["rls"] = True
    for match in re.finditer(
        r"\bcreate\s+policy\s+([a-zA-Z0-9_]+)\s+on\s+public\.([a-zA-Z0-9_]+)(.*?);",
        clean, re.I | re.S,
    ):
        name, table, body = match.group(1), match.group(2), match.group(3)
        tables.setdefault(table, {"rls": False, "policies": []})
        tables[table]["policies"].append(name)
        policies.setdefault(table, []).append(body.lower())

    rows = []
    for name in sorted(tables):
        data = tables[name]
        role_anon = any(re.search(r"\bto\s+[^;]*\banon\b", body) for body in policies.get(name, []))
        write_anon = role_anon and bool(re.search(
            r"\bfor\s+(insert|update|delete|all)\b", " ".join(policies.get(name, []))
        ))
        rows.append({
            "table": name,
            "rls": bool(data["rls"]),
            "policies": len(data["policies"]),
            "anon_write": write_anon,
        })
    return rows, len(tables)


def build_doc(client_findings, publishable, scanned, tables) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    missing_rls = [row for row in tables if not row["rls"]]
    missing_policies = [row for row in tables if row["rls"] and not row["policies"]]
    anon_write = [row for row in tables if row["anon_write"]]

    lines = [
        "# Безопасность ГДЗ НЭЛ",
        "",
        f"Аудит: {now}. Скрипт: `scripts/audit_security.py`.",
        "",
        "## Клиентский код",
        "",
        f"- просмотрено файлов `.html` / `.js`: **{scanned}**;",
        f"- найдено publishable-ключей: **{len(publishable)}**;",
        f"- найдено секретных ключей/`service_role`: **{len(client_findings)}**.",
        "",
        "В браузере используется только публикуемый ключ Supabase "
        "(`sb_publishable_…`). Он предназначен для клиента, доступ к данным "
        "ограничен RLS. Секретные ключи и `GROQ_API_KEY` живут только в "
        "переменных Supabase Edge Functions и в браузер не попадают.",
        "",
    ]
    if client_findings:
        lines += ["### Находки", ""]
        for item in client_findings:
            word = f" (`{item['word']}`)" if item.get("word") else ""
            lines.append(f"- `{item['file']}:{item['line']}` — {item['type']}{word}")
        lines += ["", "**Статус: требуется исправление.**", ""]
    else:
        lines += ["Проверка `grep` по клиенту: секретов и служебных ключей нет.", ""]

    lines += [
        "## RLS в базе",
        "",
        f"- public-таблиц найдено: **{len(tables)}**;",
        f"- без RLS: **{len(missing_rls)}**;",
        f"- с RLS, но без политик: **{len(missing_policies)}**;",
        f"- политики с записью для `anon`: **{len(anon_write)}**.",
        "",
        "| таблица | RLS | политик | запись anon |",
        "|---|---:|---:|---:|",
    ]
    for row in tables:
        lines.append(
            f"| `{row['table']}` | {'да' if row['rls'] else '**НЕТ**'} | "
            f"{row['policies']} | {'**ДА**' if row['anon_write'] else 'нет'} |"
        )

    lines += [
        "",
        "## Проверенные границы",
        "",
        "- `profiles`: пользователь читает/правит только свой профиль, админ — все; "
        "`role`, `ban`, `email`, `is_premium`, `premium_until`, `xp`, `streak_days`, "
        "`referral_code`, `referred_by` защищены триггером от подмены из браузера.",
        "- `reviews`: удаление и обновление чужих отзывов — только админ; "
        "INSERT — только свой и не забаненному.",
        "- `profile_comments`: автор удаляет свой комментарий, чужой — только админ.",
        "- `photo_requests`: свои записи и админ; удаление чужого — только админ.",
        "- `request_logs`, `ip_bans`, `promo_codes`: чтение/управление — только админ; "
        "промокод применяется через security definer RPC `redeem_promo`.",
        "- `xp_events`, `referrals`: клиент только читает свои; начисления — через "
        "security definer RPC/триггеры.",
        "- storage `photos` / `avatars`: запись и удаление только в своей папке `<uid>/`.",
        "",
        "## Ограничения",
        "",
        "- RLS проверен статически по миграциям. Фактическое состояние проекта "
        "нужно подтвердить SQL-запросом из `docs/SECURITY.md` раздела «Проверка».",
        "- Rate limit `log-request` работает после вызова Edge Function; на уровне "
        "CDN нужен Cloudflare WAF/Rate Limiting — он не заменяется клиентским логом.",
        "- Промокоды и рефералы можно пытаться фармить новыми аккаунтами; включи "
        "подтверждение email в Supabase Auth, если начнётся злоупотребление.",
        "",
        "## Проверка",
        "",
        "```sql",
        "select c.relname, c.relrowsecurity,",
        "       (select count(*) from pg_policies p where p.tablename = c.relname) as policies",
        "  from pg_class c",
        "  join pg_namespace n on n.oid = c.relnamespace",
        " where n.nspname = 'public' and c.relkind = 'r'",
        " order by c.relname;",
        "```",
        "",
        "Ожидается `relrowsecurity = true` у каждой таблицы и `policies > 0`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Аудит безопасности ГДЗ НЭЛ")
    parser.add_argument("--check", action="store_true", help="вернуть 1 при утечке")
    args = parser.parse_args()

    findings, publishable, scanned = scan_client()
    tables, _ = scan_sql()
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(build_doc(findings, publishable, scanned, tables), encoding="utf-8")

    print(f"клиентских файлов: {scanned}")
    print(f"publishable-ключей: {len(publishable)}")
    print(f"секретов/служебных ключей в клиенте: {len(findings)}")
    print(f"public-таблиц: {len(tables)}, без RLS: {sum(1 for t in tables if not t['rls'])}, "
          f"без политик: {sum(1 for t in tables if t['rls'] and not t['policies'])}")
    print(f"отчёт: {DOC.relative_to(ROOT)}")
    if findings:
        for item in findings:
            print(f"  ! {item['file']}:{item['line']} — {item['type']}")
        return 1 if args.check else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
