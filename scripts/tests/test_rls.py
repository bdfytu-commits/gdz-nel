#!/usr/bin/env python3
"""RLS и атомарность лайков на живом Supabase.

Проверяет:
  * чужой отзыв/комментарий/пост нельзя удалить или изменить;
  * админ может удалить и изменить;
  * владелец не может удалить собственный профиль (только админ);
  * honor_like выдерживает конкурентные переключения и не уводит счётчик;
  * прямой insert в honor_likes закрыт — только RPC.

Запуск:
    python3 scripts/tests/test_rls.py

Нужны GDZ_ADMIN_*, GDZ_USER1_*, GDZ_USER2_* и GDZ_TEST_PASSWORD
в scripts/tests/.env.local. Тестовые строки удаляются в finally.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from env import SUPABASE_KEY, SUPABASE_URL, load

load()

ERRORS: list[str] = []
CREATED_REVIEWS: list[str] = []
CREATED_COMMENTS: list[str] = []
CREATED_POSTS: list[int] = []


def fail(msg: str) -> None:
    ERRORS.append(msg)
    print("ОШИБКА:", msg)


def request(method: str, path: str, token: str | None = None, body=None, prefer: str | None = None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(SUPABASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        raw = err.read()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = raw.decode("utf-8", "replace")
        return err.code, payload


def login(email: str, password: str) -> tuple[str, str]:
    status, data = request(
        "POST", "/auth/v1/token?grant_type=password",
        body={"email": email, "password": password},
    )
    if status != 200 or not isinstance(data, dict) or not data.get("access_token"):
        raise SystemExit(f"не удалось войти {email}: HTTP {status} {str(data)[:200]}")
    return data["access_token"], data["user"]["id"]


def rows(result) -> list:
    status, data = result
    if status not in (200, 201, 204):
        fail(f"неожиданный HTTP {status}: {str(data)[:240]}")
        return []
    return data if isinstance(data, list) else []


def insert(table: str, token: str, payload: dict) -> dict | None:
    result = rows(request("POST", f"/rest/v1/{table}", token, payload, "return=representation"))
    return result[0] if result else None


def delete(table: str, token: str, query: str) -> list:
    return rows(request("DELETE", f"/rest/v1/{table}?{query}", token, None, "return=representation"))


def patch(table: str, token: str, query: str, payload: dict) -> list:
    return rows(request("PATCH", f"/rest/v1/{table}?{query}", token, payload, "return=representation"))


def main() -> int:
    admin_email = os.environ.get("GDZ_ADMIN_EMAIL", "")
    user1_email = os.environ.get("GDZ_USER1_EMAIL", "")
    user2_email = os.environ.get("GDZ_USER2_EMAIL", "")
    password = os.environ.get("GDZ_TEST_PASSWORD", "")
    admin_pass = os.environ.get("GDZ_ADMIN_PASSWORD", password)
    if not all([admin_email, user1_email, user2_email, password]):
        print("нет тестовых аккаунтов — пропуск")
        return 0

    admin, admin_id = login(admin_email, admin_pass)
    user1, user1_id = login(user1_email, password)
    user2, user2_id = login(user2_email, password)
    print("вход: админ, user1, user2 — ок")

    try:
        # ---- отзывы ---------------------------------------------------------
        stamp = str(int(time.time() * 1000))
        review = insert("reviews", user1, {
            "task_id": "test:rls-" + stamp,
            "user_id": user1_id,
            "username": "rls-test",
            "rating": 5,
            "text": "тест rls: этот отзыв должен удалить только админ",
            "ai_status": "pending",
            "is_approved": False,
        })
        if not review:
            fail("не удалось создать тестовый отзыв")
        else:
            rid = review["id"]
            CREATED_REVIEWS.append(rid)
            if delete("reviews", user2, f"id=eq.{rid}"):
                fail("user2 смог удалить чужой отзыв")
            else:
                print("отзывы: чужое удаление запрещено — ок")
            if patch("reviews", user2, f"id=eq.{rid}", {"text": "взлом чужого отзыва"}):
                fail("user2 смог изменить чужой отзыв")
            else:
                print("отзывы: чужое изменение запрещено — ок")
            if not patch("reviews", admin, f"id=eq.{rid}", {"text": "проверено админом"}):
                fail("админ не смог изменить отзыв")
            else:
                print("отзывы: админ может изменять — ок")
            if len(delete("reviews", admin, f"id=eq.{rid}")) != 1:
                fail("админ не смог удалить отзыв")
            else:
                print("отзывы: админ может удалять — ок")
                CREATED_REVIEWS.remove(rid)

        # ---- комментарии к профилю -----------------------------------------
        comment = insert("profile_comments", user1, {
            "target_profile_id": user2_id,
            "author_id": user1_id,
            "text": "тест rls: комментарий",
        })
        if not comment:
            fail("не удалось создать тестовый комментарий")
        else:
            cid = comment["id"]
            CREATED_COMMENTS.append(cid)
            if delete("profile_comments", user2, f"id=eq.{cid}"):
                fail("владелец профиля смог удалить чужой комментарий")
            else:
                print("комментарии: чужое удаление запрещено — ок")
            if len(delete("profile_comments", admin, f"id=eq.{cid}")) != 1:
                fail("админ не смог удалить комментарий")
            else:
                print("комментарии: админ может удалять — ок")
                CREATED_COMMENTS.remove(cid)

        # ---- профили --------------------------------------------------------
        if delete("profiles", user2, f"id=eq.{user1_id}"):
            fail("user2 смог удалить чужой профиль")
        else:
            print("профили: чужое удаление запрещено — ок")
        if delete("profiles", user1, f"id=eq.{user1_id}"):
            fail("пользователь смог удалить собственный профиль")
        else:
            print("профили: удаление только админом — ок")
        if patch("profiles", user2, f"id=eq.{user1_id}", {"username": "взлом"}):
            fail("user2 смог изменить чужой профиль")
        else:
            print("профили: чужое изменение запрещено — ок")

        # ---- доска почёта ---------------------------------------------------
        post = insert("honor_board", admin, {
            "text": "тест rls: временная запись доски почёта",
        })
        if not post:
            fail("админ не смог создать запись доски почёта")
        else:
            pid = int(post["id"])
            CREATED_POSTS.append(pid)
            status, _ = request("POST", "/rest/v1/honor_board", user1, {
                "text": "пользователь не должен создать запись"
            }, "return=representation")
            if status in (200, 201):
                fail("обычный пользователь смог создать запись доски почёта")
            else:
                print("доска: создание только админом — ок")
            if delete("honor_board", user2, f"id=eq.{pid}"):
                fail("user2 смог удалить чужую запись доски почёта")
            else:
                print("доска: чужое удаление запрещено — ок")

            status, _ = request("POST", "/rest/v1/honor_likes", user1, {
                "post_id": pid, "user_id": user1_id,
            }, "return=representation")
            if status in (200, 201):
                fail("прямой insert в honor_likes не закрыт")
            else:
                print("лайки: прямой insert закрыт — ок")

            def toggle(_):
                return request("POST", "/rest/v1/rpc/honor_like", user1, {"p_id": pid})

            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(toggle, range(6)))
            bad = [r for r in results if r[0] != 200]
            if bad:
                fail(f"конкурентные honor_like вернули ошибки: {bad[:2]}")
            status, board = request("GET", f"/rest/v1/honor_board?id=eq.{pid}&select=likes", None)
            likes = board[0]["likes"] if status == 200 and board else None
            if likes != 0:
                fail(f"после 6 конкурентных переключений likes={likes}, ожидалось 0")
            else:
                print("лайки: 6 конкурентных переключений, счётчик 0 — ок")

            for _ in range(5):
                request("POST", "/rest/v1/rpc/honor_like", user1, {"p_id": pid})
            status, board = request("GET", f"/rest/v1/honor_board?id=eq.{pid}&select=likes", None)
            likes = board[0]["likes"] if status == 200 and board else None
            if likes != 1:
                fail(f"после 5 переключений likes={likes}, ожидалось 1")
            else:
                print("лайки: нечётное число переключений, счётчик 1 — ок")
            request("POST", "/rest/v1/rpc/honor_like", user1, {"p_id": pid})

            if len(delete("honor_board", admin, f"id=eq.{pid}")) != 1:
                fail("админ не смог удалить запись доски почёта")
            else:
                print("доска: админ может удалять — ок")
                CREATED_POSTS.remove(pid)

    finally:
        for rid in CREATED_REVIEWS:
            delete("reviews", admin, f"id=eq.{rid}")
        for cid in CREATED_COMMENTS:
            delete("profile_comments", admin, f"id=eq.{cid}")
        for pid in CREATED_POSTS:
            delete("honor_board", admin, f"id=eq.{pid}")

    print("ошибок:", len(ERRORS))
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
