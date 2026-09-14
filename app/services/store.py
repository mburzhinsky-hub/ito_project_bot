from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.db.models import Decision, MessageRecord, ProjectChat, Question, Task, TelegramUser
from app.services.state_rules import apply_task_status, reply_answers_question
from app.services.text_utils import fingerprint, similar


class Store:
    def __init__(self, session_factory: async_sessionmaker, settings: Settings) -> None:
        self.sessions = session_factory
        self.settings = settings

    async def healthcheck(self) -> bool:
        async with self.sessions() as session:
            await session.execute(text("SELECT 1"))
        return True

    async def ensure_project(self, chat_id: int, title: str, chat_username: str | None = None, thread_id: int | None = None, activate: bool = False) -> ProjectChat:
        async with self.sessions() as session:
            project = await session.get(ProjectChat, chat_id)
            if project is None:
                project = ProjectChat(
                    chat_id=chat_id,
                    title=title or "Project",
                    is_active=activate,
                    chat_username=chat_username,
                    timezone=self.settings.default_timezone,
                    digest_time=self.settings.default_digest_time,
                    unanswered_after_hours=self.settings.unanswered_question_after_hours,
                    deadline_reminder_hours=self.settings.deadline_reminder_hours,
                    digest_thread_id=thread_id,
                )
                session.add(project)
            else:
                project.title = title or project.title
                project.chat_username = chat_username or project.chat_username
                if activate:
                    project.is_active = True
                    if thread_id is not None and project.digest_thread_id is None:
                        project.digest_thread_id = thread_id
            await session.commit()
            await session.refresh(project)
            return project

    async def get_project(self, chat_id: int) -> ProjectChat | None:
        async with self.sessions() as session:
            project = await session.get(ProjectChat, chat_id)
            return project if project and project.is_active else None

    async def list_projects(self) -> list[ProjectChat]:
        async with self.sessions() as session:
            stmt = select(ProjectChat).where(ProjectChat.is_active.is_(True))
            return list((await session.scalars(stmt)).all())

    async def update_project_settings(self, chat_id: int, **updates) -> ProjectChat | None:
        async with self.sessions() as session:
            project = await session.get(ProjectChat, chat_id)
            if project is None:
                return None
            for key, value in updates.items():
                if hasattr(project, key):
                    setattr(project, key, value)
            await session.commit()
            await session.refresh(project)
            return project

    async def upsert_user(self, telegram_user_id: int, username: str | None, display_name: str, dm_started: bool | None = None) -> TelegramUser:
        async with self.sessions() as session:
            user = await session.get(TelegramUser, telegram_user_id)
            if user is None:
                user = TelegramUser(
                    telegram_user_id=telegram_user_id,
                    username=username,
                    display_name=display_name,
                    dm_started=bool(dm_started),
                )
                session.add(user)
            else:
                user.username = username
                user.display_name = display_name
                if dm_started is not None:
                    user.dm_started = dm_started
            await session.commit()
            await session.refresh(user)
            return user

    async def get_user(self, telegram_user_id: int) -> TelegramUser | None:
        async with self.sessions() as session:
            return await session.get(TelegramUser, telegram_user_id)

    async def get_task(self, task_id: int) -> Task | None:
        async with self.sessions() as session:
            return await session.get(Task, task_id)

    async def save_message(self, *, chat_id: int, message_id: int, thread_id: int | None, sender_id: int | None, sender_username: str | None, sender_display_name: str, sent_at: datetime, text_value: str, reply_to_message_id: int | None, mentions: list[str], entities: list[dict], should_analyze: bool) -> MessageRecord:
        async with self.sessions() as session:
            existing = await session.scalar(select(MessageRecord).where(MessageRecord.chat_id == chat_id, MessageRecord.message_id == message_id))
            if existing:
                return existing
            record = MessageRecord(
                chat_id=chat_id,
                message_id=message_id,
                thread_id=thread_id,
                sender_id=sender_id,
                sender_username=sender_username,
                sender_display_name=sender_display_name,
                sent_at=sent_at,
                text=text_value,
                reply_to_message_id=reply_to_message_id,
                mentions_json=json.dumps(mentions, ensure_ascii=False),
                entities_json=json.dumps(entities, ensure_ascii=False),
                analysis_status="pending" if should_analyze else "skipped",
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def mark_message_analysis(self, record_id: int, status: str) -> None:
        async with self.sessions() as session:
            record = await session.get(MessageRecord, record_id)
            if record:
                record.analysis_status = status
                record.analysis_attempts += 1
                if status == "done":
                    record.analyzed_at = datetime.now(UTC)
                await session.commit()

    async def get_pending_messages(self, limit: int = 25) -> list[MessageRecord]:
        async with self.sessions() as session:
            stmt = select(MessageRecord).where(MessageRecord.analysis_status.in_(["pending", "failed"])).order_by(MessageRecord.sent_at).limit(limit)
            return list((await session.scalars(stmt)).all())

    async def recent_messages(self, chat_id: int, before_message_id: int, limit: int = 20) -> list[MessageRecord]:
        async with self.sessions() as session:
            stmt = select(MessageRecord).where(MessageRecord.chat_id == chat_id, MessageRecord.message_id <= before_message_id).order_by(MessageRecord.sent_at.desc()).limit(limit)
            rows = list((await session.scalars(stmt)).all())
            rows.reverse()
            return rows

    async def known_users_for_chat(self, chat_id: int, limit: int = 500) -> list[dict]:
        async with self.sessions() as session:
            stmt = select(MessageRecord).where(MessageRecord.chat_id == chat_id, MessageRecord.sender_id.is_not(None)).order_by(MessageRecord.sent_at.desc()).limit(limit)
            rows = list((await session.scalars(stmt)).all())
        by_id: dict[int, dict] = {}
        for row in rows:
            if row.sender_id is None or row.sender_id in by_id:
                continue
            by_id[row.sender_id] = {
                "telegram_user_id": row.sender_id,
                "username": row.sender_username,
                "display_name": row.sender_display_name,
            }
        return list(by_id.values())

    async def open_tasks(self, chat_id: int, assignee_id: int | None = None) -> list[Task]:
        async with self.sessions() as session:
            stmt = select(Task).where(Task.chat_id == chat_id, Task.status.in_(["candidate", "open", "in_progress", "waiting"]))
            if assignee_id is not None:
                stmt = stmt.where(Task.assignee_id == assignee_id)
            stmt = stmt.order_by(Task.deadline.is_(None), Task.deadline, Task.detected_at)
            return list((await session.scalars(stmt)).all())

    async def recently_closed_tasks(self, chat_id: int, since: datetime) -> list[Task]:
        async with self.sessions() as session:
            stmt = select(Task).where(Task.chat_id == chat_id, Task.status == "done", Task.completed_at.is_not(None), Task.completed_at >= since).order_by(Task.completed_at.desc())
            return list((await session.scalars(stmt)).all())

    async def open_questions(self, chat_id: int) -> list[Question]:
        async with self.sessions() as session:
            stmt = select(Question).where(Question.chat_id == chat_id, Question.status == "open").order_by(Question.asked_at)
            return list((await session.scalars(stmt)).all())

    async def create_or_merge_task(self, extracted, source_thread_id: int | None, fallback_deadline=None) -> Task | None:
        if extracted.confidence < 0.55:
            return None
        async with self.sessions() as session:
            if extracted.target_task_id:
                target = await session.get(Task, extracted.target_task_id)
                if target and target.chat_id == extracted.chat_id:
                    if extracted.title:
                        target.title = extracted.title[:500]
                    target.description = extracted.description or target.description
                    target.assignee_id = extracted.assignee_id or target.assignee_id
                    target.assignee_display_name = extracted.assignee_display_name or target.assignee_display_name
                    target.deadline = extracted.deadline or target.deadline or fallback_deadline
                    if extracted.status != target.status:
                        apply_task_status(target, extracted.status)
                    await session.commit()
                    await session.refresh(target)
                    return target
            if extracted.operation in {"complete", "cancel", "update"}:
                return None
            existing = await session.scalar(select(Task).where(Task.chat_id == extracted.chat_id, Task.fingerprint == fingerprint(extracted.title), Task.status.in_(["candidate", "open", "in_progress", "waiting"])))
            if existing:
                return existing
            candidates = list((await session.scalars(select(Task).where(Task.chat_id == extracted.chat_id, Task.status.in_(["candidate", "open", "in_progress", "waiting"])).order_by(Task.detected_at.desc()).limit(50))).all())
            for candidate in candidates:
                if candidate.assignee_id == extracted.assignee_id and similar(candidate.title, extracted.title):
                    candidate.deadline = extracted.deadline or candidate.deadline or fallback_deadline
                    candidate.confidence = max(candidate.confidence, extracted.confidence)
                    await session.commit()
                    await session.refresh(candidate)
                    return candidate
            source = await session.scalar(select(MessageRecord).where(MessageRecord.chat_id == extracted.chat_id, MessageRecord.message_id == extracted.source_message_id))
            status = "candidate" if extracted.confidence < 0.72 else extracted.status
            task = Task(
                chat_id=extracted.chat_id,
                source_message_id=extracted.source_message_id,
                source_thread_id=source_thread_id,
                title=extracted.title.strip()[:500],
                description=extracted.description,
                creator_id=extracted.creator_id,
                assignee_id=extracted.assignee_id,
                assignee_display_name=extracted.assignee_display_name,
                created_at=source.sent_at if source else datetime.now(UTC),
                deadline=extracted.deadline or fallback_deadline,
                status=status,
                confidence=extracted.confidence,
                extraction_reason=extracted.extraction_reason,
                fingerprint=fingerprint(extracted.title),
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return task

    async def complete_or_cancel_task(self, chat_id: int, task_id: int, target_status: str, at: datetime | None = None) -> Task | None:
        async with self.sessions() as session:
            task = await session.get(Task, task_id)
            if not task or task.chat_id != chat_id or not apply_task_status(task, target_status, at):
                return None
            await session.commit()
            await session.refresh(task)
            return task

    async def snooze_task(self, chat_id: int, task_id: int, until: datetime) -> Task | None:
        async with self.sessions() as session:
            task = await session.get(Task, task_id)
            if not task or task.chat_id != chat_id:
                return None
            task.snoozed_until = until
            await session.commit()
            await session.refresh(task)
            return task

    async def create_or_resolve_question(self, extracted, source_thread_id: int | None) -> Question | None:
        if extracted.confidence < 0.58:
            return None
        async with self.sessions() as session:
            if extracted.target_question_id:
                target = await session.get(Question, extracted.target_question_id)
                if target and target.chat_id == extracted.chat_id:
                    if extracted.operation == "answer":
                        target.status = "answered"
                        target.answered_at = datetime.now(UTC)
                        target.answer_message_id = extracted.source_message_id
                    elif extracted.operation == "cancel":
                        target.status = "cancelled"
                    await session.commit()
                    await session.refresh(target)
                    return target
            if extracted.operation != "create":
                return None
            fp = fingerprint(extracted.text)
            existing = await session.scalar(select(Question).where(Question.chat_id == extracted.chat_id, Question.fingerprint == fp, Question.status == "open"))
            if existing:
                return existing
            source = await session.scalar(select(MessageRecord).where(MessageRecord.chat_id == extracted.chat_id, MessageRecord.message_id == extracted.source_message_id))
            question = Question(
                chat_id=extracted.chat_id,
                source_message_id=extracted.source_message_id,
                source_thread_id=source_thread_id,
                author_id=extracted.author_id,
                addressee_id=extracted.addressee_id,
                text=extracted.text,
                asked_at=source.sent_at if source else datetime.now(UTC),
                confidence=extracted.confidence,
                fingerprint=fp,
            )
            session.add(question)
            await session.flush()
            reply_stmt = select(MessageRecord).where(MessageRecord.chat_id == extracted.chat_id, MessageRecord.reply_to_message_id == extracted.source_message_id, MessageRecord.message_id != extracted.source_message_id).order_by(MessageRecord.sent_at)
            if extracted.addressee_id is not None:
                reply_stmt = reply_stmt.where(MessageRecord.sender_id == extracted.addressee_id)
            reply = await session.scalar(reply_stmt)
            if reply:
                question.status = "answered"
                question.answered_at = reply.sent_at
                question.answer_message_id = reply.message_id
            await session.commit()
            await session.refresh(question)
            return question

    async def resolve_direct_reply(self, chat_id: int, sender_id: int | None, reply_to_message_id: int | None, answer_message_id: int, answered_at: datetime | None = None) -> Question | None:
        if reply_to_message_id is None:
            return None
        async with self.sessions() as session:
            question = await session.scalar(select(Question).where(Question.chat_id == chat_id, Question.source_message_id == reply_to_message_id, Question.status == "open"))
            if question and reply_answers_question(question, sender_id, reply_to_message_id):
                question.status = "answered"
                question.answered_at = answered_at or datetime.now(UTC)
                question.answer_message_id = answer_message_id
                await session.commit()
                await session.refresh(question)
                return question
        return None

    async def add_decision(self, chat_id: int, source_message_id: int, text_value: str, confidence: float) -> Decision | None:
        if confidence < 0.7:
            return None
        async with self.sessions() as session:
            existing = await session.scalar(select(Decision).where(Decision.chat_id == chat_id, Decision.source_message_id == source_message_id, Decision.text == text_value))
            if existing:
                return existing
            decision = Decision(chat_id=chat_id, source_message_id=source_message_id, text=text_value, confidence=confidence)
            session.add(decision)
            await session.commit()
            await session.refresh(decision)
            return decision

    async def recent_decisions(self, chat_id: int, since: datetime) -> list[Decision]:
        async with self.sessions() as session:
            stmt = select(Decision).where(Decision.chat_id == chat_id, Decision.decided_at >= since).order_by(Decision.decided_at.desc())
            return list((await session.scalars(stmt)).all())

    async def reminder_tasks(self, chat_id: int) -> list[Task]:
        async with self.sessions() as session:
            stmt = select(Task).where(Task.chat_id == chat_id, Task.status.in_(["open", "in_progress", "waiting"]), Task.deadline.is_not(None)).order_by(Task.deadline)
            return list((await session.scalars(stmt)).all())

    async def mark_task_reminded(self, task_id: int, when: datetime) -> None:
        async with self.sessions() as session:
            task = await session.get(Task, task_id)
            if task:
                task.last_reminded_at = when
                await session.commit()

    async def mark_question_reminded(self, question_id: int, when: datetime) -> None:
        async with self.sessions() as session:
            question = await session.get(Question, question_id)
            if question:
                question.last_reminded_at = when
                await session.commit()

    async def counts(self, chat_id: int, since: datetime) -> dict[str, int]:
        async with self.sessions() as session:
            messages = await session.scalar(select(func.count()).select_from(MessageRecord).where(MessageRecord.chat_id == chat_id, MessageRecord.sent_at >= since))
            tasks = await session.scalar(select(func.count()).select_from(Task).where(Task.chat_id == chat_id, Task.status.in_(["candidate", "open", "in_progress", "waiting"])))
            questions = await session.scalar(select(func.count()).select_from(Question).where(Question.chat_id == chat_id, Question.status == "open"))
            return {"messages": int(messages or 0), "tasks": int(tasks or 0), "questions": int(questions or 0)}

    async def cleanup_old_messages(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=self.settings.message_retention_days)
        async with self.sessions() as session:
            result = await session.execute(delete(MessageRecord).where(MessageRecord.sent_at < cutoff))
            await session.commit()
            return int(result.rowcount or 0)
