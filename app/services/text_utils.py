from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, time, timedelta
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

RUS_WEEKDAYS = {
    "понедельник": 0, "понедельника": 0, "понедельнику": 0,
    "вторник": 1, "вторника": 1, "вторнику": 1,
    "среда": 2, "среду": 2, "среды": 2, "среде": 2,
    "четверг": 3, "четверга": 3, "четвергу": 3,
    "пятница": 4, "пятницу": 4, "пятницы": 4, "пятнице": 4,
    "суббота": 5, "субботу": 5, "субботы": 5, "субботе": 5,
    "воскресенье": 6, "воскресенья": 6, "воскресенью": 6,
}

ACTION_HINTS = re.compile(
    r"(?iu)\b(сделай|сделать|подготовь|подготовить|скинь|пришли|отправь|проверь|проверить|"
    r"нужно|надо|можешь|давай|жду|сделаю|скину|пришлю|отправлю|проверю|напомни|"
    r"готово|сделал|сделала|отправил|отправила|закрыто|пофиксил|пофиксила)\b|\?"
)


def normalize_text(text: str) -> str:
    text = text.casefold().replace("ё", "е")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\w\s@-]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def similar(a: str, b: str, threshold: float = 0.84) -> bool:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio() >= threshold


def should_analyze_message(text: str) -> bool:
    return bool(text and len(text.strip()) >= 2 and ACTION_HINTS.search(text))


def _end_of_local_day(local_date, tz: ZoneInfo) -> datetime:
    return datetime.combine(local_date, time(23, 59, 59), tzinfo=tz).astimezone(UTC)


def parse_deadline(text: str, now: datetime, timezone: str) -> datetime | None:
    tz = ZoneInfo(timezone)
    local_now = now.astimezone(tz)
    value = normalize_text(text)
    if "послезавтра" in value:
        return _end_of_local_day(local_now.date() + timedelta(days=2), tz)
    if "завтра" in value:
        return _end_of_local_day(local_now.date() + timedelta(days=1), tz)
    if "сегодня" in value:
        return _end_of_local_day(local_now.date(), tz)
    iso_match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", value)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        try:
            return _end_of_local_day(datetime(year, month, day).date(), tz)
        except ValueError:
            return None
    dot_match = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](20\d{2}))?\b", value)
    if dot_match:
        day, month, year = dot_match.groups()
        year_i = int(year) if year else local_now.year
        try:
            candidate = datetime(year_i, int(month), int(day)).date()
        except ValueError:
            return None
        if year is None and candidate < local_now.date():
            candidate = candidate.replace(year=year_i + 1)
        return _end_of_local_day(candidate, tz)
    for word, weekday in RUS_WEEKDAYS.items():
        if re.search(rf"\b(?:до|к|на)\s+{re.escape(word)}\b", value):
            delta = (weekday - local_now.weekday()) % 7
            if delta == 0:
                delta = 7
            return _end_of_local_day(local_now.date() + timedelta(days=delta), tz)
    return None


def message_link(chat_id: int, message_id: int, chat_username: str | None = None) -> str | None:
    if chat_username:
        return f"https://t.me/{chat_username.lstrip('@')}/{message_id}"
    raw = str(chat_id)
    if raw.startswith("-100"):
        return f"https://t.me/c/{raw[4:]}/{message_id}"
    return None


def build_identity_directory(records) -> list[dict]:
    by_id: dict[int, dict] = {}
    for record in records:
        user_id = getattr(record, "sender_id", None)
        if user_id is not None:
            by_id[user_id] = {
                "telegram_user_id": user_id,
                "username": getattr(record, "sender_username", None),
                "display_name": getattr(record, "sender_display_name", "Unknown"),
            }
    return list(by_id.values())
