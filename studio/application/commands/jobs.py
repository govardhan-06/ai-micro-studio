from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Any, Mapping

from studio.domain.constants import JobStatus
from studio.persistence.models import GenerationJob, Project
from studio.persistence.operations import (
    get_or_create_generation_job,
    retry_generation_job,
    transition_generation_job,
)


MAX_GENERATION_JOB_ATTEMPTS = 3


class ProjectNotFoundError(LookupError):
    pass


class GenerationJobNotFoundError(LookupError):
    pass


def create_generation_job(
    session: Session,
    *,
    project_id: str,
    job_type: str,
    version: int | str | None = None,
    request: dict | None = None,
    provider: str | None = None,
    model: str | None = None,
    max_attempts: int = MAX_GENERATION_JOB_ATTEMPTS,
) -> tuple[GenerationJob, bool]:
    if session.get(Project, project_id) is None:
        raise ProjectNotFoundError(project_id)
    if not 1 <= max_attempts <= MAX_GENERATION_JOB_ATTEMPTS:
        raise ValueError(f"max_attempts must be between 1 and {MAX_GENERATION_JOB_ATTEMPTS}")
    return get_or_create_generation_job(
        session,
        project_id=project_id,
        job_type=job_type,
        stage=job_type,
        version=version,
        request=request,
        provider=provider,
        model=model,
        max_attempts=max_attempts,
    )


def _locked_job(session: Session, job_id: str) -> GenerationJob:
    job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id).with_for_update())
    if job is None:
        raise GenerationJobNotFoundError(job_id)
    return job


def start_generation_job(session: Session, *, job_id: str, attempt: int) -> GenerationJob:
    job = _locked_job(session, job_id)
    if job.attempt != attempt or job.status != JobStatus.QUEUED.value:
        return job
    return transition_generation_job(job, JobStatus.RUNNING, progress=0)


def complete_generation_job(session: Session, *, job_id: str, attempt: int) -> GenerationJob:
    job = _locked_job(session, job_id)
    if job.attempt != attempt or job.status in {
        JobStatus.SUCCEEDED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELLED.value,
    }:
        return job
    return transition_generation_job(job, JobStatus.SUCCEEDED, progress=1)


def fail_generation_job(
    session: Session,
    *,
    job_id: str,
    attempt: int,
    error_code: str,
    error_message: str,
) -> GenerationJob:
    job = _locked_job(session, job_id)
    if job.attempt != attempt or job.status in {
        JobStatus.SUCCEEDED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELLED.value,
    }:
        return job
    return transition_generation_job(
        job,
        JobStatus.FAILED,
        error_code=error_code,
        error_message=error_message,
    )


def update_generation_job_observability(
    session: Session,
    *,
    job_id: str,
    attempt: int,
    provider: str | None = None,
    model: str | None = None,
    usage: Mapping[str, Any] | None = None,
    cost_usd: float | None = None,
) -> GenerationJob:
    job = _locked_job(session, job_id)
    if job.attempt != attempt or job.status in {
        JobStatus.SUCCEEDED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELLED.value,
    }:
        return job
    if provider is not None:
        job.provider = provider
    if model is not None:
        job.model = model
    if usage is not None:
        job.usage_json = dict(usage)
    if cost_usd is not None:
        if cost_usd < 0:
            raise ValueError("job cost cannot be negative")
        job.cost_usd = cost_usd
    return job


def retry_generation_job_command(session: Session, *, job_id: str) -> GenerationJob:
    job = _locked_job(session, job_id)
    retry_generation_job(job)
    session.flush()
    return job
