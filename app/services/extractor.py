from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from app.db.models import MessageRecord
from app.schemas import MessageForAnalysis
from app.services.llm import OpenAIExtractorClient
from app.services.store import Store
from app.services.text_utils import parse_deadline

logger = logging.getLogger(__name__)


class ExtractionService:
    def __init__(self, store: Store, llm: OpenAIExtractorClient) -> None:
        self.store = store
        self.llm = llm

    async def process_record(self, record: MessageRecord) -> bool:
        project = await self.store.get_project(record.chat_id)
        if project is None:
            await self.store.mark_message_analysis(record.id, "failed")
            return False

        await self.store.resolve_direct_reply(
            chat_id=record.chat_id,
            sender_id=record.sender_id,
            reply_to_message_id=record.reply_to_message_id,
            answer_message_id=record.message_id,
            answered_at=record.sent_at,
        )
        if not self.llm.configured:
            await self.store.mark_message_analysis(record.id, "failed")
            return False

        messages = await self.store.recent_messages(record.chat_id, record.message_id, limit=20)
        tasks = await self.store.open_tasks(record.chat_id)
        questions = await self.store.open_questions(record.chat_id)
        payload = {
            "timezone": project.timezone,
            "current_message_id": record.message_id,
            "messages": [
                MessageForAnalysis(
                    message_id=m.message_id,
                    thread_id=m.thread_id,
                    sender_id=m.sender_id,
                    sender_username=m.sender_username,
                    sender_name=m.sender_display_name,
                    sent_at=m.sent_at,
                    text=m.text,
                    reply_to_message_id=m.reply_to_message_id,
                    mentions=json.loads(m.mentions_json or "[]"),
                    entities=json.loads(m.entities_json or "[]"),
                ).model_dump(mode="json")
                for m in messages
            ],
            "known_users": await self.store.known_users_for_chat(record.chat_id),
            "open_tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "assignee_id": t.assignee_id,
                    "creator_id": t.creator_id,
                    "deadline": t.deadline.isoformat() if t.deadline else None,
                    "status": t.status,
                    "source_message_id": t.source_message_id,
                }
                for t in tasks
            ],
            "open_questions": [
                {
                    "id": q.id,
                    "text": q.text,
                    "author_id": q.author_id,
                    "addressee_id": q.addressee_id,
                    "asked_at": q.asked_at.isoformat(),
                    "source_message_id": q.source_message_id,
                }
                for q in questions
            ],
        }
        try:
            result = await self.llm.extract(payload)
            fallback_deadline = parse_deadline(record.text, record.sent_at, project.timezone)
            for item in result.tasks:
                enriched = SimpleNamespace(**item.model_dump(), chat_id=record.chat_id)
                if item.operation in {"complete", "cancel"} and item.target_task_id:
                    await self.store.complete_or_cancel_task(
                        record.chat_id,
                        item.target_task_id,
                        "done" if item.operation == "complete" else "cancelled",
                        record.sent_at,
                    )
                else:
                    await self.store.create_or_merge_task(
                        enriched,
                        source_thread_id=record.thread_id,
                        fallback_deadline=fallback_deadline,
                    )
            for item in result.questions:
                enriched = SimpleNamespace(**item.model_dump(), chat_id=record.chat_id)
                await self.store.create_or_resolve_question(enriched, source_thread_id=record.thread_id)
            for decision in result.decisions:
                await self.store.add_decision(record.chat_id, decision.source_message_id, decision.text, decision.confidence)
            await self.store.mark_message_analysis(record.id, "done")
            return True
        except Exception:
            logger.exception("Message analysis failed", extra={"chat_id": record.chat_id, "message_id": record.message_id})
            await self.store.mark_message_analysis(record.id, "failed")
            return False

    async def retry_pending(self, limit: int = 20) -> int:
        processed = 0
        for record in await self.store.get_pending_messages(limit=limit):
            if record.analysis_attempts >= 5:
                continue
            if await self.process_record(record):
                processed += 1
        return processed
