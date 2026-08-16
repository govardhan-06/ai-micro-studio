from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.domain.constants import ApprovalStatus, ProjectStage, ProjectStatus
from studio.domain.schemas.contracts import (
    StorySpec,
    VisualBible,
    VisualCharacter,
    VisualLocation,
    VisualStyle,
)
from studio.domain.services.transitions import advance_project_stage, transition_project_status
from studio.persistence.models import Project, Scene, StoryVersion, VisualBibleVersion
from studio.persistence.operations import approve_version, next_version


class VisualRecordNotFoundError(LookupError):
    pass


class VisualPrerequisiteError(ValueError):
    pass


def _approved_story(session: Session, project_id: str) -> StoryVersion:
    story = session.scalar(
        select(StoryVersion)
        .where(
            StoryVersion.project_id == project_id,
            StoryVersion.approval_status == ApprovalStatus.APPROVED.value,
        )
        .order_by(StoryVersion.version.desc())
    )
    if story is None:
        raise VisualPrerequisiteError("an approved StorySpec is required")
    return story


def _approved_visual_bible(session: Session, project_id: str) -> VisualBibleVersion:
    bible = session.scalar(
        select(VisualBibleVersion)
        .where(
            VisualBibleVersion.project_id == project_id,
            VisualBibleVersion.approval_status == ApprovalStatus.APPROVED.value,
        )
        .order_by(VisualBibleVersion.version.desc())
    )
    if bible is None:
        raise VisualPrerequisiteError("an approved VisualBible is required")
    return bible


def derive_visual_bible(story: StorySpec) -> VisualBible:
    tone = ", ".join(story.tone)
    return VisualBible(
        style=VisualStyle(
            description=f"{story.genre} short-form visual treatment with {tone} tone",
            palette=["charcoal", "cool blue", "warm practical light"],
            camera_language=["intimate close-ups", "shallow depth of field", "restrained push-ins"],
        ),
        characters=[
            VisualCharacter(
                id="char_01",
                role="story protagonist",
                appearance=f"Keep the protagonist visually consistent with the approved premise: {story.premise}",
                clothing="Choose one setting-appropriate outfit and preserve it across scenes.",
            )
        ],
        locations=[
            VisualLocation(
                id=f"loc_{scene.order:02d}",
                description=scene.visual_intent,
                continuity_notes="Preserve the approved style, palette, and spatial details across scene assets.",
            )
            for scene in story.scenes
        ],
    )


def persist_visual_bible_draft(
    session: Session,
    *,
    project_id: str,
    visual_bible: VisualBible,
) -> VisualBibleVersion:
    if session.get(Project, project_id) is None:
        raise VisualRecordNotFoundError(f"project {project_id} not found")
    record = VisualBibleVersion(
        project_id=project_id,
        version=next_version(session, VisualBibleVersion, project_id),
        payload=visual_bible.model_dump(mode="json"),
        approval_status=ApprovalStatus.DRAFT.value,
    )
    session.add(record)
    session.flush()
    return record


def generate_visual_bible(session: Session, *, project_id: str) -> VisualBibleVersion:
    story = _approved_story(session, project_id)
    return persist_visual_bible_draft(
        session,
        project_id=project_id,
        visual_bible=derive_visual_bible(StorySpec.model_validate(story.payload)),
    )


def revise_visual_bible(
    session: Session,
    *,
    project_id: str,
    visual_bible: VisualBible,
) -> VisualBibleVersion:
    return persist_visual_bible_draft(session, project_id=project_id, visual_bible=visual_bible)


def approve_visual_bible(
    session: Session,
    *,
    project_id: str,
    visual_bible_version_id: str,
) -> VisualBibleVersion:
    record = session.scalar(
        select(VisualBibleVersion).where(
            VisualBibleVersion.id == visual_bible_version_id,
            VisualBibleVersion.project_id == project_id,
        )
    )
    project = session.get(Project, project_id)
    if record is None or project is None:
        raise VisualRecordNotFoundError(f"visual bible {visual_bible_version_id} not found")
    approved = approve_version(session, record)
    if list(ProjectStage).index(ProjectStage(project.current_stage)) < list(ProjectStage).index(ProjectStage.VISUAL_BIBLE):
        project.current_stage = advance_project_stage(project.current_stage, ProjectStage.VISUAL_BIBLE)
    project.status = transition_project_status(project.status, ProjectStatus.ACTIVE)
    session.flush()
    return approved


def generate_storyboard(session: Session, *, project_id: str) -> list[Scene]:
    story = _approved_story(session, project_id)
    _approved_visual_bible(session, project_id)
    existing = list(
        session.scalars(
            select(Scene).where(Scene.story_version_id == story.id).order_by(Scene.scene_order.asc())
        )
    )
    project = session.get(Project, project_id)
    if existing:
        if project is not None and list(ProjectStage).index(ProjectStage(project.current_stage)) < list(ProjectStage).index(ProjectStage.STORYBOARD):
            project.current_stage = advance_project_stage(project.current_stage, ProjectStage.STORYBOARD)
        return existing

    story_spec = StorySpec.model_validate(story.payload)
    scenes = [
        Scene(
            project_id=project_id,
            story_version_id=story.id,
            scene_order=source.order,
            narration=source.narration,
            duration_sec=source.duration_sec,
            strategy=source.asset_strategy,
            visual_intent=source.visual_intent,
            visual_prompt=source.visual_prompt,
            motion=source.motion,
            caption_emphasis=source.caption_emphasis,
            sfx=source.sfx,
        )
        for source in story_spec.scenes
    ]
    session.add_all(scenes)
    if project is not None:
        project.current_stage = advance_project_stage(project.current_stage, ProjectStage.STORYBOARD)
    session.flush()
    return scenes


def revise_scene(
    session: Session,
    *,
    scene_id: str,
    duration_sec: float | None = None,
    visual_prompt: str | None = None,
    asset_strategy: str | None = None,
) -> Scene:
    scene = session.get(Scene, scene_id)
    if scene is None:
        raise VisualRecordNotFoundError(f"scene {scene_id} not found")
    if duration_sec is not None:
        if not 0 < duration_sec <= 60:
            raise ValueError("scene duration must be greater than 0 and at most 60 seconds")
        scene.duration_sec = duration_sec
    if visual_prompt is not None:
        scene.visual_prompt = visual_prompt
    if asset_strategy is not None:
        scene.strategy = asset_strategy
    session.flush()
    return scene
