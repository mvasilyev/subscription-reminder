"""Проверка initData из Telegram Mini App (HMAC-SHA256 по токену бота)."""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

MAX_AGE = 24 * 3600


def validate_init_data(init_data: str, bot_token: str, now: float | None = None) -> dict | None:
    """Возвращает объект user из initData или None, если подпись неверна или устарела."""
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received = pairs.pop("hash", None)
    if not received:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
        user = json.loads(pairs["user"])
    except (KeyError, ValueError):
        return None
    if (now or time.time()) - auth_date > MAX_AGE:
        return None
    return user


def is_allowed(user: dict | None, user_id: int, admin_id: int) -> bool:
    return user_id == admin_id or bool(user and user["allowed"])
