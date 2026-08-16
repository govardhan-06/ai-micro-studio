from __future__ import annotations

from studio.providers.llm.openai_compatible import OpenAICompatibleLLMProvider


class GroqProvider(OpenAICompatibleLLMProvider):
    def __init__(self, *, model: str = "openai/gpt-oss-120b", api_key: str, base_url: str = "https://api.groq.com/openai/v1", **kwargs: object) -> None:
        super().__init__(name="groq", model=model, api_key=api_key, base_url=base_url, strict_structured_output=True, **kwargs)
