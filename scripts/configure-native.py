"""Local setup: secret input, migration, real API checks."""
import asyncio
import getpass
import os
from pathlib import Path

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)


async def check():
    from aiogram import Bot
    from openai import AsyncOpenAI
    from app.config import Settings
    from app.db.base import Base, make_engine

    settings = Settings()
    engine = make_engine(settings)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()
    bot = Bot(token=settings.telegram_bot_token.get_secret_value())
    try:
        me = await bot.get_me()
        print(f"Telegram OK: @{me.username}")
        if not me.can_read_all_group_messages:
            print("BotFather: /setprivacy -> select this bot -> Disable.")
    finally:
        await bot.session.close()
    async with AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value(),
                           timeout=30, max_retries=0) as client:
        await client.responses.create(model=settings.openai_model,
                                      input="Reply with OK.", max_output_tokens=16,
                                      store=False)
    print("OpenAI generation and database OK.")


def main():
    envfile = ROOT / ".env"
    envfile.touch(exist_ok=True)
    values = dotenv_values(envfile)
    for key in ("TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY"):
        if not values.get(key):
            value = getpass.getpass(f"Paste {key} (hidden): ").strip()
            if not value or any(c.isspace() for c in value):
                raise ValueError(f"{key} must be nonempty and contain no whitespace")
            set_key(str(envfile), key, value)
    if values.get("DATABASE_URL", "").startswith("sqlite+aiosqlite:////app/") or not values.get("DATABASE_URL"):
        set_key(str(envfile), "DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db")
    if not values.get("OPENAI_MODEL") or values.get("OPENAI_MODEL") == "gpt-5.6-luna":
        set_key(str(envfile), "OPENAI_MODEL", "gpt-4.1-mini")
    for key, value in {"DEFAULT_TIMEZONE": "Europe/Moscow",
                       "DEFAULT_DIGEST_TIME": "18:00"}.items():
        if not values.get(key):
            set_key(str(envfile), key, value)
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "logs").mkdir(exist_ok=True)
    asyncio.run(check())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never print exception URLs/headers: these may contain credentials.
        print(f"Setup check failed: {type(exc).__name__}.")
        print("Check internet, API keys and OpenAI API credit.")
        print("To replace a saved key, edit .env locally, then run START_HERE.cmd.")
        raise SystemExit(1) from None
