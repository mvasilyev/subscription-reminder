"""Раз в минуту проверяет, кому пора отправить напоминания."""
import asyncio
import logging
from datetime import timedelta
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from .bot import app_keyboard
from .config import Config
from .db import Database
from .service import due_reminders, fmt_money, local_now, when_text

log = logging.getLogger(__name__)


async def tick(bot: Bot, db: Database, cfg: Config) -> None:
    for user in await db.allowed_users(cfg.admin_id):
        now = local_now(user)
        due = due_reminders(user, await db.list_subs(user["id"]), now)
        fresh = []
        for sub, charge, left in due:
            if await db.mark_sent(sub["id"], charge.isoformat(), left):
                fresh.append((sub, charge, left))
        if not fresh:
            continue
        cards = {c["id"]: c for c in await db.list_cards(user["id"])}
        lines = ["🔔 <b>Скоро списания</b>"]
        for sub, charge, left in sorted(fresh, key=lambda x: x[1]):
            card = cards.get(sub["card_id"])
            card_txt = ""
            if card:
                card_txt = f"\n   💳 {escape(card['name'])}" + (f" •{card['last4']}" if card["last4"] else "")
            lines.append(
                f"• <b>{escape(sub['name'])}</b> — {fmt_money(sub['amount'], sub['currency'])}, "
                f"{when_text(left)} ({charge:%d.%m}){card_txt}"
            )
        try:
            await bot.send_message(user["id"], "\n".join(lines), reply_markup=app_keyboard(cfg))
        except TelegramForbiddenError:
            log.warning("user %s blocked the bot", user["id"])
        except Exception:
            log.exception("send failed for %s, will retry", user["id"])
            for sub, charge, left in fresh:
                await db.unmark_sent(sub["id"], charge.isoformat(), left)


async def run_scheduler(bot: Bot, db: Database, cfg: Config, interval: int = 60) -> None:
    while True:
        try:
            await tick(bot, db, cfg)
            await db.prune_sent((local_now({"tz": cfg.default_tz}).date() - timedelta(days=120)).isoformat())
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(interval)
