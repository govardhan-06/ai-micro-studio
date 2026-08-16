from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
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
            f"Cloudflare Whisper request failed: {exc}",
            code="audio_transient",
            provider="cloudflare_whisper",
            retryable=True,
        ) from exc


class CloudflareWhisperProvider(TranscriptionProvider):
    name = "cloudflare_whisper"

    def __init__(
        self,
        *,
        api_key: str | None,
        account_id: str | None,
        model: str = "@cf/openai/whisper-large-v3-turbo",
        base_url: str = "https://api.cloudflare.com/client/v4",
        timeout: float = 60,
        request_fn: RequestFn = _request,
    ) -> None:
        self.api_key = api_key.strip() if api_key else api_key
        self.account_id = account_id.strip() if account_id else account_id
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
        if not self.api_key or not self.account_id:
            raise AudioAuthenticationError(
                "Cloudflare API key and account ID are required",
                code="audio_authentication",
                provider=self.name,
            )
        if not audio:
            raise AudioInvalidRequestError(
                "audio content is required",
                code="audio_invalid_request",
                provider=self.name,
            )
        request = Request(
            f"{self.base_url}/accounts/{quote(self.account_id, safe='')}/ai/run/{quote(self.model, safe='@/')}",
            data=json.dumps(
                {
                    "audio": base64.b64encode(audio).decode("ascii"),
                    "task": "transcribe",
                    **({"language": language} if language else {}),
                }
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        status, headers, raw = self.request_fn(request, self.timeout)
        payload = self._payload_or_error(status, headers, raw)
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise AudioProviderResponseError(
                "Cloudflare Whisper returned no result object",
                code="audio_invalid_response",
                provider=self.name,
                status_code=status,
            )
        words = result.get("words")
        if isinstance(words, list) and words:
            timings = _word_timings(words, provider=self.name, status_code=status)
        else:
            segments = result.get("segments")
            if isinstance(segments, list):
                timings = _segment_word_timings(segments, provider=self.name, status_code=status)
            elif isinstance(result.get("vtt"), str):
                timings = _vtt_word_timings(result["vtt"], provider=self.name, status_code=status)
            else:
                raise AudioProviderResponseError(
                    "Cloudflare Whisper returned no usable word or segment timestamps",
                    code="audio_invalid_response",
                    provider=self.name,
                    status_code=status,
                )
        if any(timing.start_sec < 0 or timing.end_sec <= timing.start_sec for timing in timings):
            raise AudioProviderResponseError(
                "Cloudflare Whisper returned invalid word timing ranges",
                code="audio_invalid_response",
                provider=self.name,
                status_code=status,
            )
        return timings

    def _payload_or_error(self, status: int, headers: Mapping[str, str], raw: bytes) -> dict:
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if status >= 400:
                content_type = headers.get("Content-Type", headers.get("content-type", "unknown"))
                raise _cloudflare_error(
                    status,
                    f"Cloudflare Whisper returned a non-JSON error response (content type: {content_type})",
                ) from exc
            raise AudioProviderResponseError(
                "Cloudflare Whisper returned a non-JSON response",
                code="audio_invalid_response",
                provider=self.name,
                status_code=status,
            ) from exc
        if not isinstance(payload, Mapping):
            raise AudioProviderResponseError(
                "Cloudflare Whisper returned a non-object JSON response",
                code="audio_invalid_response",
                provider=self.name,
                status_code=status,
            )
        if status >= 400 or payload.get("success") is False:
            raise _cloudflare_error(status, _error_message(payload, status))
        return dict(payload)


def _word_timings(words: list[object], *, provider: str, status_code: int) -> list[WordTiming]:
    try:
        return [
            WordTiming(
                word=str(item["word"]).strip(),
                start_sec=float(item["start"]),
                end_sec=float(item["end"]),
            )
            for item in words
            if isinstance(item, Mapping) and str(item.get("word", "")).strip()
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise AudioProviderResponseError(
            "Cloudflare Whisper returned invalid word timestamps",
            code="audio_invalid_response",
            provider=provider,
            status_code=status_code,
        ) from exc


def _segment_word_timings(segments: list[object], *, provider: str, status_code: int) -> list[WordTiming]:
    timings: list[WordTiming] = []
    for segment in segments:
        if not isinstance(segment, Mapping):
            raise AudioProviderResponseError(
                "Cloudflare Whisper returned invalid segment timestamps",
                code="audio_invalid_response",
                provider=provider,
                status_code=status_code,
            )
        tokens = str(segment.get("text", "")).split()
        if not tokens:
            continue
        try:
            start_sec = float(segment["start"])
            end_sec = float(segment["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AudioProviderResponseError(
                "Cloudflare Whisper returned invalid segment timestamps",
                code="audio_invalid_response",
                provider=provider,
                status_code=status_code,
            ) from exc
        if start_sec < 0 or end_sec <= start_sec:
            raise AudioProviderResponseError(
                "Cloudflare Whisper returned invalid segment timing ranges",
                code="audio_invalid_response",
                provider=provider,
                status_code=status_code,
            )
        total_chars = sum(len(token) for token in tokens)
        cursor = start_sec
        for index, token in enumerate(tokens):
            next_cursor = end_sec if index == len(tokens) - 1 else cursor + (end_sec - start_sec) * len(token) / total_chars
            # ponytail: segment-proportional timings are approximate; use native word timestamps when available.
            timings.append(WordTiming(word=token, start_sec=cursor, end_sec=next_cursor))
            cursor = next_cursor
    return timings


def _vtt_word_timings(vtt: str, *, provider: str, status_code: int) -> list[WordTiming]:
    segments: list[dict[str, object]] = []
    lines = [line.strip() for line in vtt.splitlines()]
    index = 0
    while index < len(lines):
        line = lines[index]
        if "-->" not in line:
            index += 1
            continue
        start, end = (part.strip().split(" ", 1)[0] for part in line.split("-->", 1))
        text_lines: list[str] = []
        index += 1
        while index < len(lines) and lines[index]:
            text_lines.append(lines[index])
            index += 1
        try:
            segments.append({"start": _vtt_timestamp(start), "end": _vtt_timestamp(end), "text": " ".join(text_lines)})
        except ValueError as exc:
            raise AudioProviderResponseError(
                "Cloudflare Whisper returned invalid VTT timestamps",
                code="audio_invalid_response",
                provider=provider,
                status_code=status_code,
            ) from exc
    if not segments:
        raise AudioProviderResponseError(
            "Cloudflare Whisper returned an empty VTT transcript",
            code="audio_invalid_response",
            provider=provider,
            status_code=status_code,
        )
    return _segment_word_timings(segments, provider=provider, status_code=status_code)


def _vtt_timestamp(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return float(minutes) * 60 + float(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    raise ValueError(f"invalid VTT timestamp: {value}")

def _error_message(payload: Mapping[str, object], status: int) -> str:
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, Mapping):
            return str(first.get("message") or first.get("code") or f"Cloudflare Whisper request failed with status {status}")
        if first:
            return str(first)
    return f"Cloudflare Whisper request failed with status {status}"


def _cloudflare_error(status: int, message: str) -> AudioProviderError:
    if status == 401:
        return AudioAuthenticationError(message, code="audio_authentication", provider="cloudflare_whisper", status_code=status)
    if status == 403:
        return AudioProviderError(message, code="audio_forbidden", provider="cloudflare_whisper", status_code=status)
    if status == 429:
        return AudioRateLimitError(message, code="audio_rate_limited", provider="cloudflare_whisper", retryable=True, status_code=status)
    if 400 <= status < 500:
        return AudioInvalidRequestError(message, code="audio_invalid_request", provider="cloudflare_whisper", status_code=status)
    return AudioTransientError(message, code="audio_transient", provider="cloudflare_whisper", retryable=True, status_code=status)
