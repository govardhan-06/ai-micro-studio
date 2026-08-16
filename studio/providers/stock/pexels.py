from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from studio.providers.media import (
    DownloadedStockMedia,
    MediaAuthenticationError,
    MediaInvalidRequestError,
    MediaProviderError,
    MediaRateLimitError,
    MediaTransientError,
    StockMediaCandidate,
    StockMediaProvider,
)


RequestFn = Callable[[Request, float], tuple[int, Mapping[str, str], bytes]]


def _request(request: Request, timeout: float) -> tuple[int, Mapping[str, str], bytes]:
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()
    except (TimeoutError, URLError) as exc:
        raise MediaTransientError(
            f"Pexels request failed: {exc}",
            code="media_transient",
            provider="pexels",
            retryable=True,
        ) from exc


class PexelsProvider(StockMediaProvider):
    name = "pexels"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.pexels.com/v1",
        timeout: float = 30,
        request_fn: RequestFn = _request,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.request_fn = request_fn

    def search(
        self,
        query: str,
        *,
        media_type: str,
        orientation: str,
        per_page: int,
    ) -> list[StockMediaCandidate]:
        if not self.api_key:
            raise MediaAuthenticationError(
                "Pexels API key is required",
                code="media_authentication",
                provider=self.name,
            )
        if not query.strip() or media_type not in {"photo", "video"}:
            raise MediaInvalidRequestError(
                "stock query and media type are required",
                code="media_invalid_request",
                provider=self.name,
            )
        if orientation not in {"portrait", "landscape", "square"} or not 1 <= per_page <= 80:
            raise MediaInvalidRequestError(
                "stock orientation or page size is invalid",
                code="media_invalid_request",
                provider=self.name,
            )
        endpoint = "/videos/search" if media_type == "video" else "/search"
        query_string = urlencode({"query": query.strip(), "orientation": orientation, "per_page": per_page})
        request = Request(
            f"{self.base_url}{endpoint}?{query_string}",
            headers={"Authorization": self.api_key, "Accept": "application/json"},
        )
        status, headers, raw = self.request_fn(request, self.timeout)
        payload = self._payload_or_error(status, headers, raw)
        records = payload.get("videos" if media_type == "video" else "photos", [])
        return [self._candidate(record, media_type, orientation) for record in records]

    def download(self, candidate: StockMediaCandidate) -> DownloadedStockMedia:
        request = Request(candidate.download_url, headers={"Accept": "*/*"})
        status, headers, raw = self.request_fn(request, self.timeout)
        if status >= 400:
            raise _pexels_error(status, "Pexels media download failed", download=True)
        content_type = headers.get("content-type", "video/mp4" if candidate.media_type == "video" else "image/jpeg")
        return DownloadedStockMedia(candidate=candidate, content=raw, content_type=content_type.split(";", 1)[0])

    def _payload_or_error(self, status: int, headers: Mapping[str, str], raw: bytes) -> dict:
        if status >= 400:
            raise _pexels_error(status, "Pexels search failed")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MediaTransientError(
                "Pexels returned a non-JSON response",
                code="media_invalid_response",
                provider=self.name,
                retryable=True,
                status_code=status,
            ) from exc
        return payload

    def _candidate(self, record: dict, media_type: str, orientation: str) -> StockMediaCandidate:
        if media_type == "photo":
            src = record.get("src") or {}
            download_url = src.get(orientation) or src.get("original")
            if not download_url:
                raise MediaProviderError(
                    "Pexels photo has no downloadable source",
                    code="media_invalid_response",
                    provider=self.name,
                )
            metadata = {
                "source_url": record.get("url"),
                "photographer": record.get("photographer"),
                "photographer_url": record.get("photographer_url"),
                "alt": record.get("alt"),
                "license": "Pexels content license",
            }
            return StockMediaCandidate(
                provider=self.name,
                external_id=str(record["id"]),
                media_type=media_type,
                source_url=record.get("url", ""),
                download_url=download_url,
                width=int(record.get("width", 0)),
                height=int(record.get("height", 0)),
                duration_sec=None,
                metadata=metadata,
            )
        files = [file for file in record.get("video_files", []) if file.get("link")]
        if not files:
            raise MediaProviderError(
                "Pexels video has no downloadable source",
                code="media_invalid_response",
                provider=self.name,
            )
        def matches_orientation(file: dict) -> bool:
            width = file.get("width", 0)
            height = file.get("height", 0)
            if orientation == "portrait":
                return height >= width
            if orientation == "square":
                return height == width
            return width >= height

        selected = next((file for file in files if matches_orientation(file)), files[0])
        metadata = {
            "source_url": record.get("url"),
            "photographer": (record.get("user") or {}).get("name"),
            "photographer_url": (record.get("user") or {}).get("url"),
            "image_preview_url": record.get("image"),
            "license": "Pexels content license",
        }
        return StockMediaCandidate(
            provider=self.name,
            external_id=str(record["id"]),
            media_type=media_type,
            source_url=record.get("url", ""),
            download_url=selected["link"],
            width=int(selected.get("width", record.get("width", 0))),
            height=int(selected.get("height", record.get("height", 0))),
            duration_sec=float(record["duration"]) if record.get("duration") is not None else None,
            metadata=metadata,
        )


def _pexels_error(status: int, message: str, *, download: bool = False) -> MediaProviderError:
    code_prefix = "media_download" if download else "media"
    if status in {401, 403}:
        return MediaAuthenticationError(message, code=f"{code_prefix}_authentication", provider="pexels", status_code=status)
    if status == 429:
        return MediaRateLimitError(message, code=f"{code_prefix}_rate_limited", provider="pexels", retryable=True, status_code=status)
    if 400 <= status < 500:
        return MediaInvalidRequestError(message, code=f"{code_prefix}_invalid_request", provider="pexels", status_code=status)
    return MediaTransientError(message, code=f"{code_prefix}_transient", provider="pexels", retryable=True, status_code=status)
