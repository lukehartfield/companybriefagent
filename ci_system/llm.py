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
        self.api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.model = model or os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
        if self.api_key and OpenAI is not None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
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
