from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class ProjectChat(Base):
    __tablename__ = "project_chats"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="Project")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    chat_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    digest_time: Mapped[str] = mapped_column(String(5), default="18:00")
    unanswered_after_hours: Mapped[int] = mapped_column(Integer, default=12)
    deadline_reminder_hours: Mapped[int] = mapped_column(Integer, default=24)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    private_reminders: Mapped[bool] = mapped_column(Boolean, default=True)
    digest_thread_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_digest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TelegramUser(Base):
    __tablename__ = "telegram_users"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), default="Unknown")
    dm_started: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MessageRecord(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("chat_id", "message_id", name="uq_message_chat_message"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project_chats.chat_id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int] = mapped_column(BigInteger)
    thread_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sender_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    sender_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_display_name: Mapped[str] = mapped_column(String(255), default="Unknown")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    text: Mapped[str] = mapped_column(Text)
    reply_to_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mentions_json: Mapped[str] = mapped_column(Text, default="[]")
    entities_json: Mapped[str] = mapped_column(Text, default="[]")
    analysis_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    analysis_attempts: Mapped[int] = mapped_column(Integer, default=0)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project_chats.chat_id", ondelete="CASCADE"), index=True)
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    source_thread_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    assignee_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    assignee_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    extraction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project_chats.chat_id", ondelete="CASCADE"), index=True)
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    source_thread_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    author_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    addressee_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    text: Mapped[str] = mapped_column(Text)
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answer_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (UniqueConstraint("chat_id", "source_message_id", "text", name="uq_decision_source_text"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project_chats.chat_id", ondelete="CASCADE"), index=True)
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
