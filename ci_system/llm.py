from __future__ import annotations

import json
import os
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - depends on local environment
    OpenAI = None


class LLMClient:
    def __init__(self, model: str | None = None) -> None:
        provider = os.getenv("LLM_PROVIDER", "openrouter").strip().lower()
        if provider == "nvidia":
            self.api_key = os.getenv("NVIDIA_API_KEY")
            self.base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
            self.model = model or os.getenv("NVIDIA_MODEL", "minimaxai/minimax-m2.7")
        elif provider == "openai":
            self.api_key = os.getenv("OPENAI_API_KEY")
            self.base_url = os.getenv("OPENAI_BASE_URL")
            self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        else:
            self.api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
            self.base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
            self.model = model or os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")
        max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "0"))
        if self.api_key and OpenAI is not None:
            client_kwargs = {
                "api_key": self.api_key,
                "max_retries": max_retries,
            }
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            self._client = OpenAI(**client_kwargs)
        else:
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not self._client:
            raise RuntimeError("No supported LLM API key is set.")

        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content or "{}")

    def chat_text(self, system_prompt: str, user_prompt: str) -> str:
        if not self._client:
            raise RuntimeError("No supported LLM API key is set.")

        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return (response.choices[0].message.content or "").strip()
