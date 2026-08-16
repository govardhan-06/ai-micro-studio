from __future__ import annotations

import os
from typing import Protocol


CELERY_TASK_NAME = "studio.application.run_generation_job"


class JobDispatcher(Protocol):
    def dispatch(self, *, job_id: str, attempt: int) -> str:
        ...


class JobDispatchError(RuntimeError):
    def __init__(self, job_id: str, cause: Exception):
        super().__init__(f"could not dispatch generation job {job_id}")
        self.job_id = job_id
        self.cause = cause


class CeleryJobDispatcher:
    def __init__(self, broker_url: str | None = None):
        from celery import Celery

        self._celery = Celery(
            "ai_micro_story_studio_api",
            broker=broker_url or os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        )

    def dispatch(self, *, job_id: str, attempt: int) -> str:
        result = self._celery.send_task(CELERY_TASK_NAME, args=[job_id, attempt])
        return result.id


def enqueue_generation_job(session, dispatcher: JobDispatcher, **job_kwargs):
    from studio.application.commands.jobs import create_generation_job, fail_generation_job

    job, created = create_generation_job(session, **job_kwargs)
    session.commit()
    if not created:
        return job, False, False
    try:
        dispatcher.dispatch(job_id=job.id, attempt=job.attempt)
    except Exception as exc:
        fail_generation_job(
            session,
            job_id=job.id,
            attempt=job.attempt,
            error_code="dispatch_unavailable",
            error_message=str(exc),
        )
        session.commit()
        raise JobDispatchError(job.id, exc) from exc
    return job, True, True


def retry_and_enqueue_generation_job(session, dispatcher: JobDispatcher, *, job_id: str):
    from studio.application.commands.jobs import fail_generation_job, retry_generation_job_command

    job = retry_generation_job_command(session, job_id=job_id)
    session.commit()
    try:
        dispatcher.dispatch(job_id=job.id, attempt=job.attempt)
    except Exception as exc:
        fail_generation_job(
            session,
            job_id=job.id,
            attempt=job.attempt,
            error_code="dispatch_unavailable",
            error_message=str(exc),
        )
        session.commit()
        raise JobDispatchError(job.id, exc) from exc
    return job
