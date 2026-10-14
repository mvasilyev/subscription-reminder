FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
RUN pip install "aiogram>=3.13,<4" "fastapi>=0.115,<1" "uvicorn>=0.32,<1" "aiosqlite>=0.20,<1" "tzdata>=2024.1"
COPY app ./app
COPY webapp ./webapp
ENV DB_PATH=/data/bot.sqlite3
VOLUME /data
EXPOSE 8080
CMD ["python", "-m", "app.main"]
