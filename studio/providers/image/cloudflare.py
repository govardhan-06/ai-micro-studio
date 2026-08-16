from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from studio.providers.media import (
    GeneratedImage,
    ImageProvider,
    MediaAuthenticationError,
    MediaInvalidRequestError,
    MediaModerationError,
    MediaProviderError,
    MediaRateLimitError,
    MediaTransientError,
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
            f"Cloudflare request failed: {exc}",
            code="media_transient",
            provider="cloudflare",
            retryable=True,
        ) from exc


class CloudflareFluxProvider(ImageProvider):
    name = "cloudflare"
    model = "@cf/black-forest-labs/flux-1-schnell"

    def __init__(
        self,
        *,
        api_key: str | None,
        account_id: str | None,
        base_url: str = "https://api.cloudflare.com/client/v4",
        timeout: float = 30,
        request_fn: RequestFn = _request,
    ) -> None:
        self.api_key = api_key
        self.account_id = account_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.request_fn = request_fn

    def generate(
        self,
        prompt: str,
        *,
        references: Sequence[str] | None = None,
        aspect_ratio: str | None = None,
        seed: int | None = None,
    ) -> GeneratedImage:
        if not self.api_key or not self.account_id:
            raise MediaAuthenticationError(
                "Cloudflare API key and account ID are required",
                code="media_authentication",
                provider=self.name,
            )
        if not 1 <= len(prompt) <= 2048:
            raise MediaInvalidRequestError(
                "image prompt must contain between 1 and 2048 characters",
                code="media_invalid_request",
                provider=self.name,
            )
        if seed is not None and seed < 0:
            raise MediaInvalidRequestError(
                "image seed must be non-negative",
                code="media_invalid_request",
                provider=self.name,
            )
        url = (
            f"{self.base_url}/accounts/{quote(self.account_id, safe='')}/ai/run/"
            f"{quote(self.model, safe='@/') }"
        )
        body: dict[str, object] = {"prompt": prompt, "steps": 4}
        if seed is not None:
            body["seed"] = seed
        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        status, headers, raw = self.request_fn(request, self.timeout)
        payload = self._payload_or_error(status, headers, raw)
        try:
            encoded = payload["result"]["image"]
            content = base64.b64decode(encoded, validate=True)
        except (KeyError, TypeError, binascii.Error) as exc:
            raise MediaProviderError(
                "Cloudflare returned an invalid image response",
                code="media_invalid_response",
                provider=self.name,
            ) from exc
        return GeneratedImage(
            provider=self.name,
            model=self.model,
            content=content,
            content_type=(
                headers.get("content-type", "image/jpeg").split(";", 1)[0]
                if headers.get("content-type", "").startswith("image/")
                else "image/jpeg"
            ),
            metadata={
                "request": {
                    "prompt": prompt,
                    "references": list(references or []),
                    "aspect_ratio": aspect_ratio,
                    "seed": seed,
                    "steps": 4,
                },
                "response": {"success": payload.get("success", True)},
            },
        )

    def _payload_or_error(
        self,
        status: int,
        headers: Mapping[str, str],
        raw: bytes,
    ) -> dict:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MediaTransientError(
                "Cloudflare returned a non-JSON response",
                code="media_invalid_response",
                provider=self.name,
                retryable=status >= 500,
                status_code=status,
            ) from exc
        if status >= 400 or not payload.get("success", False):
            message = _error_message(payload, status)
            raise _cloudflare_error(status, message)
        return payload


def _error_message(payload: dict, status: int) -> str:
    errors = payload.get("errors") or []
    if errors and isinstance(errors[0], dict):
        return str(errors[0].get("message") or errors[0].get("code") or "Cloudflare request failed")
    return f"Cloudflare request failed with status {status}"


def _cloudflare_error(status: int, message: str) -> MediaProviderError:
    lowered = message.lower()
    if status in {401, 403}:
        return MediaAuthenticationError(message, code="media_authentication", provider="cloudflare", status_code=status)
    if status == 429:
        return MediaRateLimitError(message, code="media_rate_limited", provider="cloudflare", retryable=True, status_code=status)
    if status < 400:
        return MediaProviderError(message, code="media_provider_error", provider="cloudflare", status_code=status)
    if any(term in lowered for term in ("moderation", "safety", "content policy", "unsafe")):
        return MediaModerationError(message, code="media_moderation", provider="cloudflare", status_code=status)
    if 400 <= status < 500:
        return MediaInvalidRequestError(message, code="media_invalid_request", provider="cloudflare", status_code=status)
    return MediaTransientError(message, code="media_transient", provider="cloudflare", retryable=True, status_code=status)
