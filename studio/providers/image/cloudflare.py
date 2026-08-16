from __future__ import annotations

import base64
import binascii
import json
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
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
    ImageProviderCapabilities,
)
from studio.storage.local import create_artifact_storage


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
    model = "@cf/black-forest-labs/flux-2-klein-4b"

    def __init__(
        self,
        *,
        api_key: str | None,
        account_id: str | None,
        base_url: str = "https://api.cloudflare.com/client/v4",
        timeout: float = 30,
        model: str | None = None,
        request_fn: RequestFn = _request,
    ) -> None:
        self.api_key = api_key
        self.account_id = account_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.model = model or self.model
        self.request_fn = request_fn

    @property
    def capabilities(self) -> ImageProviderCapabilities:
        reference_capable = self.model == "@cf/black-forest-labs/flux-2-klein-4b"
        return ImageProviderCapabilities(
            supports_reference_images=reference_capable,
            max_reference_images=4 if reference_capable else 0,
            supports_image_editing=reference_capable,
        )

    def validate_model(self) -> bool:
        """Validate the configured model against Cloudflare's model-search endpoint."""
        if not self.api_key or not self.account_id:
            raise MediaAuthenticationError(
                "Cloudflare API key and account ID are required",
                code="media_authentication",
                provider=self.name,
            )
        request = Request(
            f"{self.base_url}/accounts/{quote(self.account_id, safe='')}/ai/models/search?search={quote(self.model, safe='')}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="GET",
        )
        status, headers, raw = self.request_fn(request, self.timeout)
        payload = self._payload_or_error(status, headers, raw)
        return any(item.get("name") == self.model or item.get("id") == self.model for item in payload.get("result", []))

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
            f"{quote(self.model, safe='@/')}"
        )
        reference_bytes = []
        selected_references = list(references or [])[: self.capabilities.max_reference_images]
        if self.capabilities.supports_reference_images:
            for reference in selected_references:
                reference_bytes.append(_reference_bytes(reference))
            fields = {"prompt": prompt, "width": str(_dimensions(aspect_ratio)[0]), "height": str(_dimensions(aspect_ratio)[1])}
            if seed is not None:
                fields["seed"] = str(seed)
            body, content_type = _multipart(fields, reference_bytes)
        else:
            body = json.dumps({"prompt": prompt, **({"seed": seed} if seed is not None else {})}).encode("utf-8")
            content_type = "application/json"
            reference_bytes = []
        request = Request(
            url,
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": content_type},
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
                    "references": selected_references,
                    "aspect_ratio": aspect_ratio,
                    "seed": seed,
                    "steps": 4 if self.capabilities.supports_reference_images else None,
                    "reference_order": list(range(len(reference_bytes))),
                },
                "capabilities": {
                    "supports_reference_images": self.capabilities.supports_reference_images,
                    "max_reference_images": self.capabilities.max_reference_images,
                    "supports_image_editing": self.capabilities.supports_image_editing,
                    "limitation": None if self.capabilities.supports_reference_images else "prompt_only_fallback",
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


def _dimensions(aspect_ratio: str | None) -> tuple[int, int]:
    if aspect_ratio == "9:16":
        return 768, 1365
    if aspect_ratio == "1:1":
        return 1024, 1024
    return 1024, 768


def _multipart(fields: Mapping[str, str], images: Sequence[bytes]) -> tuple[bytes, str]:
    boundary = f"----ai-micro-story-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )
    for index, image in enumerate(images):
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="input_image_{index}"; filename="reference-{index}.png"\r\n'.encode(),
                b"Content-Type: image/png\r\n\r\n",
                image,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _reference_bytes(reference: str) -> bytes:
    if reference.startswith("data:") and "," in reference:
        return base64.b64decode(reference.split(",", 1)[1])
    if reference.startswith("local://"):
        source = create_artifact_storage().read(reference)
    else:
        source = Path(reference).read_bytes()
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return source
    with tempfile.TemporaryDirectory(prefix="ai-micro-story-ref-") as directory:
        source_path = Path(directory) / "source"
        target_path = Path(directory) / "reference.png"
        source_path.write_bytes(source)
        completed = subprocess.run(
            [ffmpeg, "-y", "-i", str(source_path), "-vf", "scale='min(511,iw)':'min(511,ih)':force_original_aspect_ratio=decrease", str(target_path)],
            check=False,
            capture_output=True,
            timeout=30,
        )
        return target_path.read_bytes() if completed.returncode == 0 and target_path.is_file() else source


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
