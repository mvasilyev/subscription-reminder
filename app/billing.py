"""Календарная математика: следующие даты списаний и месячный эквивалент."""
import calendar
from datetime import date, timedelta

UNITS = ("day", "week", "month", "year")


def nth_charge(anchor: date, unit: str, every: int, k: int) -> date:
    """k-е списание после anchor (k=0 — сам anchor). Для месяцев день
    прижимается к концу месяца, но не «съезжает»: 31.01 → 28.02 → 31.03."""
    if unit == "day":
        return anchor + timedelta(days=every * k)
    if unit == "week":
        return anchor + timedelta(weeks=every * k)
    months = every * k * (12 if unit == "year" else 1)
    total = anchor.month - 1 + months
    y, m = anchor.year + total // 12, total % 12 + 1
    return date(y, m, min(anchor.day, calendar.monthrange(y, m)[1]))


def next_charge(anchor: date, unit: str, every: int, today: date) -> date:
    """Ближайшее списание в день today или позже."""
    if anchor >= today:
        return anchor
    days = (today - anchor).days
    # максимальная длина периода, чтобы оценка k не перескочила вперёд
    longest = {"day": 1, "week": 7, "month": 31, "year": 366}[unit] * every
    k = max(0, days // longest - 1)
    while nth_charge(anchor, unit, every, k) < today:
        k += 1
    return nth_charge(anchor, unit, every, k)


def monthly_equivalent(amount: float, unit: str, every: int) -> float:
    per_month = {"day": 365.25 / 12, "week": 365.25 / 12 / 7, "month": 1.0, "year": 1 / 12}[unit]
    return amount * per_month / every


def parse_reminders(raw: str | None) -> list[int] | None:
    if raw is None or raw == "":
        return None
    return sorted({int(x) for x in raw.split(",") if x.strip() != ""}, reverse=True)


def format_reminders(days: list[int] | None) -> str | None:
    if days is None:
        return None
    return ",".join(str(d) for d in sorted(set(days), reverse=True))
