# subscription-reminder

Telegram-бот + Mini App: заранее напоминает, что скоро спишутся деньги за подписку.

- у каждого пользователя свои карты, подписки и настройки;
- подписки в любой валюте, период — каждые N дней/недель/месяцев/лет (31-е число не «съезжает»);
- напоминания за N дней (несколько штук) — по умолчанию для пользователя и своими для подписки, в выбранное время и часовом поясе;
- сводка «в месяц ≈» по каждой валюте;
- приватный доступ: админ из `ADMIN_ID`, остальных пускаешь сам.

Стек: Python 3.12, aiogram 3, FastAPI, SQLite. Фронт на чистом HTML/JS без сборки. Один процесс, около 180 МБ RAM (львиная доля — модели aiogram).

## Доступ

- Незнакомец пишет `/start` → получает свой ID, тебе приходит запрос с кнопками «Разрешить / Отклонить».
- `/users` — список, `/allow <id>`, `/deny <id>` — выдать или забрать доступ (команды работают только для админа).
- API Mini App проверяет подпись `initData` (HMAC от токена бота) и тот же список доступа.

## Команды бота

`/start` — открыть приложение, `/next` — ближайшие списания, `/id` — свой ID.

## Деплой

```sh
cp .env.example .env   # BOT_TOKEN, ADMIN_ID, DOMAIN, WEBAPP_URL
docker compose up -d --build
```

Сервер, где уже есть Caddy в docker-сети (например, `pickerwheel_default`):

```sh
PROXY_NETWORK=pickerwheel_default docker compose -f docker-compose.shared.yml -p subs up -d --build
# в Caddyfile:  <домен> { reverse_proxy subs-app:8080 }
```

База — `/data/bot.sqlite3` в volume `app-data`. Бэкап:
`docker compose cp app:/data/bot.sqlite3 ./backup.sqlite3`.

## Разработка

```sh
uv sync && uv run pytest
```
