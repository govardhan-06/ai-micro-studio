from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping, Sequence
from urllib.parse import quote
from urllib.request import Request, urlopen

from studio.domain.schemas.contracts import VisualQAResult
from studio.providers.media import MediaAuthenticationError, MediaProviderError


RequestFn = Callable[[Request, float], tuple[int, Mapping[str, str], bytes]]

QA_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "passed": {"type": "boolean"},
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "correction": {"type": "string"},
                },
                "required": ["code", "message", "severity", "correction"],
            },
        },
    },
    "required": ["passed", "score", "issues"],
}


def _request(request: Request, timeout: float) -> tuple[int, Mapping[str, str], bytes]:
    with urlopen(request, timeout=timeout) as response:
        return response.status, dict(response.headers.items()), response.read()


class CloudflareVisionProvider:
    name = "cloudflare"
    model = "@cf/meta/llama-4-scout-17b-16e-instruct"

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

    def evaluate(
        self,
        image: bytes,
        *,
        prompt: str,
        references: Sequence[bytes] = (),
        reference_asset_ids: Sequence[str] = (),
    ) -> VisualQAResult:
        if not self.api_key or not self.account_id:
            raise MediaAuthenticationError(
                "Cloudflare API key and account ID are required",
                code="media_authentication",
                provider=self.name,
            )
        images = [image, *references]
        content = [{"type": "text", "text": prompt}]
        content.extend(
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64.b64encode(item).decode()}"}}
            for item in images
        )
        request = Request(
            f"{self.base_url}/accounts/{quote(self.account_id, safe='')}/ai/run/{quote(self.model, safe='@/')}",
            data=json.dumps(
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": "Return only a JSON object matching the requested QA schema. Do not use markdown or add extra fields.",
                        },
                        {"role": "user", "content": content},
                    ],
                    "temperature": 0,
                    "guided_json": QA_RESPONSE_SCHEMA,
                }
            ).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        status, _, raw = self.request_fn(request, self.timeout)
        try:
            payload = json.loads(raw.decode())
            if status >= 400 or not payload.get("success", False):
                raise MediaProviderError(
                    "Cloudflare vision request failed",
                    code="media_qa_failed",
                    provider=self.name,
                    retryable=status >= 500,
                    status_code=status,
                )
            text = payload["result"].get("response", "")
            result = _decode_response(text)
            return VisualQAResult.model_validate(
                {**result, "model": self.model, "checked_reference_asset_ids": list(reference_asset_ids)}
            )
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise MediaProviderError(
                "Cloudflare vision returned an invalid QA response",
                code="media_qa_invalid_response",
                provider=self.name,
                retryable=status >= 500,
                status_code=status,
            ) from exc


def _decode_response(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        raise TypeError("Cloudflare vision response must be a JSON object")
    text = value.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) < 3:
            raise ValueError("Cloudflare vision response contains an empty code fence")
        text = "\n".join(lines[1:-1]).strip()
    result = json.loads(text)
    if not isinstance(result, Mapping):
        raise TypeError("Cloudflare vision response must be a JSON object")
    return result
