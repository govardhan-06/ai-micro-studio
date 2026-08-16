from __future__ import annotations

import base64
import binascii
import io
import json
import wave
from collections.abc import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from studio.providers.audio import (
    AudioArtifact,
    AudioAuthenticationError,
    AudioInvalidRequestError,
    AudioProviderError,
    AudioProviderResponseError,
    AudioRateLimitError,
    AudioTransientError,
    TTSProvider,
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
            f"Gemini TTS request failed: {exc}",
            code="audio_transient",
            provider="gemini_tts",
            retryable=True,
        ) from exc


class GeminiTTSProvider(TTSProvider):
    name = "gemini_tts"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gemini-3.1-flash-tts-preview",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 60,
        request_fn: RequestFn = _request,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.request_fn = request_fn

    def synthesize(self, text: str, *, voice: str | None = None, direction: str | None = None) -> AudioArtifact:
        if not self.api_key:
            raise AudioAuthenticationError(
                "Gemini API key is required",
                code="audio_authentication",
                provider=self.name,
            )
        if not 1 <= len(text.strip()) <= 10000:
            raise AudioInvalidRequestError(
                "narration text must contain between 1 and 10000 characters",
                code="audio_invalid_request",
                provider=self.name,
            )
        input_text = f"{direction.strip()}\n\n{text.strip()}" if direction and direction.strip() else text.strip()
        body = {
            "model": self.model,
            "input": input_text,
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice or "Kore"}]},
        }
        request = Request(
            f"{self.base_url}/interactions",
            data=json.dumps(body).encode("utf-8"),
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        status, headers, raw = self.request_fn(request, self.timeout)
        payload = self._payload_or_error(status, headers, raw)
        try:
            audio_block = _find_audio_block(payload)
            encoded = audio_block["data"]
            pcm = base64.b64decode(encoded, validate=True)
        except (KeyError, TypeError, binascii.Error) as exc:
            raise AudioProviderResponseError(
                "Gemini TTS returned no valid audio",
                code="audio_invalid_response",
                provider=self.name,
            ) from exc
        if not pcm:
            raise AudioProviderResponseError(
                "Gemini TTS returned empty audio",
                code="audio_invalid_response",
                provider=self.name,
            )
        sample_rate = _positive_int(audio_block.get("sample_rate"), default=24000)
        sample_width = 2
        channels = _positive_int(audio_block.get("channels"), default=1)
        wav_data, duration_sec, sample_rate, channels, sample_width = _audio_as_wav(
            pcm,
            channels=channels,
            sample_rate=sample_rate,
            sample_width=sample_width,
        )
        return AudioArtifact(
            provider=self.name,
            model=self.model,
            content=wav_data,
            content_type="audio/wav",
            duration_sec=duration_sec,
            metadata={
                "voice": voice or "Kore",
                "direction": direction,
                "sample_rate": sample_rate,
                "channels": channels,
                "sample_width": sample_width,
            },
        )

    def _payload_or_error(self, status: int, headers: Mapping[str, str], raw: bytes) -> dict:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AudioTransientError(
                "Gemini TTS returned a non-JSON response",
                code="audio_invalid_response",
                provider=self.name,
                retryable=status >= 500,
                status_code=status,
            ) from exc
        if status >= 400:
            raise _gemini_error(status, _error_message(payload, status))
        return payload


def _pcm_to_wav(pcm: bytes, *, channels: int, sample_rate: int, sample_width: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return output.getvalue()


def _audio_as_wav(
    audio: bytes,
    *,
    channels: int,
    sample_rate: int,
    sample_width: int,
) -> tuple[bytes, float, int, int, int]:
    if audio.startswith(b"RIFF") and audio[8:12] == b"WAVE":
        try:
            with wave.open(io.BytesIO(audio), "rb") as wav_file:
                actual_channels = wav_file.getnchannels()
                actual_sample_rate = wav_file.getframerate()
                actual_sample_width = wav_file.getsampwidth()
                duration_sec = wav_file.getnframes() / actual_sample_rate
        except (EOFError, wave.Error) as exc:
            raise AudioProviderResponseError(
                "Gemini TTS returned an invalid WAV payload",
                code="audio_invalid_response",
                provider="gemini_tts",
            ) from exc
        return audio, duration_sec, actual_sample_rate, actual_channels, actual_sample_width

    wav_data = _pcm_to_wav(audio, channels=channels, sample_rate=sample_rate, sample_width=sample_width)
    return wav_data, len(audio) / (sample_rate * channels * sample_width), sample_rate, channels, sample_width


def _find_audio_block(payload: Mapping[str, object]) -> Mapping[str, object]:
    output_audio = payload.get("output_audio")
    if isinstance(output_audio, Mapping):
        return output_audio

    steps = payload.get("steps")
    if isinstance(steps, list):
        for step in reversed(steps):
            if not isinstance(step, Mapping):
                continue
            content = step.get("content")
            if not isinstance(content, list):
                continue
            for block in reversed(content):
                if isinstance(block, Mapping) and block.get("type") == "audio":
                    return block

    raise KeyError("audio output block")


def _positive_int(value: object, *, default: int) -> int:
    return value if isinstance(value, int) and value > 0 else default


def _error_message(payload: dict, status: int) -> str:
    return str((payload.get("error") or {}).get("message") or f"Gemini TTS request failed with status {status}")


def _gemini_error(status: int, message: str) -> AudioProviderError:
    if status in {401, 403}:
        return AudioAuthenticationError(message, code="audio_authentication", provider="gemini_tts", status_code=status)
    if status == 429:
        return AudioRateLimitError(message, code="audio_rate_limited", provider="gemini_tts", retryable=True, status_code=status)
    if 400 <= status < 500:
        return AudioInvalidRequestError(message, code="audio_invalid_request", provider="gemini_tts", status_code=status)
    return AudioTransientError(message, code="audio_transient", provider="gemini_tts", retryable=True, status_code=status)
