from __future__ import annotations

from studio.providers.llm.openai_compatible import OpenAICompatibleLLMProvider


class NvidiaNIMProvider(OpenAICompatibleLLMProvider):
    def __init__(self, *, model: str, api_key: str, base_url: str = "https://integrate.api.nvidia.com/v1", **kwargs: object) -> None:
        super().__init__(name="nvidia_nim", model=model, api_key=api_key, base_url=base_url, **kwargs)
