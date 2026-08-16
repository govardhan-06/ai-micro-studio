from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from sqlalchemy.orm import Session, sessionmaker

from studio.application.queries.projects import project_event_snapshot


async def project_event_stream(
    session_factory: sessionmaker[Session],
    *,
    project_id: str,
    poll_interval: float = 1.0,
    max_events: int | None = None,
) -> AsyncIterator[str]:
    previous_payload: str | None = None
    emitted_events = 0
    while True:
        with session_factory() as session:
            snapshot = project_event_snapshot(session, project_id=project_id)
        if snapshot is None:
            return

        payload = json.dumps(snapshot, separators=(",", ":"), sort_keys=True)
        if payload != previous_payload:
            previous_payload = payload
            emitted_events += 1
            yield f"event: project\ndata: {payload}\n\n"
            if max_events is not None and emitted_events >= max_events:
                return
        else:
            yield ": heartbeat\n\n"
        await asyncio.sleep(poll_interval)
