from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.agents.creative_director.contracts import CreativePackage
from studio.domain.constants import ApprovalStatus, ProjectStage, ProjectStatus
from studio.domain.schemas.contracts import StorySpec
from studio.domain.services.transitions import (
    advance_project_stage,
    transition_project_status,
)
from studio.persistence.models import IdeaCandidate, Project, StoryVersion
from studio.persistence.operations import approve_version, next_version, reject_version


class CreativeRecordNotFoundError(LookupError):
    pass


def persist_creative_package(
    session: Session,
    *,
    project_id: str,
    package: CreativePackage,
    persist_story: bool = True,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[list[IdeaCandidate], StoryVersion | None]:
    project = session.get(Project, project_id)
    if project is None:
        raise CreativeRecordNotFoundError(f"project {project_id} not found")

    candidates = []
    for candidate in package.candidates:
        record = IdeaCandidate(
            id=candidate.id,
            project_id=project_id,
            premise=candidate.premise,
            hook=candidate.hook,
            scores=candidate.scores.model_dump(),
            rationale=candidate.rationale,
            source_run=candidate.source_run,
            is_selected=False,
        )
        session.add(record)
        candidates.append(record)

    story = None
    if persist_story:
        story = StoryVersion(
            project_id=project_id,
            version=next_version(session, StoryVersion, project_id),
            payload=package.story.model_dump(mode="json"),
            critique=package.critique.model_dump(mode="json"),
            provider=provider or (package.providers_used[0] if package.providers_used else None),
            model=model,
        )
        session.add(story)
    session.flush()
    return candidates, story


def persist_story_draft(
    session: Session,
    *,
    project_id: str,
    story: StorySpec,
    critique: dict,
    provider: str | None = None,
    model: str | None = None,
) -> StoryVersion:
    if session.get(Project, project_id) is None:
        raise CreativeRecordNotFoundError(f"project {project_id} not found")
    record = StoryVersion(
        project_id=project_id,
        version=next_version(session, StoryVersion, project_id),
        payload=story.model_dump(mode="json"),
        critique=critique,
        provider=provider,
        model=model,
        approval_status=ApprovalStatus.DRAFT.value,
    )
    session.add(record)
    session.flush()
    return record


def select_idea(session: Session, *, project_id: str, idea_id: str) -> IdeaCandidate:
    idea = session.scalar(
        select(IdeaCandidate).where(IdeaCandidate.id == idea_id, IdeaCandidate.project_id == project_id)
    )
    if idea is None:
        raise CreativeRecordNotFoundError(f"idea {idea_id} not found for project {project_id}")
    candidates = session.scalars(select(IdeaCandidate).where(IdeaCandidate.project_id == project_id))
    for candidate in candidates:
        candidate.is_selected = candidate.id == idea.id
    session.flush()
    return idea


def revise_story(
    session: Session,
    *,
    project_id: str,
    story_version_id: str,
    story: StorySpec,
) -> StoryVersion:
    source = session.scalar(
        select(StoryVersion).where(StoryVersion.id == story_version_id, StoryVersion.project_id == project_id)
    )
    if source is None:
        raise CreativeRecordNotFoundError(f"story {story_version_id} not found for project {project_id}")
    revised = StoryVersion(
        project_id=project_id,
        version=next_version(session, StoryVersion, project_id),
        payload=story.model_dump(mode="json"),
        provider=source.provider,
        model=source.model,
        critique=None,
        approval_status=ApprovalStatus.DRAFT.value,
    )
    session.add(revised)
    session.flush()
    return revised


def approve_story(session: Session, *, project_id: str, story_version_id: str) -> StoryVersion:
    story = session.scalar(
        select(StoryVersion).where(StoryVersion.id == story_version_id, StoryVersion.project_id == project_id)
    )
    project = session.get(Project, project_id)
    if story is None or project is None:
        raise CreativeRecordNotFoundError(f"story {story_version_id} not found for project {project_id}")
    approved = approve_version(session, story)
    project.current_stage = advance_project_stage(project.current_stage, ProjectStage.STORY)
    project.status = transition_project_status(project.status, ProjectStatus.ACTIVE)
    session.flush()
    return approved


def reject_story(
    session: Session,
    *,
    project_id: str,
    story_version_id: str,
    reason: str,
) -> StoryVersion:
    story = session.scalar(
        select(StoryVersion).where(StoryVersion.id == story_version_id, StoryVersion.project_id == project_id)
    )
    if story is None:
        raise CreativeRecordNotFoundError(f"story {story_version_id} not found for project {project_id}")
    reject_version(story, reason=reason)
    session.flush()
    return story
