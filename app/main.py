import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .api import create_api
from .bot import create_router, setup_bot
from .config import load_config
from .db import Database
from .scheduler import run_scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    db = Database(cfg.db_path, cfg.default_tz)
    await db.connect()
    await db.set_allowed(cfg.admin_id, True)

    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(create_router(db, cfg))
    await setup_bot(bot, cfg)

    server = uvicorn.Server(uvicorn.Config(create_api(db, cfg), host=cfg.host, port=cfg.port, log_level="warning",
                                           proxy_headers=True, forwarded_allow_ips="*"))
    try:
        # uvicorn ловит SIGTERM и завершается — вслед за ним гасим бота и планировщик
        tasks = [
            asyncio.create_task(server.serve()),
            asyncio.create_task(dp.start_polling(bot, handle_signals=False)),
            asyncio.create_task(run_scheduler(bot, db, cfg)),
        ]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
