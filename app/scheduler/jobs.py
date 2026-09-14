from __future__ import annotations

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.digest import DigestService
from app.services.extractor import ExtractionService
from app.services.reminders import ReminderService
from app.services.store import Store

logger = logging.getLogger(__name__)


class JobManager:
    def __init__(self, bot: Bot, store: Store, digest: DigestService, reminders: ReminderService, extractor: ExtractionService) -> None:
        self.bot = bot
        self.store = store
        self.digest = digest
        self.reminders = reminders
        self.extractor = extractor
        self.scheduler = AsyncIOScheduler(timezone="UTC")

    async def digest_tick(self) -> None:
        now_utc = datetime.now(UTC)
        for project in await self.store.list_projects():
            try:
                local_now = now_utc.astimezone(ZoneInfo(project.timezone))
                hour, minute = map(int, project.digest_time.split(":"))
                scheduled_passed = (local_now.hour, local_now.minute) >= (hour, minute)
                last_local_date = None
                if project.last_digest_at:
                    last = project.last_digest_at
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=UTC)
                    last_local_date = last.astimezone(ZoneInfo(project.timezone)).date()
                if scheduled_passed and last_local_date != local_now.date():
                    text = await self.digest.build(project, now_utc)
                    await self.bot.send_message(project.chat_id, text, message_thread_id=project.digest_thread_id, disable_web_page_preview=True)
                    await self.store.update_project_settings(project.chat_id, last_digest_at=now_utc)
            except Exception:
                logger.exception("Daily digest failed", extra={"chat_id": project.chat_id})

    async def reminder_tick(self) -> None:
        for project in await self.store.list_projects():
            try:
                await self.reminders.send_due(project)
            except Exception:
                logger.exception("Reminder scan failed", extra={"chat_id": project.chat_id})

    async def retry_analysis(self) -> None:
        try:
            await self.extractor.retry_pending(limit=20)
        except Exception:
            logger.exception("Pending analysis retry failed")

    async def retention_cleanup(self) -> None:
        try:
            await self.store.cleanup_old_messages()
        except Exception:
            logger.exception("Retention cleanup failed")

    def start(self) -> None:
        self.scheduler.add_job(self.digest_tick, "interval", minutes=1, max_instances=1, coalesce=True)
        self.scheduler.add_job(self.reminder_tick, "interval", hours=1, max_instances=1, coalesce=True)
        self.scheduler.add_job(self.retry_analysis, "interval", minutes=10, max_instances=1, coalesce=True)
        self.scheduler.add_job(self.retention_cleanup, "interval", hours=24, max_instances=1, coalesce=True)
        self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
