from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from studio.domain.constants import ApprovalStatus, JobStatus
from studio.domain.services.idempotency import build_idempotency_key
from studio.domain.services.transitions import (
    InvalidTransitionError,
    transition_approval_status,
    transition_job_status,
)
from studio.persistence.models import (
    Asset,
    AssetSelection,
    GenerationJob,
    NarrationVersion,
    Scene,
    StoryVersion,
    VisualBibleVersion,
    new_id,
    utc_now,
)


VersionedRecord = TypeVar("VersionedRecord", StoryVersion, VisualBibleVersion, NarrationVersion)
logger = logging.getLogger("studio.jobs")


def next_version(session: Session, model: type[VersionedRecord], project_id: str) -> int:
    current = session.scalar(select(func.max(model.version)).where(model.project_id == project_id))
    return (current or 0) + 1


def approve_version(session: Session, version: VersionedRecord) -> VersionedRecord:
    transition_approval_status(version.approval_status, ApprovalStatus.APPROVED)
    previous_versions = session.scalars(
        select(type(version)).where(
            type(version).project_id == version.project_id,
            type(version).approval_status == ApprovalStatus.APPROVED.value,
            type(version).id != version.id,
        )
    )
    for previous in previous_versions:
        previous.approval_status = transition_approval_status(previous.approval_status, ApprovalStatus.SUPERSEDED)
    version.approval_status = ApprovalStatus.APPROVED.value
    version.approved_at = utc_now()
    return version


def reject_version(version: VersionedRecord, *, reason: str | None = None) -> VersionedRecord:
    if reason is not None and not reason.strip():
        raise ValueError("rejection reason cannot be blank")
    version.approval_status = transition_approval_status(version.approval_status, ApprovalStatus.REJECTED)
    if isinstance(version, StoryVersion):
        version.rejection_reason = reason.strip() if reason is not None else None
    return version


def _latency_ms(started_at: datetime | None, completed_at: datetime) -> float | None:
    if started_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return max(0.0, (completed_at - started_at).total_seconds() * 1000)


def record_generation_job_event(
    job: GenerationJob,
    *,
    status: JobStatus | str,
    outcome: str | None = None,
    now: datetime | None = None,
    latency_ms: float | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    occurred_at = now or utc_now()
    status_value = status.value if isinstance(status, JobStatus) else status
    event = {
        "occurred_at": occurred_at.isoformat(),
        "project_id": job.project_id,
        "job_id": job.id,
        "provider": job.provider,
        "model": job.model,
        "stage": job.type,
        "attempt": job.attempt or 1,
        "status": status_value,
        "outcome": outcome or status_value,
        "latency_ms": latency_ms,
        "usage": job.usage_json,
        "cost_usd": job.cost_usd,
        "regeneration_count": job.regeneration_count or 0,
        "error_code": error_code,
        "error_message": error_message,
    }
    job.timeline_json = [*(job.timeline_json or []), event]
    job.outcome = event["outcome"]
    if latency_ms is not None:
        job.latency_ms = latency_ms
    logger.info(
        "generation_job_event",
        extra={
            "job_event": event,
            "project_id": job.project_id,
            "job_id": job.id,
            "provider": job.provider,
            "model": job.model,
            "stage": job.type,
            "attempt": job.attempt,
            "latency_ms": latency_ms,
            "outcome": event["outcome"],
            "usage": job.usage_json,
            "cost_usd": job.cost_usd,
            "regeneration_count": job.regeneration_count or 0,
        },
    )
    return event


def select_asset(session: Session, *, scene_id: str, asset_id: str) -> AssetSelection:
    scene = session.get(Scene, scene_id)
    asset = session.get(Asset, asset_id)
    if scene is None or asset is None:
        raise ValueError("scene and asset must exist before selecting an asset")
    if asset.scene_id != scene.id:
        raise ValueError("asset does not belong to scene")
    qa_rejected = asset.status == "qa_rejected" or asset.metadata_json.get("qa", {}).get("passed") is False
    if asset.status != "available" and not qa_rejected:
        raise ValueError("only available or QA-rejected assets can be selected")

    selection = session.get(AssetSelection, scene_id)
    if selection is None:
        selection = AssetSelection(scene_id=scene_id, selected_asset_id=asset_id)
        session.add(selection)
    else:
        selection.selected_asset_id = asset_id
        selection.updated_at = utc_now()
    session.flush()
    return selection


def get_or_create_generation_job(
    session: Session,
    *,
    project_id: str,
    job_type: str,
    stage: str,
    version: int | str | None = None,
    request: dict[str, Any] | None = None,
    provider: str | None = None,
    model: str | None = None,
    max_attempts: int = 3,
) -> tuple[GenerationJob, bool]:
    key = build_idempotency_key(project_id=project_id, stage=stage, version=version, request=request)
    existing = session.scalar(select(GenerationJob).where(GenerationJob.idempotency_key == key))
    if existing is not None:
        return existing, False
    previous_regenerations = session.scalar(
        select(func.max(GenerationJob.regeneration_count)).where(
            GenerationJob.project_id == project_id,
            GenerationJob.type == job_type,
        )
    )
    job = GenerationJob(
        id=new_id(),
        project_id=project_id,
        type=job_type,
        provider=provider,
        model=model,
        request_json=request or {},
        attempt=1,
        max_attempts=max_attempts,
        idempotency_key=key,
        regeneration_count=(previous_regenerations if previous_regenerations is not None else -1) + 1,
    )
    record_generation_job_event(job, status=JobStatus.QUEUED, outcome="queued")
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError:
        existing = session.scalar(select(GenerationJob).where(GenerationJob.idempotency_key == key))
        if existing is None:
            raise
        return existing, False
    return job, True


def transition_generation_job(
    job: GenerationJob,
    target: JobStatus,
    *,
    progress: float | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    now: datetime | None = None,
) -> GenerationJob:
    target_value = transition_job_status(job.status, target)
    current_time = now or datetime.now(timezone.utc)
    if progress is not None and not 0 <= progress <= 1:
        raise ValueError("job progress must be between 0 and 1")

    job.status = target_value
    if progress is not None:
        job.progress = progress
    if target_value == JobStatus.RUNNING.value and job.started_at is None:
        job.started_at = current_time
    if target_value == JobStatus.SUCCEEDED.value:
        job.progress = 1
        job.completed_at = current_time
        job.error_code = None
        job.error_message = None
    elif target_value == JobStatus.FAILED.value:
        job.completed_at = current_time
        job.error_code = error_code
        job.error_message = error_message
    elif target_value == JobStatus.CANCELLED.value:
        job.completed_at = current_time
    record_generation_job_event(
        job,
        status=target_value,
        now=current_time,
        latency_ms=_latency_ms(job.started_at, current_time)
        if target_value in {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}
        else None,
        error_code=error_code,
        error_message=error_message,
    )
    return job


def retry_generation_job(job: GenerationJob) -> GenerationJob:
    if job.status != JobStatus.FAILED.value:
        raise InvalidTransitionError("only failed jobs can be retried")
    if job.attempt >= job.max_attempts:
        raise InvalidTransitionError("job has exhausted its retry attempts")
    job.attempt += 1
    job.status = JobStatus.QUEUED.value
    job.progress = 0
    job.started_at = None
    job.completed_at = None
    job.error_code = None
    job.error_message = None
    record_generation_job_event(job, status=JobStatus.QUEUED, outcome="retry_queued")
    return job
