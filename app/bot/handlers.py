from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import Settings
from app.services.digest import DigestService
from app.services.extractor import ExtractionService
from app.services.store import Store
from app.services.text_utils import message_link, should_analyze_message


def _args(text: str | None) -> list[str]:
    return (text or "").split()[1:]


async def _is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
    except Exception:
        return False


def _task_keyboard(chat_id: int, task_id: int, source_url: str | None) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(text="✅ Готово", callback_data=f"td:{chat_id}:{task_id}"),
        InlineKeyboardButton(text="⏰ +4ч", callback_data=f"ts:{chat_id}:{task_id}"),
    ]
    if source_url:
        row.append(InlineKeyboardButton(text="💬 Исходник", url=source_url))
    return InlineKeyboardMarkup(inline_keyboard=[row])


async def _can_modify_task(bot: Bot, store: Store, chat_id: int, task_id: int, user_id: int) -> bool:
    task = await store.get_task(task_id)
    if not task or task.chat_id != chat_id:
        return False
    if user_id in {task.assignee_id, task.creator_id}:
        return True
    return await _is_admin(bot, chat_id, user_id)


def build_router(store: Store, extractor: ExtractionService, digest: DigestService, settings: Settings) -> Router:
    router = Router(name="project_assistant")

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        if message.from_user:
            await store.upsert_user(
                message.from_user.id,
                message.from_user.username,
                message.from_user.full_name,
                dm_started=True if message.chat.type == ChatType.PRIVATE else None,
            )
        if message.chat.type == ChatType.PRIVATE:
            await message.answer("Готово. Теперь бот может присылать тебе личные напоминания. В проектной группе выполни /setup.")
        else:
            await message.answer("Для подключения этого проектного чата используй /setup.")

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(
            "<b>Команды</b>\n"
            "/setup — подключить чат\n/status — состояние\n/digest — отчёт сейчас\n"
            "/tasks — открытые задачи\n/questions — вопросы без ответа\n/mine — мои задачи\n"
            "/done ID — закрыть задачу\n/snooze ID [часы] — отложить напоминание\n"
            "/settings — настройки\n/settings digest=18:00 timezone=Europe/Moscow unanswered=12 deadline=24 reminders=on private=on"
        )

    @router.message(Command("setup"))
    async def setup(message: Message, bot: Bot) -> None:
        if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            await message.answer("/setup нужно запускать внутри проектной группы.")
            return
        if not message.from_user or not await _is_admin(bot, message.chat.id, message.from_user.id):
            await message.answer("Настраивать проект может администратор группы.")
            return
        project = await store.ensure_project(
            message.chat.id,
            message.chat.title or "Project",
            message.chat.username,
            message.message_thread_id,
            activate=True,
        )
        await message.answer(
            "✅ <b>Project Assistant подключён</b>\n"
            f"Ежедневный отчёт: {escape(project.digest_time)}\n"
            f"Часовой пояс: {escape(project.timezone)}\n"
            f"Вопрос без ответа: {project.unanswered_after_hours} ч."
        )

    @router.message(Command("status"))
    async def status(message: Message) -> None:
        project = await store.get_project(message.chat.id)
        if not project:
            await message.answer("Проект не подключён. Выполни /setup.")
            return
        counts = await store.counts(project.chat_id, datetime.now(UTC) - timedelta(hours=24))
        db_ok = await store.healthcheck()
        await message.answer(
            "<b>Status</b>\n"
            f"Bot: 🟢 running\nDatabase: {'🟢 connected' if db_ok else '🔴 error'}\n"
            f"OpenAI: {'🟢 configured' if settings.openai_api_key else '🔴 not configured'}\n"
            f"Messages 24h: {counts['messages']}\nOpen tasks: {counts['tasks']}\nOpen questions: {counts['questions']}\n"
            f"Digest: {escape(project.digest_time)} ({escape(project.timezone)})"
        )

    @router.message(Command("digest"))
    async def digest_now(message: Message) -> None:
        project = await store.get_project(message.chat.id)
        if not project:
            await message.answer("Проект не подключён. Выполни /setup.")
            return
        await message.answer(await digest.build(project), disable_web_page_preview=True)

    async def send_tasks(message: Message, mine: bool) -> None:
        project = await store.get_project(message.chat.id)
        if not project:
            await message.answer("Проект не подключён. Выполни /setup.")
            return
        assignee = message.from_user.id if mine and message.from_user else None
        tasks = await store.open_tasks(project.chat_id, assignee_id=assignee)
        if not tasks:
            await message.answer("Открытых задач нет.")
            return
        for task in tasks[:25]:
            link = message_link(project.chat_id, task.source_message_id, project.chat_username)
            deadline = "не указан"
            if task.deadline:
                value = task.deadline.replace(tzinfo=UTC) if task.deadline.tzinfo is None else task.deadline
                deadline = value.astimezone(ZoneInfo(project.timezone)).strftime("%d.%m %H:%M")
            who = task.assignee_display_name or (str(task.assignee_id) if task.assignee_id else "не назначен")
            await message.answer(
                f"<b>#{task.id} {escape(task.title)}</b>\nИсполнитель: {escape(who)}\nДедлайн: {deadline}\nСтатус: {escape(task.status)}",
                reply_markup=_task_keyboard(project.chat_id, task.id, link),
                disable_web_page_preview=True,
            )

    @router.message(Command("tasks"))
    async def tasks_command(message: Message) -> None:
        await send_tasks(message, mine=False)

    @router.message(Command("mine"))
    async def mine_command(message: Message) -> None:
        await send_tasks(message, mine=True)

    @router.message(Command("questions"))
    async def questions_command(message: Message) -> None:
        project = await store.get_project(message.chat.id)
        if not project:
            await message.answer("Проект не подключён. Выполни /setup.")
            return
        questions = await store.open_questions(project.chat_id)
        if not questions:
            await message.answer("Вопросов без ответа нет.")
            return
        lines = ["❓ <b>Вопросы без ответа</b>"]
        for q in questions[:25]:
            link = message_link(project.chat_id, q.source_message_id, project.chat_username)
            suffix = f' · <a href="{escape(link)}">сообщение</a>' if link else f" · msg #{q.source_message_id}"
            lines.append(f"\n#{q.id} {escape(q.text[:400])}{suffix}")
        await message.answer("\n".join(lines), disable_web_page_preview=True)

    @router.message(Command("done"))
    async def done_command(message: Message, bot: Bot) -> None:
        args = _args(message.text)
        if not args or not args[0].isdigit():
            await message.answer("Использование: /done ID")
            return
        task_id = int(args[0])
        if not message.from_user or not await _can_modify_task(bot, store, message.chat.id, task_id, message.from_user.id):
            await message.answer("Нет прав на изменение этой задачи.")
            return
        task = await store.complete_or_cancel_task(message.chat.id, task_id, "done")
        await message.answer(f"✅ #{task_id} закрыта." if task else "Не удалось закрыть задачу.")

    @router.message(Command("snooze"))
    async def snooze_command(message: Message, bot: Bot) -> None:
        args = _args(message.text)
        if not args or not args[0].isdigit():
            await message.answer("Использование: /snooze ID [часы]")
            return
        task_id = int(args[0])
        hours = int(args[1]) if len(args) > 1 and args[1].isdigit() else 4
        hours = max(1, min(hours, 168))
        if not message.from_user or not await _can_modify_task(bot, store, message.chat.id, task_id, message.from_user.id):
            await message.answer("Нет прав на изменение этой задачи.")
            return
        task = await store.snooze_task(message.chat.id, task_id, datetime.now(UTC) + timedelta(hours=hours))
        await message.answer(f"⏰ #{task_id}: напоминание отложено на {hours} ч." if task else "Задача не найдена.")

    @router.message(Command("settings"))
    async def settings_command(message: Message, bot: Bot) -> None:
        project = await store.get_project(message.chat.id)
        if not project:
            await message.answer("Сначала выполни /setup.")
            return
        args = _args(message.text)
        if not args:
            await message.answer(
                f"<b>Настройки</b>\nTimezone: {escape(project.timezone)}\nDigest: {escape(project.digest_time)}\n"
                f"Unanswered: {project.unanswered_after_hours} ч\nDeadline reminder: {project.deadline_reminder_hours} ч\n"
                f"Reminders: {'on' if project.reminders_enabled else 'off'}\nPrivate: {'on' if project.private_reminders else 'off'}"
            )
            return
        if not message.from_user or not await _is_admin(bot, message.chat.id, message.from_user.id):
            await message.answer("Менять настройки может администратор группы.")
            return
        updates: dict = {}
        bad: list[str] = []
        for token in args:
            if "=" not in token:
                bad.append(token)
                continue
            key, value = token.split("=", 1)
            try:
                if key == "digest" and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                    updates["digest_time"] = value
                elif key == "timezone":
                    ZoneInfo(value)
                    updates["timezone"] = value
                elif key == "unanswered":
                    updates["unanswered_after_hours"] = max(1, int(value))
                elif key == "deadline":
                    updates["deadline_reminder_hours"] = max(1, int(value))
                elif key == "reminders" and value in {"on", "off"}:
                    updates["reminders_enabled"] = value == "on"
                elif key == "private" and value in {"on", "off"}:
                    updates["private_reminders"] = value == "on"
                elif key == "thread" and value == "current":
                    updates["digest_thread_id"] = message.message_thread_id
                elif key == "thread" and value == "main":
                    updates["digest_thread_id"] = None
                else:
                    bad.append(token)
            except (ValueError, ZoneInfoNotFoundError):
                bad.append(token)
        if updates:
            await store.update_project_settings(project.chat_id, **updates)
        await message.answer("✅ Настройки обновлены." + (f" Не распознано: {', '.join(map(escape, bad))}" if bad else ""))

    @router.callback_query(F.data.startswith("td:"))
    async def callback_done(callback: CallbackQuery, bot: Bot) -> None:
        if not callback.data or not callback.from_user:
            return
        _, chat_s, task_s = callback.data.split(":", 2)
        chat_id, task_id = int(chat_s), int(task_s)
        if not await _can_modify_task(bot, store, chat_id, task_id, callback.from_user.id):
            await callback.answer("Нет прав на изменение задачи", show_alert=True)
            return
        task = await store.complete_or_cancel_task(chat_id, task_id, "done")
        await callback.answer("Задача закрыта" if task else "Не удалось закрыть", show_alert=not bool(task))
        if task and callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

    @router.callback_query(F.data.startswith("ts:"))
    async def callback_snooze(callback: CallbackQuery, bot: Bot) -> None:
        if not callback.data or not callback.from_user:
            return
        _, chat_s, task_s = callback.data.split(":", 2)
        chat_id, task_id = int(chat_s), int(task_s)
        if not await _can_modify_task(bot, store, chat_id, task_id, callback.from_user.id):
            await callback.answer("Нет прав на изменение задачи", show_alert=True)
            return
        task = await store.snooze_task(chat_id, task_id, datetime.now(UTC) + timedelta(hours=4))
        await callback.answer("Напоминание отложено на 4 часа" if task else "Задача не найдена")

    @router.message()
    async def ingest(message: Message) -> None:
        if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            return
        text_value = message.text or message.caption or ""
        if not text_value or text_value.startswith("/"):
            return
        project = await store.ensure_project(message.chat.id, message.chat.title or "Project", message.chat.username)
        if message.from_user:
            await store.upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        mentions = re.findall(r"@[A-Za-z0-9_]{3,}", text_value)
        entities = []
        for entity in (message.entities or message.caption_entities or []):
            item = {"type": str(entity.type), "offset": entity.offset, "length": entity.length}
            mentioned_user = getattr(entity, "user", None)
            if mentioned_user is not None:
                item.update({"user_id": mentioned_user.id, "username": mentioned_user.username, "display_name": mentioned_user.full_name})
                await store.upsert_user(mentioned_user.id, mentioned_user.username, mentioned_user.full_name)
            entities.append(item)
        sent_at = message.date if message.date.tzinfo else message.date.replace(tzinfo=UTC)
        record = await store.save_message(
            chat_id=project.chat_id,
            message_id=message.message_id,
            thread_id=message.message_thread_id,
            sender_id=message.from_user.id if message.from_user else None,
            sender_username=message.from_user.username if message.from_user else None,
            sender_display_name=message.from_user.full_name if message.from_user else "Unknown",
            sent_at=sent_at,
            text_value=text_value,
            reply_to_message_id=message.reply_to_message.message_id if message.reply_to_message else None,
            mentions=mentions,
            entities=entities,
            should_analyze=project.is_active and should_analyze_message(text_value),
        )
        await store.resolve_direct_reply(
            project.chat_id,
            record.sender_id,
            record.reply_to_message_id,
            record.message_id,
            record.sent_at,
        )
        if record.analysis_status == "pending":
            await extractor.process_record(record)

    return router
