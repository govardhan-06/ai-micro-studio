from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.domain.constants import ProjectStage
from studio.domain.services.transitions import advance_project_stage
from studio.persistence.models import MetricSnapshot, Project, Publication, Render, new_id, utc_now


class PublicationRecordNotFoundError(LookupError):
    pass


def create_publication(
    session: Session,
    *,
    project_id: str,
    platform: str,
    url: str | None,
    external_id: str | None,
    published_at: datetime | None,
) -> Publication:
    project = session.get(Project, project_id)
    if project is None:
        raise PublicationRecordNotFoundError(f"project {project_id} not found")
    final_render = session.scalar(
        select(Render).where(
            Render.project_id == project_id,
            Render.render_type == "final",
            Render.status == "succeeded",
        )
    )
    if final_render is None:
        raise ValueError("a succeeded final render is required before recording publication")
    publication = Publication(
        id=new_id(),
        project_id=project_id,
        platform=platform,
        url=url,
        external_id=external_id,
        published_at=published_at,
    )
    session.add(publication)
    project.current_stage = advance_project_stage(project.current_stage, ProjectStage.METRICS)
    session.flush()
    return publication


def list_publications(session: Session, *, project_id: str) -> list[Publication]:
    return list(
        session.scalars(
            select(Publication)
            .where(Publication.project_id == project_id)
            .order_by(Publication.published_at.desc(), Publication.created_at.desc())
        )
    )


def get_publication(session: Session, *, publication_id: str) -> Publication:
    publication = session.get(Publication, publication_id)
    if publication is None:
        raise PublicationRecordNotFoundError(f"publication {publication_id} not found")
    return publication


def create_metric_snapshot(
    session: Session,
    *,
    publication_id: str,
    captured_at: datetime | None,
    views: int,
    retention: float | None,
    likes: int,
    comments: int,
    shares_saves: int,
    followers_gained: int,
) -> MetricSnapshot:
    get_publication(session, publication_id=publication_id)
    snapshot = MetricSnapshot(
        id=new_id(),
        publication_id=publication_id,
        captured_at=captured_at or utc_now(),
        views=views,
        retention=retention,
        likes=likes,
        comments=comments,
        shares_saves=shares_saves,
        followers_gained=followers_gained,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def list_metric_snapshots(session: Session, *, publication_id: str) -> list[MetricSnapshot]:
    return list(
        session.scalars(
            select(MetricSnapshot)
            .where(MetricSnapshot.publication_id == publication_id)
            .order_by(MetricSnapshot.captured_at.desc())
        )
    )
