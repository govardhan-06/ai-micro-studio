from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Optional, Union


def build_idempotency_key(
    *,
    project_id: str,
    stage: str,
    version: Optional[Union[int, str]] = None,
    request: Optional[Mapping[str, Any]] = None,
) -> str:
    if not project_id or not stage:
        raise ValueError("project_id and stage are required")

    payload = {
        "project_id": project_id,
        "stage": stage,
        "version": version,
        "request": request or {},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
