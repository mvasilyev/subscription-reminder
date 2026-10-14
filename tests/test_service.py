from datetime import datetime
from zoneinfo import ZoneInfo

from app.service import due_reminders

USER = {"tz": "Europe/Moscow", "notify_time": "10:00", "default_reminders": "3,1"}


def sub(**kw):
    return {"id": 1, "anchor": "2026-10-17", "unit": "month", "every": 1, "reminders": None, "active": 1, **kw}


def at(h: int, day: int = 14):
    return datetime(2026, 10, day, h, 0, tzinfo=ZoneInfo("Europe/Moscow"))


def test_default_reminder_after_notify_time():
    assert [(s["id"], d.isoformat(), left) for s, d, left in due_reminders(USER, [sub()], at(11))] == [(1, "2026-10-17", 3)]


def test_not_before_notify_time():
    assert due_reminders(USER, [sub()], at(9)) == []


def test_custom_reminders_override_default():
    assert due_reminders(USER, [sub(reminders="7")], at(11)) == []
    assert len(due_reminders(USER, [sub(reminders="3,0")], at(11))) == 1


def test_day_of_charge():
    assert due_reminders(USER, [sub(reminders="0")], at(11, day=17))[0][2] == 0


def test_inactive_skipped():
    assert due_reminders(USER, [sub(active=0)], at(11)) == []
