import logging
from typing import Any

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger(__name__)


class VLLMClient:
    """Thin async wrapper around the OpenAI-compatible vLLM API."""

    def __init__(self):
        self._client = AsyncOpenAI(
            base_url=settings.vllm_base_url,
            api_key="not-needed",  # vLLM doesn't require a real key
        )
        self.model = settings.vllm_model

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat completion request to vLLM and return the text response."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        try:
            completion = await self._client.chat.completions.create(**kwargs)
            return completion.choices[0].message.content or ""
        except Exception as e:
            logger.error("vLLM request failed: %s", e)
            raise

    async def is_available(self) -> bool:
        """Check if the vLLM server is reachable."""
        try:
            models = await self._client.models.list()
            return len(models.data) > 0
        except Exception:
            return False


# Module-level singleton
llm_client = VLLMClient()
