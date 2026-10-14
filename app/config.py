import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_id: int
    webapp_url: str
    db_path: str
    default_tz: str
    host: str
    port: int


def load_config() -> Config:
    token = os.environ.get("BOT_TOKEN", "").strip()
    admin = os.environ.get("ADMIN_ID", "").strip()
    if not token or not admin:
        raise SystemExit("BOT_TOKEN и ADMIN_ID обязательны (см. .env.example)")
    return Config(
        bot_token=token,
        admin_id=int(admin),
        webapp_url=os.environ.get("WEBAPP_URL", "").strip(),
        db_path=os.environ.get("DB_PATH", "data/bot.sqlite3"),
        default_tz=os.environ.get("DEFAULT_TZ", "Europe/Moscow"),
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8080")),
    )
