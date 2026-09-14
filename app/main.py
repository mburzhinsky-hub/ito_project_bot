from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import build_router
from app.config import get_settings
from app.db.base import Base, make_engine, make_session_factory
from app.services.digest import DigestService
from app.services.extractor import ExtractionService
from app.services.llm import OpenAIExtractorClient
from app.services.reminders import ReminderService
from app.services.store import Store
from app.scheduler.jobs import JobManager


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    engine = make_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = make_session_factory(engine)
    store = Store(sessions, settings)
    llm = OpenAIExtractorClient(settings)
    extractor = ExtractionService(store, llm)
    digest = DigestService(store)

    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    reminders = ReminderService(store, bot)
    jobs = JobManager(bot, store, digest, reminders, extractor)
    dp = Dispatcher()
    dp.include_router(build_router(store, extractor, digest, settings))

    jobs.start()
    logging.getLogger(__name__).info("Project Assistant starting in long-polling mode")
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        jobs.shutdown()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
