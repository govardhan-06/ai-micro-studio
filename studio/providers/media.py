from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


class MediaProviderError(RuntimeError):
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


class MediaAuthenticationError(MediaProviderError):
    pass


class MediaInvalidRequestError(MediaProviderError):
    pass


class MediaModerationError(MediaProviderError):
    pass


class MediaRateLimitError(MediaProviderError):
    pass


class MediaTransientError(MediaProviderError):
    pass


@dataclass(frozen=True)
class ImageProviderCapabilities:
    supports_reference_images: bool
    max_reference_images: int
    supports_image_editing: bool


@dataclass(frozen=True)
class GeneratedImage:
    provider: str
    model: str
    content: bytes
    content_type: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class StockMediaCandidate:
    provider: str
    external_id: str
    media_type: str
    source_url: str
    download_url: str
    width: int
    height: int
    duration_sec: float | None
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class DownloadedStockMedia:
    candidate: StockMediaCandidate
    content: bytes
    content_type: str


class ImageProvider(Protocol):
    name: str
    model: str
    capabilities: ImageProviderCapabilities

    def generate(
        self,
        prompt: str,
        *,
        references: Sequence[str] | None = None,
        aspect_ratio: str | None = None,
        seed: int | None = None,
    ) -> GeneratedImage:
        ...


class StockMediaProvider(Protocol):
    name: str

    def search(
        self,
        query: str,
        *,
        media_type: str,
        orientation: str,
        per_page: int,
    ) -> list[StockMediaCandidate]:
        ...

    def download(self, candidate: StockMediaCandidate) -> DownloadedStockMedia:
        ...
