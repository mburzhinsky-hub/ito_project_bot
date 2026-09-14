from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ExtractedTask(BaseModel):
    operation: Literal["create", "update", "complete", "cancel"]
    target_task_id: int | None = None
    source_message_id: int
    title: str
    description: str | None = None
    creator_id: int | None = None
    assignee_id: int | None = None
    assignee_display_name: str | None = None
    deadline: datetime | None = None
    status: Literal["candidate", "open", "in_progress", "waiting", "done", "cancelled"] = "open"
    confidence: float = Field(ge=0, le=1)
    extraction_reason: str


class ExtractedQuestion(BaseModel):
    operation: Literal["create", "answer", "cancel"]
    target_question_id: int | None = None
    source_message_id: int
    author_id: int | None = None
    addressee_id: int | None = None
    text: str
    confidence: float = Field(ge=0, le=1)


class ExtractedDecision(BaseModel):
    source_message_id: int
    text: str
    confidence: float = Field(ge=0, le=1)


class ExtractionResult(BaseModel):
    tasks: list[ExtractedTask] = Field(default_factory=list)
    questions: list[ExtractedQuestion] = Field(default_factory=list)
    decisions: list[ExtractedDecision] = Field(default_factory=list)


class MessageForAnalysis(BaseModel):
    message_id: int
    thread_id: int | None = None
    sender_id: int | None = None
    sender_username: str | None = None
    sender_name: str
    sent_at: datetime
    text: str
    reply_to_message_id: int | None = None
    mentions: list[str] = Field(default_factory=list)
    entities: list[dict] = Field(default_factory=list)
