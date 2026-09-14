from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
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
    digest_thread_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_digest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
