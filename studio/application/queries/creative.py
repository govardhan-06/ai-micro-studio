from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.persistence.models import IdeaCandidate, Scene, StoryVersion, VisualBibleVersion


def list_ideas(session: Session, *, project_id: str, sort: str = "score") -> list[IdeaCandidate]:
    ideas = list(
        session.scalars(select(IdeaCandidate).where(IdeaCandidate.project_id == project_id))
    )
    if sort == "created":
        return sorted(ideas, key=lambda idea: idea.created_at)
    if sort not in {"score", "created"}:
        raise ValueError("sort must be score or created")
    return sorted(ideas, key=lambda idea: sum(idea.scores.values()), reverse=True)


def list_stories(session: Session, *, project_id: str) -> list[StoryVersion]:
    return list(
        session.scalars(
            select(StoryVersion)
            .where(StoryVersion.project_id == project_id)
            .order_by(StoryVersion.version.desc())
        )
    )


def list_visual_bibles(session: Session, *, project_id: str) -> list[VisualBibleVersion]:
    return list(
        session.scalars(
            select(VisualBibleVersion)
            .where(VisualBibleVersion.project_id == project_id)
            .order_by(VisualBibleVersion.version.desc())
        )
    )


def list_scenes(session: Session, *, project_id: str) -> list[Scene]:
    return list(
        session.scalars(
            select(Scene)
            .where(Scene.project_id == project_id)
            .order_by(Scene.story_version_id, Scene.scene_order)
        )
    )
