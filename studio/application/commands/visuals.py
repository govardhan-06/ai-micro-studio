from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.domain.constants import ApprovalStatus, ProjectStage, ProjectStatus
from studio.domain.schemas.contracts import (
    ShotSpec,
    StorySpec,
    VisualBible,
    VisualCharacter,
    VisualLocation,
    VisualStyle,
    normalize_visual_bible,
    no_text_instruction,
)
from studio.domain.services.transitions import advance_project_stage, transition_project_status
from studio.persistence.models import Asset, Project, Scene, StoryVersion, VisualBibleVersion
from studio.persistence.operations import approve_version, next_version


class VisualRecordNotFoundError(LookupError):
    pass


class VisualPrerequisiteError(ValueError):
    pass


def canonical_visual_bible_payload(visual_bible: VisualBible) -> dict:
    return visual_bible.model_dump(
        mode="json",
        exclude_none=True,
        exclude={
            "style": {"description", "palette", "camera_language"},
            "characters": {"__all__": {"appearance"}},
            "locations": {"__all__": {"description", "continuity_notes"}},
        },
    )


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
    locations: list[VisualLocation] = []
    location_by_description: dict[str, str] = {}
    for scene in story.scenes:
        key = " ".join(scene.visual_intent.lower().split())
        location_id = location_by_description.get(key)
        if location_id is None:
            location_id = f"loc_{len(locations) + 1:02d}"
            location_by_description[key] = location_id
            locations.append(
                VisualLocation(
                    id=location_id,
                    name=f"Location {len(locations) + 1}",
                    architecture_geometry=scene.visual_intent,
                    time="as approved in the StorySpec",
                    weather="as approved in the StorySpec",
                    lighting="motivated cinematic light",
                    persistent_props=[],
                    immutable_traits=["preserve the physical geometry across shots"],
                )
            )
    return VisualBible(
        style=VisualStyle(
            lighting=f"motivated practical light with {tone} contrast",
            lens_language="intimate close-ups, shallow depth of field, restrained push-ins",
            render_style=f"cinematic photorealism for {story.genre} short-form fiction",
            aspect_ratio="9:16",
        ),
        characters=[
            VisualCharacter(
                id="char_01",
                role="story protagonist",
                age="adult",
                presentation="as established by the approved StorySpec",
                ethnicity="as established by the approved StorySpec",
                face=f"recognizable protagonist from the approved premise: {story.premise}",
                hair="preserve one consistent hairstyle across every shot",
                build="preserve one consistent build across every shot",
                clothing="Choose one setting-appropriate outfit and preserve it across scenes.",
                accessories=[],
                immutable_traits=["same face, hair, build, and clothing in every shot"],
            )
        ],
        locations=locations,
    )


def shot_spec_for_scene(story: StorySpec, bible: VisualBible, scene_order: int) -> ShotSpec:
    scene = next((item for item in story.scenes if item.order == scene_order), None)
    if scene is None:
        raise VisualPrerequisiteError(f"story scene {scene_order} not found")
    location = next(
        (
            item
            for item in bible.locations
            if " ".join(item.architecture_geometry.lower().split()) == " ".join(scene.visual_intent.lower().split())
        ),
        bible.locations[0] if bible.locations else None,
    )
    if location is None:
        raise VisualPrerequisiteError("Visual Bible needs a physical location before storyboard generation")
    character_ids = [character.id for character in bible.characters]
    return ShotSpec(
        location_id=location.id,
        character_ids=character_ids,
        action=scene.visual_intent,
        expression="emotion follows the narration beat",
        composition="vertical portrait composition with a readable focal subject",
        camera="medium shot with motivated close-up coverage",
        temporary_props=[],
        lighting=location.lighting,
        continuity_source=[*character_ids, location.id],
    )


def build_image_prompt(bible: VisualBible, shot_spec: ShotSpec, *, previous_shot: str | None = None) -> str:
    characters = [character for character in bible.characters if character.id in shot_spec.character_ids]
    character_text = "; ".join(
        f"{character.id}: age {character.age}, {character.presentation}, {character.ethnicity}, face {character.face}, hair {character.hair}, build {character.build}, clothing {character.clothing}, accessories {', '.join(character.accessories) or 'none'}, immutable traits {', '.join(character.immutable_traits) or 'none'}"
        for character in characters
    ) or "no recurring character"
    location = next((item for item in bible.locations if item.id == shot_spec.location_id), None)
    if location is None:
        raise VisualPrerequisiteError(f"location {shot_spec.location_id} is not in the Visual Bible")
    continuity = ", ".join(shot_spec.continuity_source) or "approved Visual Bible"
    previous = f" Previous approved shot linkage: {previous_shot}." if previous_shot else ""
    return (
        f"Global style: lighting {bible.style.lighting}; lens language {bible.style.lens_language}; "
        f"render style {bible.style.render_style}; aspect ratio {bible.style.aspect_ratio}. "
        f"Canonical identities: {character_text}. "
        f"Physical location {location.id} ({location.name}): {location.architecture_geometry}; "
        f"time {location.time}; weather {location.weather}; lighting {location.lighting}; "
        f"persistent props {', '.join(location.persistent_props) or 'none'}; immutable traits {', '.join(location.immutable_traits) or 'none'}. "
        f"Shot delta: action {shot_spec.action}; expression {shot_spec.expression}; composition {shot_spec.composition}; "
        f"camera {shot_spec.camera}; temporary props {', '.join(shot_spec.temporary_props) or 'none'}; "
        f"moment lighting {shot_spec.lighting}. Continuity sources: {continuity}.{previous} "
        f"{no_text_instruction(shot_spec)}"
    )


def _reference_ids(bible: VisualBible) -> list[str]:
    return [asset_id for item in [*bible.characters, *bible.locations] for asset_id in item.reference_asset_ids]


def missing_reference_assets(session: Session, *, project_id: str, bible: VisualBible) -> list[str]:
    required = _reference_ids(bible)
    if not required:
        return [item.id for item in [*bible.characters, *bible.locations]]
    existing = {
        asset.id
        for asset in session.scalars(select(Asset).where(Asset.project_id == project_id, Asset.scene_id.is_(None)))
        if asset.asset_type in {"character_reference", "location_reference"} and asset.status == "available"
    }
    return [item for item in required if item not in existing]


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
        payload=canonical_visual_bible_payload(visual_bible),
        approval_status=ApprovalStatus.DRAFT.value,
    )
    session.add(record)
    session.flush()
    return record


def generate_visual_bible(
    session: Session,
    *,
    project_id: str,
    visual_bible: VisualBible | None = None,
) -> VisualBibleVersion:
    story = _approved_story(session, project_id)
    return persist_visual_bible_draft(
        session,
        project_id=project_id,
        visual_bible=visual_bible or derive_visual_bible(StorySpec.model_validate(story.payload)),
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


def generate_storyboard(
    session: Session,
    *,
    project_id: str,
    shot_specs: list[ShotSpec] | None = None,
) -> list[Scene]:
    story = _approved_story(session, project_id)
    visual_bible_record = _approved_visual_bible(session, project_id)
    visual_bible = normalize_visual_bible(visual_bible_record.payload)
    missing = missing_reference_assets(session, project_id=project_id, bible=visual_bible)
    if missing:
        raise VisualPrerequisiteError("canonical character and location references must be generated before storyboard creation")
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
    if shot_specs is not None and len(shot_specs) != len(story_spec.scenes):
        raise VisualPrerequisiteError("storyboard requires one ShotSpec per story scene")
    scenes = []
    for index, source in enumerate(story_spec.scenes):
        shot_spec = shot_specs[index] if shot_specs is not None else shot_spec_for_scene(story_spec, visual_bible, source.order)
        if shot_spec.location_id not in {location.id for location in visual_bible.locations}:
            raise VisualPrerequisiteError(f"shot spec location {shot_spec.location_id} is not in the approved Visual Bible")
        if set(shot_spec.character_ids) - {character.id for character in visual_bible.characters}:
            raise VisualPrerequisiteError("shot spec contains a character outside the approved Visual Bible")
        scenes.append(Scene(
            project_id=project_id,
            story_version_id=story.id,
            scene_order=source.order,
            narration=source.narration,
            duration_sec=source.duration_sec,
            strategy=source.asset_strategy,
            visual_intent=source.visual_intent,
            visual_prompt=build_image_prompt(visual_bible, shot_spec),
            shot_spec_json=shot_spec.model_dump(mode="json"),
            motion=source.motion,
            caption_emphasis=source.caption_emphasis,
            sfx=source.sfx,
        ))
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
    shot_spec: ShotSpec | None = None,
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
    if shot_spec is not None:
        scene.shot_spec_json = shot_spec.model_dump(mode="json")
    session.flush()
    return scene
