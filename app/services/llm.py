from __future__ import annotations

import json
import logging
from pathlib import Path

from openai import AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.config import Settings
from app.schemas import ExtractionResult

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    pass


class OpenAIExtractorClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value()) if settings.openai_api_key else None
        self.instructions = Path(__file__).resolve().parents[1].joinpath("prompts", "extraction.txt").read_text(encoding="utf-8")

    @property
    def configured(self) -> bool:
        return self.client is not None

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=8),
        reraise=True,
    )
    async def extract(self, payload: dict) -> ExtractionResult:
        if self.client is None:
            raise LLMUnavailable("OPENAI_API_KEY is not configured")
        response = await self.client.responses.parse(
            model=self.settings.openai_model,
            instructions=self.instructions,
            input=json.dumps(payload, ensure_ascii=False, default=str),
            text_format=ExtractionResult,
            store=False,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            logger.info(
                "OpenAI extraction usage",
                extra={
                    "model": self.settings.openai_model,
                    "input_tokens": getattr(usage, "input_tokens", None),
                    "output_tokens": getattr(usage, "output_tokens", None),
                },
            )
        parsed = getattr(response, "output_parsed", None)
        if parsed is not None:
            return parsed
        for output in getattr(response, "output", []):
            if getattr(output, "type", None) != "message":
                continue
            for content in getattr(output, "content", []):
                candidate = getattr(content, "parsed", None)
                if candidate is not None:
                    return candidate
        raise LLMUnavailable("OpenAI returned no parsed structured output")
