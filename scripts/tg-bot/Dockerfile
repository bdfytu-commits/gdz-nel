# ГДЗ НЭЛ — телеграм-бот (Ф18)
#
# Сборка:
#   docker build -t gdz-nel-bot scripts/tg-bot
#
# Запуск (токен берётся из .env, в образ секреты не попадают):
#   docker run --rm --env-file .env \
#     -e GDZ_DATA_DIR=/app/data \
#     -v "$PWD/app/data:/app/data:ro" \
#     gdz-nel-bot
#
# Режим «пост раз в сутки»:
#   docker run --rm --env-file .env -e GDZ_DATA_DIR=/app/data \
#     -v "$PWD/app/data:/app/data:ro" gdz-nel-bot python bot.py --daily-post

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /bot

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]
