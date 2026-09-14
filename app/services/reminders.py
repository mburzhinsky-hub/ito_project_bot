from __future__ import annotations

from datetime import UTC, datetime, timedelta
from html import escape

from aiogram import Bot

from app.db.models import ProjectChat
from app.services.store import Store
from app.services.text_utils import message_link


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ReminderService:
    def __init__(self, store: Store, bot: Bot) -> None:
        self.store = store
        self.bot = bot

    async def send_due(self, project: ProjectChat, now: datetime | None = None) -> int:
        if not project.reminders_enabled:
            return 0
        now_utc = now or datetime.now(UTC)
        sent = 0
        for task in await self.store.reminder_tasks(project.chat_id):
            if not task.deadline:
                continue
            deadline = _utc(task.deadline)
            if task.snoozed_until and _utc(task.snoozed_until) > now_utc:
                continue
            if task.last_reminded_at and now_utc - _utc(task.last_reminded_at) < timedelta(hours=12):
                continue
            hours_left = (deadline - now_utc).total_seconds() / 3600
            if hours_left > project.deadline_reminder_hours:
                continue
            prefix = "🔴 Просрочено" if hours_left < 0 else "⏰ Скоро дедлайн"
            link = message_link(project.chat_id, task.source_message_id, project.chat_username)
            suffix = f'\n<a href="{escape(link)}">Исходное сообщение</a>' if link else ""
            text = f"{prefix}: <b>{escape(task.title)}</b>{suffix}"
            destination = project.chat_id
            if project.private_reminders and task.assignee_id:
                user = await self.store.get_user(task.assignee_id)
                if user and user.dm_started:
                    destination = task.assignee_id
            try:
                await self.bot.send_message(destination, text)
                await self.store.mark_task_reminded(task.id, now_utc)
                sent += 1
            except Exception:
                if destination != project.chat_id:
                    await self.bot.send_message(project.chat_id, text, message_thread_id=task.source_thread_id)
                    await self.store.mark_task_reminded(task.id, now_utc)
                    sent += 1

        for question in await self.store.open_questions(project.chat_id):
            age = now_utc - _utc(question.asked_at)
            if age < timedelta(hours=project.unanswered_after_hours):
                continue
            if question.last_reminded_at and now_utc - _utc(question.last_reminded_at) < timedelta(hours=12):
                continue
            text = f"❓ Вопрос всё ещё без ответа: {escape(question.text[:400])}"
            destination = project.chat_id
            if project.private_reminders and question.addressee_id:
                user = await self.store.get_user(question.addressee_id)
                if user and user.dm_started:
                    destination = question.addressee_id
            try:
                await self.bot.send_message(destination, text)
                await self.store.mark_question_reminded(question.id, now_utc)
                sent += 1
            except Exception:
                if destination != project.chat_id:
                    await self.bot.send_message(project.chat_id, text, message_thread_id=question.source_thread_id)
                    await self.store.mark_question_reminded(question.id, now_utc)
                    sent += 1
        return sent
