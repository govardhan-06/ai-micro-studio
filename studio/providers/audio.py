from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class AudioProviderError(RuntimeError):
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


class AudioAuthenticationError(AudioProviderError):
    pass


class AudioInvalidRequestError(AudioProviderError):
    pass


class AudioProviderResponseError(AudioProviderError):
    pass


class AudioRateLimitError(AudioProviderError):
    pass


class AudioTransientError(AudioProviderError):
    pass


@dataclass(frozen=True)
class AudioArtifact:
    provider: str
    model: str
    content: bytes
    content_type: str
    duration_sec: float
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class WordTiming:
    word: str
    start_sec: float
    end_sec: float

    def as_dict(self) -> dict[str, object]:
        return {"word": self.word, "start_sec": self.start_sec, "end_sec": self.end_sec}


class TTSProvider(Protocol):
    name: str
    model: str

    def synthesize(self, text: str, *, voice: str | None = None, direction: str | None = None) -> AudioArtifact:
        ...


class TranscriptionProvider(Protocol):
    name: str
    model: str

    def align(
        self,
        audio: bytes,
        *,
        content_type: str = "audio/wav",
        language: str | None = "en",
    ) -> list[WordTiming]:
        ...
