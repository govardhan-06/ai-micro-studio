from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any, Callable, TypeVar
from urllib import error, request

from pydantic import BaseModel, ValidationError

from studio.providers.llm.contracts import (
    LLMAuthenticationError,
    LLMInvalidRequestError,
    LLMModerationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResult,
    LLMStructuredOutputError,
    LLMTransientError,
)


StructuredT = TypeVar("StructuredT", bound=BaseModel)
Transport = Callable[[str, bytes, dict[str, str], float], tuple[int, bytes]]


def _default_transport(url: str, body: bytes, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read()
    except error.HTTPError as exc:
        return exc.code, exc.read()
    except (error.URLError, TimeoutError, socket.timeout) as exc:
        raise LLMTransientError(
            f"{type(exc).__name__}: provider request failed",
            code="provider_unavailable",
            provider="unknown",
            retryable=True,
        ) from exc


@dataclass
class OpenAICompatibleLLMProvider:
    name: str
    model: str
    api_key: str
    base_url: str
    timeout: float = 60.0
    strict_structured_output: bool = False
    transport: Transport = _default_transport

    def _url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            status, raw = self.transport(
                self._url(),
                json.dumps(payload).encode("utf-8"),
                {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                self.timeout,
            )
        except LLMProviderError as exc:
            if exc.provider == "unknown":
                raise type(exc)(
                    str(exc),
                    code=exc.code,
                    provider=self.name,
                    retryable=exc.retryable,
                    status_code=exc.status_code,
                ) from exc
            raise

        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LLMTransientError(
                "provider returned invalid JSON",
                code="invalid_provider_response",
                provider=self.name,
                retryable=True,
                status_code=status,
            ) from exc

        if status in (401, 403):
            raise LLMAuthenticationError(
                _error_message(body), code="authentication", provider=self.name, status_code=status
            )
        if status == 429:
            raise LLMRateLimitError(
                _error_message(body), code="rate_limit", provider=self.name, retryable=True, status_code=status
            )
        if status in (408, 409) or status >= 500:
            raise LLMTransientError(
                _error_message(body), code="provider_unavailable", provider=self.name, retryable=True, status_code=status
            )
        if status in (400, 422):
            message = _error_message(body)
            error_type = LLMModerationError if _looks_moderated(message) else LLMInvalidRequestError
            raise error_type(message, code="moderation" if error_type is LLMModerationError else "invalid_request", provider=self.name, status_code=status)
        if status >= 400:
            raise LLMProviderError(
                _error_message(body), code="provider_error", provider=self.name, retryable=False, status_code=status
            )
        if not isinstance(body, dict):
            raise LLMTransientError(
                "provider returned a non-object response",
                code="invalid_provider_response",
                provider=self.name,
                retryable=True,
                status_code=status,
            )
        return body

    def _generate(self, prompt: str, *, system_prompt: str | None = None, schema: type[StructuredT] | None = None) -> LLMResult[Any]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0.4}
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": self.strict_structured_output,
                    "schema": schema.model_json_schema(),
                },
            }

        body = self._request(payload)
        try:
            choice = body["choices"][0]
            message = choice["message"]
            content = message.get("content", "")
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            if not isinstance(content, str):
                raise TypeError("message content is not text")
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMTransientError(
                "provider response did not contain a chat message",
                code="invalid_provider_response",
                provider=self.name,
                retryable=True,
            ) from exc

        structured = None
        if schema is not None:
            try:
                structured = schema.model_validate(json.loads(content))
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                raise LLMStructuredOutputError(
                    "provider response failed the requested schema",
                    code="structured_output_invalid",
                    provider=self.name,
                    retryable=True,
                ) from exc
        return LLMResult(
            provider=self.name,
            model=self.model,
            text=content,
            structured=structured,
            usage=body.get("usage"),
        )

    def generate(self, prompt: str, *, system_prompt: str | None = None) -> LLMResult[BaseModel]:
        return self._generate(prompt, system_prompt=system_prompt)

    def generate_structured(
        self,
        prompt: str,
        schema: type[StructuredT],
        *,
        system_prompt: str | None = None,
    ) -> LLMResult[StructuredT]:
        return self._generate(prompt, system_prompt=system_prompt, schema=schema)


def _error_message(body: Any) -> str:
    if isinstance(body, dict):
        error_body = body.get("error", body)
        if isinstance(error_body, dict):
            return str(error_body.get("message", error_body))
    return str(body)


def _looks_moderated(message: str) -> bool:
    lowered = message.lower()
    return any(term in lowered for term in ("moderation", "safety", "content policy", "blocked"))
