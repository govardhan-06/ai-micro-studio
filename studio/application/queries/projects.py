from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.persistence.models import GenerationJob, Project


def list_projects(session: Session) -> list[Project]:
    return list(session.scalars(select(Project).order_by(Project.created_at.desc())))


def get_project(session: Session, *, project_id: str) -> Project | None:
    return session.get(Project, project_id)


def list_project_jobs(session: Session, *, project_id: str) -> list[GenerationJob]:
    return list(
        session.scalars(
            select(GenerationJob)
            .where(GenerationJob.project_id == project_id)
            .order_by(GenerationJob.created_at.asc())
        )
    )


def get_generation_job(session: Session, *, job_id: str) -> GenerationJob | None:
    return session.get(GenerationJob, job_id)


def normalize_generation_job_timeline(timeline: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        {**event, "attempt": 1 if event.get("attempt") is None else event["attempt"]}
        for event in timeline or []
    ]


def project_event_snapshot(session: Session, *, project_id: str) -> dict | None:
    project = get_project(session, project_id=project_id)
    if project is None:
        return None
    jobs = list_project_jobs(session, project_id=project_id)
    return {
        "project": {
            "id": project.id,
            "title": project.title,
            "status": project.status,
            "genre": project.genre,
            "current_stage": project.current_stage,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
        },
        "jobs": [
            {
                "id": job.id,
                "type": job.type,
                "stage": job.type,
                "status": job.status,
                "provider": job.provider,
                "model": job.model,
                "attempt": job.attempt,
                "max_attempts": job.max_attempts,
                "progress": job.progress,
                "error_code": job.error_code,
                "error_message": job.error_message,
                "latency_ms": job.latency_ms,
                "outcome": job.outcome,
                "usage": job.usage_json,
                "cost_usd": job.cost_usd,
                "regeneration_count": job.regeneration_count,
                "timeline": normalize_generation_job_timeline(job.timeline_json),
                "created_at": job.created_at.isoformat(),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            }
            for job in jobs
        ],
    }
