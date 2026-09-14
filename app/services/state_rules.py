from __future__ import annotations

from datetime import UTC, datetime

ALLOWED_TASK_TRANSITIONS: dict[str, set[str]] = {
    "candidate": {"open", "cancelled"},
    "open": {"in_progress", "waiting", "done", "cancelled"},
    "in_progress": {"waiting", "open", "done", "cancelled"},
    "waiting": {"open", "in_progress", "done", "cancelled"},
    "done": {"open"},
    "cancelled": {"open"},
}


def can_transition_task(current: str, target: str) -> bool:
    return target == current or target in ALLOWED_TASK_TRANSITIONS.get(current, set())


def apply_task_status(task, target: str, at: datetime | None = None) -> bool:
    if not can_transition_task(task.status, target):
        return False
    task.status = target
    when = at or datetime.now(UTC)
    if target == "done":
        task.completed_at = when
    elif target not in {"done", "cancelled"}:
        task.completed_at = None
    return True


def reply_answers_question(question, sender_id: int | None, reply_to_message_id: int | None) -> bool:
    if question.status != "open" or reply_to_message_id != question.source_message_id:
        return False
    return question.addressee_id is None or question.addressee_id == sender_id
