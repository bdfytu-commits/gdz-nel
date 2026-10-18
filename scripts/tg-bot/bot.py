#!/usr/bin/env python3
"""
ГДЗ НЭЛ — телеграм-бот канала @gdz_nel (Ф18).

Что умеет:
  /start  — приветствие и кнопка «Открыть ГДЗ»
  /help   — как пользоваться
  /task   — случайная задача из приложения (в чат)
  /post   — отправить случайную задачу в канал @gdz_nel (только админы канала)
  /subject <предмет> — случайная задача по предмету (math, russian, ...)

Токен и канал читаются из .env (никакого хардкода):
  TELEGRAM_BOT_TOKEN=...
  TELEGRAM_CHANNEL_ID=@gdz_nel

Ежедневный постинг (по желанию):  python bot.py --daily-post  (раз в сутки)

Запуск:
  cd scripts/tg-bot
  pip install -r requirements.txt
  python bot.py
"""

import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
SITE = "https://bdfytu-commits.github.io/gdz-nel"
APP_URL = SITE + "/app/"

load_dotenv(ROOT / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")

DATA_DIR = Path(os.environ.get("GDZ_DATA_DIR") or (ROOT / "app" / "data"))

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "@gdz_nel")

SUBJECT_TITLES = {
    "math": "Математика",
    "algebra": "Алгебра",
    "russian": "Русский язык",
    "literature": "Литература",
    "english": "Английский язык",
    "biology": "Биология",
    "history": "История",
    "social": "Обществознание",
}


# ---------------------------------------------------------------------------
# данные приложения
# ---------------------------------------------------------------------------

def load_catalog() -> dict:
    try:
        return json.loads((DATA_DIR / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def book_index() -> dict:
    """book_id -> {grade, subject, title}"""
    index = {}
    for grade in load_catalog().get("grades", []):
        for subject in grade.get("subjects", []):
            for book in subject.get("textbooks", []):
                index[book["id"]] = {
                    "grade": grade["id"],
                    "subject": subject["id"],
                    "subjectTitle": subject.get("title", subject["id"]),
                    "title": book.get("title", book["id"]),
                }
    return index


def all_books() -> list:
    books = []
    for path in sorted(DATA_DIR.glob("*/*.json")):
        if path.name in ("catalog.json", "stats.json"):
            continue
        books.append(path)
    return books


def pick_task(subject: str | None = None):
    books = all_books()
    random.shuffle(books)
    for path in books:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        book_id = data.get("textbook") or path.stem
        info = book_index().get(book_id)
        book_subject = data.get("subject") or (info or {}).get("subject")
        if subject and book_subject != subject:
            continue
        tasks = [t for t in data.get("tasks", []) if (t.get("condition") or "").strip()]
        if not tasks:
            continue
        task = random.choice(tasks)
        return {
            "book": book_id,
            "info": info or {},
            "subject": book_subject or "",
            "task": task,
            "path": path,
        }
    return None


def clamp(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut + "…"


def task_message(item: dict) -> str:
    info = item["info"]
    task = item["task"]
    subject = info.get("subjectTitle") or SUBJECT_TITLES.get(item["subject"], item["subject"])

    lines = ["📘 " + clamp(subject + " · " + (info.get("title") or item["book"]), 90),
             "№ " + str(task.get("number", "?"))]

    if task.get("section"):
        lines.append("§ " + clamp(task["section"], 70))

    condition = clamp(task.get("condition", ""), 320)
    if condition:
        lines.append("")
        lines.append("Условие: " + condition)

    answer = clamp(task.get("answer", ""), 200)
    if answer:
        lines.append("")
        lines.append("Ответ: " + answer)

    lines.append("")
    lines.append("Полное решение — на сайте.")
    return "\n".join(lines)


def task_keyboard(item: dict) -> InlineKeyboardMarkup:
    info = item["info"]
    task = item["task"]
    url = APP_URL
    if info.get("grade") and info.get("subject"):
        url += "#/" + str(info["grade"]) + "/" + str(info["subject"]) + "/" + \
            str(item["book"]) + "/" + str(task.get("number", ""))
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Открыть решение", url=url)
    ]])


# ---------------------------------------------------------------------------
# бот
# ---------------------------------------------------------------------------

if not TOKEN:
    print("нет TELEGRAM_BOT_TOKEN — добавь его в .env (см. .env.example)", file=sys.stderr)
    sys.exit(1)

bot = Bot(token=TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Это бот ГДЗ НЭЛ.\n\n"
        "• /task — случайная задача с решением\n"
        "• /subject math — задача по предмету\n"
        "• /help — все команды\n\n"
        "Полные решения — в приложении.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Открыть ГДЗ НЭЛ", url=SITE)
        ]]),
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды бота:\n"
        "/task — случайная задача из приложения\n"
        "/subject <предмет> — задача по предмету\n"
        "    предметы: " + ", ".join(SUBJECT_TITLES.keys()) + "\n"
        "/post — случайная задача в канал " + CHANNEL_ID + " (для админов)\n\n"
        "Задания и решения — только для самопроверки.",
    )


async def send_task(message: Message, subject: str | None = None) -> None:
    item = pick_task(subject)
    if not item:
        await message.answer("Не нашёл задач — данные приложения ещё не собраны.")
        return
    await message.answer(
        task_message(item),
        reply_markup=task_keyboard(item),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


@dp.message(Command("task"))
async def cmd_task(message: Message) -> None:
    await send_task(message)


@dp.message(Command("subject"))
async def cmd_subject(message: Message, command: CommandObject) -> None:
    subject = (command.args or "").strip().lower()
    if subject not in SUBJECT_TITLES:
        await message.answer("Предметы: " + ", ".join(SUBJECT_TITLES.keys()))
        return
    await send_task(message, subject)


@dp.message(Command("post"))
async def cmd_post(message: Message) -> None:
    item = pick_task()
    if not item:
        await message.answer("Не нашёл задач для поста.")
        return
    try:
        await bot.send_message(
            CHANNEL_ID,
            task_message(item),
            reply_markup=task_keyboard(item),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except Exception as err:  # noqa: BLE001 — покажем админу причину
        await message.answer("Не получилось опубликовать: " + str(err)[:200])
        return
    await message.answer("Опубликовал в " + CHANNEL_ID)


@dp.message(F.text)
async def fallback(message: Message) -> None:
    await message.answer("Не понял команду. /help — список.")


async def daily_post_once(keyword: str | None = None) -> None:
    item = pick_task()
    if not item:
        print("нет данных для поста")
        return
    await bot.send_message(
        CHANNEL_ID,
        task_message(item),
        reply_markup=task_keyboard(item),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    print("пост отправлен:", item["book"], item["task"].get("number"))


async def main() -> None:
    parser = argparse.ArgumentParser(description="ГДЗ НЭЛ — телеграм-бот")
    parser.add_argument("--daily-post", action="store_true",
                        help="не слушать команды, а раз в сутки постить задачу в канал")
    parser.add_argument("--once", action="store_true",
                        help="отправить один пост в канал и выйти (для cron)")
    args = parser.parse_args()

    if args.once:
        await daily_post_once()
        await bot.session.close()
        return

    if args.daily_post:
        while True:
            try:
                await daily_post_once()
            except Exception as err:  # noqa: BLE001
                print("ошибка постинга:", err)
            await asyncio.sleep(24 * 3600)

    print("бот запущен, канал:", CHANNEL_ID)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
