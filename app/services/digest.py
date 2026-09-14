from __future__ import annotations

from datetime import UTC, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from app.db.models import ProjectChat, Question, Task
from app.services.store import Store
from app.services.text_utils import message_link


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _format_local(value: datetime | None, timezone: str) -> str:
    if value is None:
        return "—"
    return _utc(value).astimezone(ZoneInfo(timezone)).strftime("%d.%m %H:%M")


def _source_suffix(project: ProjectChat, message_id: int) -> str:
    link = message_link(project.chat_id, message_id, project.chat_username)
    return f' <a href="{escape(link)}">↗ сообщение</a>' if link else f" · msg #{message_id}"


class DigestService:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def _user_name(self, user_id: int | None, fallback: str = "?") -> str:
        if user_id is None:
            return fallback
        user = await self.store.get_user(user_id)
        return user.display_name if user else str(user_id)

    async def _task_line(self, task: Task, project: ProjectChat) -> str:
        assignee = task.assignee_display_name or await self._user_name(task.assignee_id, "Исполнитель не указан")
        creator = await self._user_name(task.creator_id, "неизвестно")
        deadline = _format_local(task.deadline, project.timezone) if task.deadline else "не указан"
        return (
            f"\n• <b>{escape(assignee)}</b> — {escape(task.title)}"
            f"\n  Поручил/инициировал: {escape(creator)}"
            f"\n  Дедлайн: {deadline}{_source_suffix(project, task.source_message_id)}"
        )

    async def build(self, project: ProjectChat, now: datetime | None = None) -> str:
        now_utc = now or datetime.now(UTC)
        since = now_utc - timedelta(hours=24)
        tasks = await self.store.open_tasks(project.chat_id)
        questions = await self.store.open_questions(project.chat_id)
        closed = await self.store.recently_closed_tasks(project.chat_id, since)
        decisions = await self.store.recent_decisions(project.chat_id, since)
        overdue, active = [], []
        for task in tasks:
            (overdue if task.deadline and _utc(task.deadline) < now_utc else active).append(task)
        stale = [q for q in questions if now_utc - _utc(q.asked_at) >= timedelta(hours=project.unanswered_after_hours)]

        if not overdue and not active and not stale and not closed and not decisions:
            return "📋 <b>Project Daily</b>\n\nСейчас нет задач, зависших вопросов или новых решений, требующих внимания."

        lines = ["📋 <b>Project Daily</b>"]
        if overdue:
            lines.append("\n🔴 <b>ПРОСРОЧЕНО</b>")
            for task in overdue[:10]:
                lines.append(await self._task_line(task, project))
        if active:
            lines.append("\n🟡 <b>В РАБОТЕ</b>")
            for task in active[:15]:
                lines.append(await self._task_line(task, project))
        if stale:
            lines.append("\n❓ <b>БЕЗ ОТВЕТА</b>")
            for q in stale[:10]:
                age_h = int((now_utc - _utc(q.asked_at)).total_seconds() // 3600)
                author = await self._user_name(q.author_id)
                addressee = await self._user_name(q.addressee_id)
                lines.append(f"\n• {escape(author)} → {escape(addressee)}: {escape(q.text[:300])}\n  Без ответа: {age_h} ч.{_source_suffix(project, q.source_message_id)}")
        if decisions:
            lines.append("\n🧭 <b>РЕШЕНИЯ ЗА 24 ЧАСА</b>")
            for d in decisions[:10]:
                lines.append(f"\n• {escape(d.text[:400])}{_source_suffix(project, d.source_message_id)}")
        if closed:
            lines.append("\n✅ <b>ЗАКРЫТО ЗА 24 ЧАСА</b>")
            for task in closed[:10]:
                lines.append(f"\n• {escape(task.title)}")
        return "\n".join(lines)
