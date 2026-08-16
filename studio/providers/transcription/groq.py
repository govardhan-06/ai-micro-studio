from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from studio.providers.audio import (
    AudioAuthenticationError,
    AudioInvalidRequestError,
    AudioProviderError,
    AudioProviderResponseError,
    AudioRateLimitError,
    AudioTransientError,
    TranscriptionProvider,
    WordTiming,
)


RequestFn = Callable[[Request, float], tuple[int, Mapping[str, str], bytes]]


def _request(request: Request, timeout: float) -> tuple[int, Mapping[str, str], bytes]:
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()
    except (TimeoutError, URLError) as exc:
        raise AudioTransientError(
            f"Groq Whisper request failed: {exc}",
            code="audio_transient",
            provider="groq_whisper",
            retryable=True,
        ) from exc


class GroqWhisperProvider(TranscriptionProvider):
    name = "groq_whisper"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "whisper-large-v3-turbo",
        base_url: str = "https://api.groq.com/openai/v1",
        timeout: float = 60,
        request_fn: RequestFn = _request,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.request_fn = request_fn

    def align(
        self,
        audio: bytes,
        *,
        content_type: str = "audio/wav",
        language: str | None = "en",
    ) -> list[WordTiming]:
        if not self.api_key:
            raise AudioAuthenticationError(
                "Groq API key is required",
                code="audio_authentication",
                provider=self.name,
            )
        if not audio:
            raise AudioInvalidRequestError(
                "audio content is required",
                code="audio_invalid_request",
                provider=self.name,
            )
        boundary = f"----studio-{uuid.uuid4().hex}"
        body = _multipart_body(
            boundary,
            fields={
                "model": self.model,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
                **({"language": language} if language else {}),
            },
            file=("narration.wav", content_type, audio),
        )
        request = Request(
            f"{self.base_url}/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
            },
            method="POST",
        )
        status, headers, raw = self.request_fn(request, self.timeout)
        payload = self._payload_or_error(status, headers, raw)
        words = payload.get("words")
        if not isinstance(words, list):
            raise AudioProviderResponseError(
                "Groq Whisper returned no word timestamps",
                code="audio_invalid_response",
                provider=self.name,
            )
        try:
            result = [
                WordTiming(
                    word=str(item["word"]).strip(),
                    start_sec=float(item["start"]),
                    end_sec=float(item["end"]),
                )
                for item in words
                if str(item.get("word", "")).strip()
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise AudioProviderResponseError(
                "Groq Whisper returned invalid word timestamps",
                code="audio_invalid_response",
                provider=self.name,
            ) from exc
        if any(timing.start_sec < 0 or timing.end_sec <= timing.start_sec for timing in result):
            raise AudioProviderResponseError(
                "Groq Whisper returned invalid word timing ranges",
                code="audio_invalid_response",
                provider=self.name,
            )
        return result

    def _payload_or_error(self, status: int, headers: Mapping[str, str], raw: bytes) -> dict:
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if status >= 400:
                content_type = headers.get("Content-Type", headers.get("content-type", "unknown"))
                raise _groq_error(
                    status,
                    f"Groq Whisper returned a non-JSON error response (content type: {content_type})",
                ) from exc
            raise AudioProviderResponseError(
                "Groq Whisper returned a non-JSON response",
                code="audio_invalid_response",
                provider=self.name,
                status_code=status,
            ) from exc
        if not isinstance(payload, Mapping):
            raise AudioProviderResponseError(
                "Groq Whisper returned a non-object JSON response",
                code="audio_invalid_response",
                provider=self.name,
                status_code=status,
            )
        if status >= 400:
            error = payload.get("error")
            message = (
                str(error.get("message"))
                if isinstance(error, Mapping) and error.get("message")
                else str(error)
                if isinstance(error, str) and error
                else "Groq Whisper request failed"
            )
            raise _groq_error(status, message)
        return dict(payload)


def _multipart_body(
    boundary: str,
    *,
    fields: Mapping[str, str],
    file: tuple[str, str, bytes],
) -> bytes:
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
    filename, content_type, content = file
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks)


def _groq_error(status: int, message: str) -> AudioProviderError:
    if status == 401:
        return AudioAuthenticationError(
            f"{message} (HTTP {status})",
            code="audio_authentication",
            provider="groq_whisper",
            status_code=status,
        )
    if status == 403:
        return AudioProviderError(
            f"{message} (HTTP {status})",
            code="audio_forbidden",
            provider="groq_whisper",
            status_code=status,
        )
    if status == 429:
        return AudioRateLimitError(message, code="audio_rate_limited", provider="groq_whisper", retryable=True, status_code=status)
    if 400 <= status < 500:
        return AudioInvalidRequestError(message, code="audio_invalid_request", provider="groq_whisper", status_code=status)
    return AudioTransientError(message, code="audio_transient", provider="groq_whisper", retryable=True, status_code=status)
