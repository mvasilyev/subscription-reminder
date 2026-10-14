"""Общая логика поверх БД: ближайшие списания, сводка, какие напоминания пора слать."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .billing import monthly_equivalent, next_charge, parse_reminders

CURRENCY_SIGNS = {"RUB": "₽", "USD": "$", "EUR": "€", "KZT": "₸", "GBP": "£", "UAH": "₴", "GEL": "₾", "TRY": "₺"}


def fmt_money(amount: float, currency: str) -> str:
    text = f"{amount:,.2f}".replace(",", " ").removesuffix(".00")
    return f"{text} {CURRENCY_SIGNS.get(currency, currency)}"


def local_now(user: dict) -> datetime:
    return datetime.now(ZoneInfo(user["tz"]))


def effective_reminders(sub: dict, user: dict) -> list[int]:
    own = parse_reminders(sub["reminders"])
    return own if own is not None else (parse_reminders(user["default_reminders"]) or [])


def enrich(sub: dict, user: dict, today: date) -> dict:
    nxt = next_charge(date.fromisoformat(sub["anchor"]), sub["unit"], sub["every"], today)
    return {
        **sub,
        "active": bool(sub["active"]),
        "reminders": parse_reminders(sub["reminders"]),
        "effective_reminders": effective_reminders(sub, user),
        "next_charge": nxt.isoformat(),
        "days_left": (nxt - today).days,
    }


def monthly_summary(subs: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for s in subs:
        if s["active"]:
            totals[s["currency"]] = totals.get(s["currency"], 0) + monthly_equivalent(s["amount"], s["unit"], s["every"])
    return {k: round(v, 2) for k, v in sorted(totals.items())}


def due_reminders(user: dict, subs: list[dict], now: datetime) -> list[tuple[dict, date, int]]:
    """Напоминания, которые пора отправить сегодня (после notify_time в часовом поясе пользователя)."""
    hh, mm = map(int, user["notify_time"].split(":"))
    if now.time() < time(hh, mm):
        return []
    today = now.date()
    due = []
    for sub in subs:
        if not sub["active"]:
            continue
        anchor = date.fromisoformat(sub["anchor"])
        # «за N дней» может быть длиннее периода (ежедневная подписка, напоминание за 3 дня),
        # поэтому проверяем не ближайшее списание, а есть ли списание ровно через N дней
        for left in effective_reminders(sub, user):
            target = today + timedelta(days=left)
            if next_charge(anchor, sub["unit"], sub["every"], target) == target:
                due.append((sub, target, left))
    return due


def days_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "дня"
    return "дней"


def when_text(days_left: int) -> str:
    if days_left == 0:
        return "сегодня"
    if days_left == 1:
        return "завтра"
    return f"через {days_left} {days_word(days_left)}"
