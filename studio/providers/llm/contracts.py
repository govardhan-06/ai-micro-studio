from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Mapping, Protocol, TypeVar

from pydantic import BaseModel


StructuredT = TypeVar("StructuredT", bound=BaseModel)


class LLMProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        provider: str,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.retryable = retryable
        self.status_code = status_code


class LLMAuthenticationError(LLMProviderError):
    pass


class LLMInvalidRequestError(LLMProviderError):
    pass


class LLMModerationError(LLMProviderError):
    pass


class LLMRateLimitError(LLMProviderError):
    pass


class LLMTransientError(LLMProviderError):
    pass


class LLMStructuredOutputError(LLMProviderError):
    pass


@dataclass(frozen=True)
class LLMResult(Generic[StructuredT]):
    provider: str
    model: str
    text: str
    structured: StructuredT | None = None
    usage: Mapping[str, Any] | None = None


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, prompt: str, *, system_prompt: str | None = None) -> LLMResult[BaseModel]: ...

    def generate_structured(
        self,
        prompt: str,
        schema: type[StructuredT],
        *,
        system_prompt: str | None = None,
    ) -> LLMResult[StructuredT]: ...
