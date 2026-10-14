import asyncio

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from app import scheduler
from app.config import Config
from app.db import Database

ADMIN = 1
CFG = Config("1:T", ADMIN, "", ":memory:", "Europe/Moscow", "127.0.0.1", 0)


class FakeBot:
    def __init__(self, fail: BaseException | None = None):
        self.sent: list[str] = []
        self.fail = fail

    async def send_message(self, chat_id, text, **kw):
        if self.fail:
            raise self.fail
        self.sent.append(text)


@pytest.fixture
async def db(monkeypatch):
    d = Database(":memory:", "Europe/Moscow")
    await d.connect()
    await d.set_allowed(ADMIN, True)
    await d.update_settings(ADMIN, {"notify_time": "00:00", "default_reminders": "0"})
    yield d
    await d.close()


async def add_daily(db, n=1, name="Sub"):
    for i in range(n):
        await db.create_sub(ADMIN, {
            "name": f"{name}{i}", "amount": 1.0, "currency": "RUB", "card_id": None, "anchor": "2020-01-01",
            "unit": "day", "every": 1, "reminders": None, "note": "", "active": 1,
        })


async def test_sends_once(db):
    await add_daily(db, 2)
    bot = FakeBot()
    await scheduler.tick(bot, db, CFG)
    await scheduler.tick(bot, db, CFG)
    assert len(bot.sent) == 1 and "Sub0" in bot.sent[0] and "Sub1" in bot.sent[0]


async def test_retry_after_failure(db):
    await add_daily(db)
    await scheduler.tick(FakeBot(fail=RuntimeError("network")), db, CFG)
    bot = FakeBot()
    await scheduler.tick(bot, db, CFG)
    assert len(bot.sent) == 1


async def test_cancel_unmarks(db):
    await add_daily(db)
    with pytest.raises(asyncio.CancelledError):
        await scheduler.tick(FakeBot(fail=asyncio.CancelledError()), db, CFG)
    bot = FakeBot()
    await scheduler.tick(bot, db, CFG)
    assert len(bot.sent) == 1


async def test_blocked_user_not_retried(db):
    await add_daily(db)
    err = TelegramForbiddenError(method=SendMessage(chat_id=ADMIN, text="x"), message="blocked")
    await scheduler.tick(FakeBot(fail=err), db, CFG)
    bot = FakeBot()
    await scheduler.tick(bot, db, CFG)
    assert bot.sent == []


async def test_long_digest_is_split(db):
    await add_daily(db, 80, name="X" * 60)
    bot = FakeBot()
    await scheduler.tick(bot, db, CFG)
    assert len(bot.sent) > 1 and all(len(t) <= 4096 for t in bot.sent)
    assert sum(t.count("•") for t in bot.sent) == 80


async def test_access_request_once(db):
    await db.touch_user(5, "Stranger")
    assert await db.mark_requested(5) is True
    assert await db.mark_requested(5) is False
